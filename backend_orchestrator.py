import time
import os
from dotenv import load_dotenv
import logging
import sys
import pandas as pd

# Carrega variáveis de ambiente
load_dotenv()

# --- CONFIGURAÇÃO DE LOGS ---
LOG_DIR = "logs"
LOG_FILE = "processamento_cobrancas.log"

if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
        print(f"Diretório '{LOG_DIR}' criado com sucesso.")
    except OSError as e:
        print(f"Erro ao criar diretório de logs: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(module)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, LOG_FILE), mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
# ----------------------------

try:
    from modules import leitor_planilha, construtor_mensagem, waha_sender, txt_sender
    from config.constants import MAPEAMENTO_LOTEAMENTO, MAPEAMENTO_EMPRESA_POR_CODIGO, EMPRESA_PADRAO
except ImportError as e:
    logger.critical(f"Erro ao importar módulos: {e}")
    raise

# Carrega Configurações do .env com valores padrão
CONFIG = {
    'col_nome': os.getenv('COLUNA_NOME', 'CLIENTE'),
    'col_telefone': os.getenv('COLUNA_TELEFONE', 'TELEFONE'),
    'col_lote': os.getenv('COLUNA_LOTE', 'NUMERO'),
    'col_valor': os.getenv('COLUNA_VALOR', 'SALDO'),
    'col_vencimento': os.getenv('COLUNA_VENCIMENTO', 'VENCTO.'),
    'col_loteamento': os.getenv('COLUNA_LOTEAMENTO', 'DUPLICATA'),
    'telefone_contato': os.getenv('TELEFONE_CONTATO', ''),
    'modo_envio': os.getenv('MODO_ENVIO', 'WAHA_SENDER')
}

def _formatar_moeda(valor):
    if not isinstance(valor, (int, float)):
        return "N/A"
    try:
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor)

def _processar_grupo_cliente(telefone, grupo_df):
    try:
        nome_cliente = grupo_df[CONFIG['col_nome']].iloc[0]
        
        lista_parcelas_info = []
        valor_total = 0.0
        
        codigos_loteamento = grupo_df[CONFIG['col_loteamento']].astype(str).str.split('/').str[0].str.strip().unique()
        empresas_encontradas = {MAPEAMENTO_EMPRESA_POR_CODIGO.get(cod) for cod in codigos_loteamento if cod in MAPEAMENTO_EMPRESA_POR_CODIGO}
        
        if len(empresas_encontradas) == 1:
            nome_empresa = empresas_encontradas.pop()
        else:
            nome_empresa = EMPRESA_PADRAO

        for _, parcela in grupo_df.iterrows():
            cod_loteamento = str(parcela.get(CONFIG['col_loteamento'], '')).split('/')[0].strip()
            valor_parcela = pd.to_numeric(parcela.get(CONFIG['col_valor']), errors='coerce') or 0.0
            
            info = {
                'loteamento_nome': MAPEAMENTO_LOTEAMENTO.get(cod_loteamento, cod_loteamento),
                'lote': parcela.get(CONFIG['col_lote'], 'N/A'),
                'vencimento': str(parcela.get(CONFIG['col_vencimento'])),
                'valor': _formatar_moeda(valor_parcela)
            }
            lista_parcelas_info.append(info)
            valor_total += valor_parcela

        mensagem = construtor_mensagem.criar_mensagem_consolidada(
            nome_cliente=nome_cliente,
            lista_parcelas_info=lista_parcelas_info,
            valor_total_fmt=_formatar_moeda(valor_total),
            nome_empresa=nome_empresa,
            telefone_contato=CONFIG['telefone_contato']
        )
        
        if CONFIG['modo_envio'] == 'WAHA_SENDER':
            return waha_sender.enviar_mensagem(telefone, mensagem)
        else:
            return txt_sender.salvar_mensagem_em_txt(telefone, nome_cliente, mensagem)
            
    except Exception as e:
        logger.error(f"Erro ao processar grupo do telefone {telefone}: {e}")
        return False

def processar_cobrancas(arquivo_input):
    logger.info("--- Iniciando Processamento de Cobranças ---")
    
    df = leitor_planilha.carregar_dados(arquivo_input)
    if df is None or df.empty:
        return {'status': 'erro', 'message': 'Planilha vazia ou inválida'}

    col_tel = CONFIG['col_telefone']
    
    if col_tel not in df.columns:
        return {'status': 'erro', 'message': f"Coluna '{col_tel}' não encontrada na planilha."}
    
    df[col_tel] = df[col_tel].apply(leitor_planilha.formatar_telefone_para_8_digitos)
    
    df_validos = df[df[col_tel].notna()]
    
    if df_validos.empty:
        return {'status': 'aviso', 'message': 'Nenhum telefone válido encontrado para processar.'}

    grupos = df_validos.groupby(col_tel)
    total_grupos = len(grupos)
    logger.info(f"Encontrados {total_grupos} clientes únicos com telefone válido.")
    
    sucessos = 0
    falhas = 0

    for telefone, grupo in grupos:
        if _processar_grupo_cliente(telefone, grupo):
            sucessos += 1
        else:
            falhas += 1
            
    return {
        'status': 'sucesso',
        'message': f"Processamento finalizado. Sucessos: {sucessos}, Falhas: {falhas}",
        'mensagens_sucesso': sucessos,
        'falhas_envio': falhas
    }