import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def formatar_telefone_para_8_digitos(tel_str):
    """
    Formata um número para o padrão E.164 (+55DDDxxxxxxxx).
    """
    if not isinstance(tel_str, str) or not tel_str.strip():
        return None
    digitos = ''.join(filter(str.isdigit, tel_str))
    if digitos.startswith('55') and len(digitos) > 11: digitos = digitos[2:]
    
    numero_final = ""
    if len(digitos) == 11 and digitos[2] == '9':
        numero_final = digitos[0:2] + digitos[3:]
    elif len(digitos) == 10:
        numero_final = digitos
    else:
        return None
        
    return f"+55{numero_final}"

def carregar_dados(caminho_arquivo):
    try:
        df = pd.read_excel(caminho_arquivo, dtype=str)
        df.dropna(how='all', inplace=True)
        return df
    except Exception as e:
        logger.error(f"Erro ao ler planilha: {e}")
        return None

# --- NOVA FUNÇÃO PARA O DASHBOARD ---
def gerar_dados_dashboard_aging(df, config, data_base=None, loteamento_selecionado="Todos"):
    col_vencimento = config.get('col_vencimento')
    col_valor = config.get('col_valor')
    col_loteamento_nome = 'Nome Loteamento' # Criado dinamicamente no app

    if not all([col_vencimento, col_valor]) or col_vencimento not in df.columns:
        return None

    # Filtra por loteamento se necessário
    df_dash = df.copy()
    
    # Tratamento de datas e valores
    df_dash[col_vencimento] = pd.to_datetime(df_dash[col_vencimento], errors='coerce', dayfirst=True)
    
    # Função auxiliar interna para converter moeda
    def converter_float(x):
        try:
            return float(str(x).replace('.', '').replace(',', '.'))
        except:
            return 0.0
            
    df_dash[col_valor] = df_dash[col_valor].apply(converter_float)

    if loteamento_selecionado != "Todos" and col_loteamento_nome in df_dash.columns:
        df_dash = df_dash[df_dash[col_loteamento_nome] == loteamento_selecionado]

    data_base = pd.to_datetime(data_base if data_base else datetime.now().date())
    
    # Pega apenas os vencidos
    df_vencidas = df_dash[df_dash[col_vencimento] < data_base].copy()
    
    if df_vencidas.empty:
        return {'kpis': {'total_vencido': 0}, 'dados_donut': pd.DataFrame()}

    # Calcula Aging (Faixas de atraso)
    df_vencidas['dias_atraso'] = (data_base - df_vencidas[col_vencimento]).dt.days
    bins = [-1, 30, 60, 90, 120, 180, 360, 720, float('inf')]
    labels = ['Até 30 dias', '31-60 dias', '61-90 dias', '91-120 dias', '121-180 dias', '181-360 dias', '361-720 dias', '720+ dias']
    df_vencidas['Faixa de Atraso'] = pd.cut(df_vencidas['dias_atraso'], bins=bins, labels=labels, right=True)
    
    total_vencido = df_vencidas[col_valor].sum()
    
    # Agrupa para o gráfico
    dados_donut = df_vencidas.groupby('Faixa de Atraso', observed=True)[col_valor].sum().reset_index()
    dados_donut.columns = ['Faixa de Atraso', 'Valor']
    
    if total_vencido > 0:
        dados_donut['Percentual'] = (dados_donut['Valor'] / total_vencido) * 100
    else:
        dados_donut['Percentual'] = 0

    return {
        'kpis': {'total_vencido': total_vencido},
        'dados_donut': dados_donut
    }