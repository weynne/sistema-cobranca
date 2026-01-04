import os
import re
import logging 
from datetime import datetime

logger = logging.getLogger(__name__)

DIRETORIO_SAIDA = "mensagens_txt_geradas"

def limpar_nome_arquivo(nome): 
    # Remove caracteres especiais para não quebrar o sistema de arquivos
    nome = re.sub(r'[^\w\s-]', '', str(nome))
    nome = re.sub(r'\s+', '_', nome)
    return nome[:50]

def salvar_mensagem_em_txt(telefone_destino, nome_cliente, mensagem): 
    if not telefone_destino:
        telefone_destino = "telefone_na"
    if not nome_cliente:
        nome_cliente = "cliente_desconhecido"

    try:
        os.makedirs(DIRETORIO_SAIDA, exist_ok=True)
    except OSError as e:
        logger.error(f"Erro ao criar diretório '{DIRETORIO_SAIDA}': {e}")
        return False

    nome_cliente_limpo = limpar_nome_arquivo(nome_cliente)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"cobranca_{telefone_destino}_{nome_cliente_limpo}_{timestamp}.txt"
    caminho_completo = os.path.join(DIRETORIO_SAIDA, nome_arquivo)

    try:
        with open(caminho_completo, 'w', encoding='utf-8') as f:
            f.write(f"Destinatário: {telefone_destino}\n")
            f.write(f"Nome: {nome_cliente}\n")
            f.write("="*30 + "\n")
            f.write(mensagem) 
        logger.info(f"TXT salvo: {caminho_completo}")
        return True
    except Exception as e: 
        logger.error(f"Erro ao salvar arquivo TXT: {e}")
        return False