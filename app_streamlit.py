import streamlit as st
import pandas as pd
import os
import sys
import logging
from datetime import datetime
import plotly.express as px

# Importa módulos locais
from modules import leitor_planilha
from config.constants import MAPEAMENTO_LOTEAMENTO 
import backend_orchestrator 

# --- Configuração da Página ---
st.set_page_config(
    page_title="Sistema de Cobrança Waha",
    page_icon="📊",
    layout="wide"
)

# --- Captura de Logs para exibir na tela ---
class StreamlitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        if 'log_records' not in st.session_state:
            st.session_state.log_records = []
    
    def emit(self, record):
        try:
            msg = self.format(record)
            st.session_state.log_records.append(msg)
        except Exception:
            pass

def setup_gui_logging():
    if 'logging_setup_done' not in st.session_state:
        root_logger = logging.getLogger()
        handler = StreamlitLogHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        root_logger.addHandler(handler)
        st.session_state.logging_setup_done = True

def formatar_milhar(valor):
    if valor >= 1_000_000: return f"R$ {valor/1_000_000:.2f} Mi"
    if valor >= 1_000: return f"R$ {valor/1_000:.1f} Mil"
    return f"R$ {valor:,.2f}"

def main():
    setup_gui_logging()
    st.title("📊 Dashboard e Cobrança Automatizada")

    # AJUSTE 3: Usando backend_orchestrator
    config_app = backend_orchestrator.CONFIG

    with st.sidebar:
        st.header("1. Upload")
        uploaded_file = st.file_uploader("Planilha de Inadimplentes (.xlsx)", type=["xlsx"])
        
        st.markdown("---")
        st.header("2. Ação")
        btn_processar = st.button("🚀 Iniciar Disparos", type="primary", use_container_width=True)
        
        with st.expander("📝 Logs em Tempo Real", expanded=True):
            if 'log_records' in st.session_state:
                st.code("\n".join(st.session_state.log_records[-20:]), language="text")

    if not uploaded_file:
        st.info("👋 Faça o upload da planilha na barra lateral para começar.")
        return

    @st.cache_data
    def carregar_df(file):
        return leitor_planilha.carregar_dados(file)

    df = carregar_df(uploaded_file)
    
    if df is None or df.empty:
        st.error("Erro ao ler planilha ou planilha vazia.")
        return

    # --- Dashboard de Análise ---
    st.subheader("Visão Geral da Carteira")
    
    col_lot = config_app['col_loteamento']
    if col_lot in df.columns:
        df['cod_loteamento'] = df[col_lot].astype(str).str.split('/').str[0].str.strip()
        df['Nome Loteamento'] = df['cod_loteamento'].map(MAPEAMENTO_LOTEAMENTO).fillna(df['cod_loteamento'])
    else:
        df['Nome Loteamento'] = 'Geral'

    col_filt1, col_filt2 = st.columns(2)
    opcoes = ["Todos"] + list(df['Nome Loteamento'].unique())
    loteamento_sel = col_filt1.selectbox("Filtrar Empreendimento", options=opcoes)
    data_ref = col_filt2.date_input("Data Base para Cálculo de Atraso", value=datetime.now())

    dash_data = leitor_planilha.gerar_dados_dashboard_aging(df, config_app, data_ref, loteamento_sel)

    if dash_data and dash_data['kpis']['total_vencido'] > 0:
        col_kpi1, col_kpi2 = st.columns(2)
        col_kpi1.metric("Total Vencido (Selecionado)", formatar_milhar(dash_data['kpis']['total_vencido']))
        col_kpi2.metric("Clientes Envolvidos", len(df))

        col_graf1, col_graf2 = st.columns([0.6, 0.4])
        
        with col_graf1:
            fig = px.pie(dash_data['dados_donut'], values='Valor', names='Faixa de Atraso', hole=0.4, title="Aging da Dívida")
            st.plotly_chart(fig, use_container_width=True)
            
        with col_graf2:
            st.write("Detalhamento:")
            st.dataframe(dash_data['dados_donut'][['Faixa de Atraso', 'Valor', 'Percentual']], hide_index=True)
    else:
        st.warning("Nenhum débito vencido encontrado com os filtros atuais.")

    # --- Lógica de Disparo ---
    if btn_processar:
        st.divider()
        st.header("Processamento")
        st.session_state.log_records = []
        
        with st.status("Executando envios...", expanded=True) as status:
            st.write("Iniciando orquestrador...")
            
            uploaded_file.seek(0)
            # AJUSTE 4: Chamando backend_orchestrator
            resultado = backend_orchestrator.processar_cobrancas(uploaded_file)
            
            if resultado['status'] == 'sucesso':
                status.update(label="Concluído com Sucesso!", state="complete", expanded=False)
                st.balloons()
                st.success(resultado['message'])
            else:
                status.update(label="Concluído com Avisos/Erros", state="error")
                st.error(resultado['message'])

if __name__ == "__main__":
    main()