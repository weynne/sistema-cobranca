import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
import plotly.express as px

from modules import leitor_planilha
from config.constants import MAPEAMENTO_LOTEAMENTO, MAPEAMENTO_EMPRESA_POR_CODIGO
import backend_orchestrator

# --- DEFINIÇÃO DE CORES FIXAS (Mapa de Calor) ---
# Garante que a cor seja sempre a mesma, independente do filtro
CORES_AGING = {
    'a. Até 30 dias':   '#fee5d9',  # Vermelho bem claro
    'b. 31-60 dias':    '#fcbba1',
    'c. 61-90 dias':    '#fc9272',
    'd. 91-120 dias':   '#fb6a4a',
    'e. 121-180 dias':  '#ef3b2c',
    'f. 181-360 dias':  '#cb181d',
    'g. 361-720 dias':  '#a50f15',
    'h. 720+ dias':     '#67000d'   # Vermelho sangue/escuro
}

# --- Configuração da Página ---
st.set_page_config(
    page_title="Dashboard de Cobrança",
    page_icon="📊",
    layout="wide"
)

# --- Função de Leitura de Logs ---
def ler_logs_do_arquivo():
    log_path = os.path.join("logs", "processamento_cobrancas.log")
    if not os.path.exists(log_path): return "Aguardando logs..."
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[-50:])
    except: return "Erro ao ler logs."

