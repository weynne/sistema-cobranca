import time
import os
from dotenv import load_dotenv
import logging
import sys
import pandas as pd
from datetime import datetime

# Carrega variáveis de ambiente
load_dotenv()

# --- CONFIGURAÇÃO DE LOGS ---
LOG_DIR = "logs"
LOG_FILE = "processamento_cobrancas.log"

if not os.path.exists(LOG_DIR):
    try: os.makedirs(LOG_DIR)
    except OSError: pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(module)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, LOG_FILE), mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

try:
    from modules import leitor_planilha, construtor_mensagem, waha_sender, txt_sender
    from config.constants import MAPEAMENTO_LOTEAMENTO, MAPEAMENTO_EMPRESA_POR_CODIGO, EMPRESA_PADRAO
except ImportError as e:
    logger.critical(f"Erro ao importar módulos: {e}")
    raise

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
    if not isinstance(valor, (int, float)): return "N/A"
    try: return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

# --- FUNÇÃO RESGATADA DO PROJETO ANTIGO ---
def _salvar_descartados(df_descartados, nome_arquivo_original="planilha_upload"):
    if df_descartados.empty:
        return None, 0
    
    dir_descartados = "contatos_descartados"
    if not os.path.exists(dir_descartados):
        os.makedirs(dir_descartados, exist_ok=True)
        
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    # Limpa nome do arquivo para não dar erro no sistema de arquivos
    nome_base = os.path.splitext(os.path.basename(str(nome_arquivo_original)))[0]
    nome_base = ''.join(c for c in nome_base if c.isalnum() or c in (' ', '_', '-')).strip()
    
    caminho_arquivo = os.path.join(dir_descartados, f"{nome_base}_SEM_TELEFONE_{timestamp}.xlsx")

    try:
        df_descartados.to_excel(caminho_arquivo, index=False)
        logger.info(f"📁 Arquivo de descartados salvo: {caminho_arquivo}")
        return caminho_arquivo, len(df_descartados)
    except Exception as e:
        logger.error(f"Falha ao salvar descartados: {e}")
        return None, 0

def _processar_grupo_cliente(telefone, grupo_df):
    try:
        nome_cliente = grupo_df[CONFIG['col_nome']].iloc[0]
        
        lista_parcelas_info = []
        valor_total = 0.0
        
        codigos_loteamento = grupo_df[CONFIG['col_loteamento']].astype(str).str.split('/').str[0].str.strip().unique()
        empresas_encontradas = {MAPEAMENTO_EMPRESA_POR_CODIGO.get(cod) for cod in codigos_loteamento if cod in MAPEAMENTO_EMPRESA_POR_CODIGO}
        
        nome_empresa = empresas_encontradas.pop() if len(empresas_encontradas) == 1 else EMPRESA_PADRAO

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
        
        sucesso = False
        # Lógica Híbrida (TXT ou WAHA)
        if CONFIG['modo_envio'] == 'WAHA_SENDER':
            sucesso = waha_sender.enviar_mensagem(telefone, mensagem)
        else:
            # Modo Fallback (TXT) recuperado do projeto antigo
            sucesso = txt_sender.salvar_mensagem_em_txt(telefone, nome_cliente, mensagem)
            
        return sucesso, "Enviado" if sucesso else "Falha no Envio"
            
    except Exception as e:
        erro_msg = f"Erro interno: {str(e)}"
        logger.error(f"Erro ao processar {telefone}: {erro_msg}")
        return False, erro_msg

def processar_cobrancas(arquivo_input):
    logger.info("--- Iniciando Processamento ---")
    
    # Pega o nome do arquivo para usar no relatório de descartados
    nome_arquivo_origem = getattr(arquivo_input, 'name', 'upload_manual')
    
    df = leitor_planilha.carregar_dados(arquivo_input)
    if df is None or df.empty:
        return {'status': 'erro', 'message': 'Planilha vazia ou inválida', 'relatorio': []}

    col_tel = CONFIG['col_telefone']
    col_nome = CONFIG['col_nome']
    
    if col_tel not in df.columns:
        return {'status': 'erro', 'message': f"Coluna '{col_tel}' não encontrada.", 'relatorio': []}
    
    # 1. Tratamento e Separação 
    # Guarda o original para conferência
    df['original_tel'] = df[col_tel]
    # Tenta formatar
    df[col_tel] = df[col_tel].apply(leitor_planilha.formatar_telefone_para_8_digitos)
    
    # Separa Válidos vs Descartados
    df_validos = df[df[col_tel].notna()]
    df_descartados = df[df[col_tel].isna()]
    
    # Salva os descartados (Se houver)
    caminho_descartados, qtd_descartados = _salvar_descartados(df_descartados, nome_arquivo_origem)
    
    if df_validos.empty:
        msg = f"Nenhum telefone válido. {qtd_descartados} contatos descartados/salvos."
        logger.warning(msg)
        return {
            'status': 'aviso', 
            'message': msg, 
            'relatorio': [], 
            'arquivo_descartados': caminho_descartados
        }

    # 2. Processamento dos Válidos
    grupos = df_validos.groupby(col_tel)
    total_grupos = len(grupos)
    logger.info(f"Clientes válidos para envio: {total_grupos}. Descartados: {qtd_descartados}")
    
    sucessos = 0
    falhas = 0
    relatorio_detalhado = []

    for telefone, grupo in grupos:
        nome_cliente = grupo[col_nome].iloc[0] if col_nome in grupo.columns else "Desconhecido"
        status_envio, motivo = _processar_grupo_cliente(telefone, grupo)
        
        if status_envio:
            sucessos += 1
            logger.info(f"✅ Sucesso: {nome_cliente}")
        else:
            falhas += 1
            logger.warning(f"❌ Falha: {nome_cliente} - {motivo}")
            
        relatorio_detalhado.append({
            "Cliente": nome_cliente,
            "Telefone": telefone,
            "Status": "Sucesso" if status_envio else "Falha",
            "Detalhe": motivo
        })
        time.sleep(int(os.getenv('DELAY_SEGUNDOS', 1)))

    return {
        'status': 'sucesso',
        'message': f"Processo Fim. Sucessos: {sucessos} | Falhas: {falhas} | Sem Telefone: {qtd_descartados}",
        'mensagens_sucesso': sucessos,
        'falhas_envio': falhas,
        'relatorio': relatorio_detalhado,
        'arquivo_descartados': caminho_descartados 
    }