import pandas as pd
import logging

# Configuração básica de log para este módulo
logger = logging.getLogger(__name__)

def formatar_telefone_para_8_digitos(tel_str):
    """
    Formata um número para o padrão E.164 (+55DDDxxxxxxxx).
    Regra: 
    - Se tiver 11 dígitos (DDD + 9 + 8 num) e o 3º for 9, remove esse 9.
    - Se tiver 10 dígitos (DDD + 8 num), mantém.
    - Caso contrário, retorna None (inválido).
    """
    if not isinstance(tel_str, str) or not tel_str.strip():
        return None
        
    # Limpa tudo que não é número
    digitos = ''.join(filter(str.isdigit, tel_str))
    
    # Remove prefixo 55 se existir (para normalizar)
    if digitos.startswith('55') and len(digitos) > 11:
         digitos = digitos[2:]

    numero_final = ""
    
    # Regra Principal: 11 dígitos começando com DDD + 9
    if len(digitos) == 11 and digitos[2] == '9':
        ddd = digitos[0:2]
        resto = digitos[3:]
        numero_final = ddd + resto
    
    # Regra Secundária: Já está com 10 dígitos (DDD + 8)
    elif len(digitos) == 10:
        numero_final = digitos
        
    else:
        # Número inválido para a nossa regra
        return None
        
    return f"+55{numero_final}"

def carregar_dados(caminho_arquivo):
    """
    Lê o Excel e retorna um DataFrame básico.
    """
    try:
        # dtype=str garante que telefones não virem notação científica
        df = pd.read_excel(caminho_arquivo, dtype=str)
        df.dropna(how='all', inplace=True)
        return df
    except Exception as e:
        logger.error(f"Erro ao ler planilha: {e}")
        return None