# --- Função Visual (Estilo Projeto Antigo) ---
def exibir_resultados_processamento(resultados):
    if not resultados:
        st.error("O processamento não retornou resultados válidos.")
        return

    st.divider()
    
    if resultados['status'] == 'sucesso':
        st.success(f"🎉 **{resultados.get('message', 'Processamento concluído!')}**")
        if resultados.get('falhas_envio', 0) == 0:
            st.balloons()
    else:
        st.warning(f"⚠️ **{resultados.get('message')}**")

    # ESTRUTURA DE ABAS
    tab_resumo, tab_arquivos, tab_logs = st.tabs(["📊 Resumo", "📂 Arquivos Gerados", "📝 Logs"])
    
    with tab_resumo:
        st.subheader("Visão Geral do Processamento")
        resumo_data = {
            "Métrica": ["Total de Clientes", "Enviados com Sucesso", "Falhas de Envio", "Sem Telefone (Descartados)"],
            "Quantidade": [
                str((resultados.get('mensagens_sucesso', 0) + resultados.get('falhas_envio', 0) + resultados.get('num_descartados_arquivo', 0))),
                str(resultados.get('mensagens_sucesso', 0)),
                str(resultados.get('falhas_envio', 0)),
                str(resultados.get('num_descartados_arquivo', 0) if resultados.get('arquivo_descartados') else "0")
            ]
        }
        st.table(pd.DataFrame(resumo_data).set_index("Métrica"))

    with tab_arquivos:
        st.subheader("Downloads Disponíveis")
        col_down1, col_down2 = st.columns(2)
        
        with col_down1:
            arq_descartados = resultados.get('arquivo_descartados')
            if arq_descartados and os.path.exists(arq_descartados):
                st.info("Alguns contatos não tinham telefone válido e foram separados.")
                with open(arq_descartados, "rb") as fp:
                    st.download_button(
                        label="⬇️ Baixar Planilha de Descartados (.xlsx)",
                        data=fp,
                        file_name=os.path.basename(arq_descartados),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.success("✅ Nenhum contato precisou ser descartado.")

        with col_down2:
            relatorio = resultados.get('relatorio', [])
            if relatorio:
                st.info("Relatório detalhado com status de cada envio.")
                df_rel = pd.DataFrame(relatorio)
                csv = df_rel.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Baixar Relatório de Status (.csv)",
                    data=csv,
                    file_name=f"relatorio_status_{datetime.now().strftime('%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    with tab_logs:
        st.subheader("Logs Detalhados")
        logs_txt = ler_logs_do_arquivo()
        st.text_area("Console:", value=logs_txt, height=300)

def formatar_milhar(valor):
    if valor >= 1_000_000: return f"R$ {valor/1_000_000:.2f} Mi"
    if valor >= 1_000: return f"R$ {valor/1_000:.1f} Mil"
    return f"R$ {valor:,.2f}"

def main():
    with st.sidebar:
        st.header("⚙️ Configuração")
        uploaded_file = st.file_uploader("1. Escolha a planilha de cobrança", type=["xlsx", "xls"])
        
        st.markdown("---")
        st.header("🚀 Ação Principal")
        btn_processar = st.button("2. Gerar Mensagens de Cobrança", type="primary", use_container_width=True, disabled=(uploaded_file is None))

    st.title("📊 Dashboard e Cobrança Automatizada")
    config_app = backend_orchestrator.CONFIG

    if not uploaded_file:
        st.info("⬅️ Por favor, carregue uma planilha na barra lateral para começar.")
        return

    @st.cache_data
    def carregar_df(file): return leitor_planilha.carregar_dados(file)

    df = carregar_df(uploaded_file)
    if df is None or df.empty:
        st.error("A planilha carregada está vazia ou não foi lida corretamente.")
        return

    # --- Dashboard ---
    st.header("Análise de Inadimplência")
    
    col_lot = config_app['col_loteamento']
    if col_lot in df.columns:
        df['cod_loteamento'] = df[col_lot].astype(str).str.split('/').str[0].str.strip()
        df['Nome Loteamento'] = df['cod_loteamento'].map(MAPEAMENTO_LOTEAMENTO).fillna(df['cod_loteamento'])
    else: 
        df['Nome Loteamento'] = 'Geral'
        df['cod_loteamento'] = '0'

    c_filt1, c_filt2 = st.columns(2)
    
    empresas_unicas = sorted(list(set(MAPEAMENTO_EMPRESA_POR_CODIGO.values())))
    loteamentos_unicos = sorted(list(df['Nome Loteamento'].unique()))
    opcoes_filtro = ["Todos"] + empresas_unicas + loteamentos_unicos
    
    selecao = c_filt1.selectbox("Filtrar por Empreendimento ou Empresa", opcoes_filtro)
    data_ref = c_filt2.date_input("Data Base da Análise", value=datetime.now(), format="DD/MM/YYYY")

    # Lógica de Filtro
    df_filtrado = df.copy()
    if selecao == "Todos":
        pass
    elif selecao in empresas_unicas:
        codigos_da_empresa = [cod for cod, emp in MAPEAMENTO_EMPRESA_POR_CODIGO.items() if emp == selecao]
        df_filtrado = df_filtrado[df_filtrado['cod_loteamento'].isin(codigos_da_empresa)]
    else:
        df_filtrado = df_filtrado[df_filtrado['Nome Loteamento'] == selecao]

    dash_data = leitor_planilha.gerar_dados_dashboard_aging(df_filtrado, config_app, data_ref, "Todos")

    st.markdown("---")

    if dash_data and dash_data['kpis']['total_vencido'] > 0:
        kpis = dash_data['kpis']
        c1, c2, c3 = st.columns(3)
        c1.metric("Valor Total Vencido", formatar_milhar(kpis['total_vencido']))
        c2.metric("Clientes Envolvidos", len(df_filtrado))
        c3.metric("Ticket Médio", formatar_milhar(kpis['total_vencido']/len(df_filtrado)))

        st.markdown("<br>", unsafe_allow_html=True)
        
        c_graf, c_tab = st.columns([0.6, 0.4])
        with c_graf:
            st.subheader("Aging do Valor Vencido")
            
            # Ordenação dos dados para garantir a legenda correta
            df_chart = dash_data['dados_donut'].sort_values('Faixa de Atraso')

            # --- USO DE MAPA DE CORES FIXO ---
            # Aqui usamos 'color_discrete_map' em vez de sequence.
            # Isso garante que a chave 'a. Até 30 dias' tenha SEMPRE a cor #fee5d9,
            # mesmo que ela seja a única fatia do gráfico.
            fig = px.pie(
                df_chart, 
                values='Valor', 
                names='Faixa de Atraso', 
                hole=0.4,
                color='Faixa de Atraso', # Necessário para o mapa funcionar bem
                color_discrete_map=CORES_AGING
            )
            
            fig.update_traces(sort=False, textposition='outside', textinfo='percent+label', rotation=90)
            st.plotly_chart(fig, use_container_width=True)
            
        with c_tab:
            st.subheader("Tabela de Apoio")
            df_disp = df_chart[['Faixa de Atraso', 'Valor', 'Percentual']].copy()
            df_disp['Valor'] = df_disp['Valor'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            df_disp['Percentual'] = df_disp['Percentual'].apply(lambda x: f"{x:.2f}%")
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
    else:
        st.warning("Nenhum dado vencido encontrado para o filtro selecionado.")

    if btn_processar:
        with st.spinner("⏳ Processando..."):
            uploaded_file.seek(0)
            resultados = backend_orchestrator.processar_cobrancas(uploaded_file)
            exibir_resultados_processamento(resultados)

if __name__ == "__main__":
    main()