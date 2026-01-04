import requests
import logging
import time
import os

logger = logging.getLogger(__name__)

def enviar_mensagem(telefone, mensagem):
    """
    Envia a mensagem de texto via API do Waha.
    Retorna True se sucesso (201/200), False caso contrário.
    """
    # Carrega configs do ambiente
    base_url = os.getenv("WAHA_BASE_URL", "http://localhost:3000")
    api_key = os.getenv("WAHA_API_KEY")
    session = os.getenv("WAHA_SESSION_NAME", "default")
    
    # Validação básica
    if not api_key:
        logger.error("WAHA_API_KEY não definida no .env")
        return False
        
    if not telefone:
        return False

    url = f"{base_url}/api/sendText"
    
    # Formata o chatId (Ex: 558199998888@c.us)
    # Removemos o + só pra garantir, pois o Waha às vezes prefere números limpos
    chat_id = f"{telefone.replace('+', '')}@c.us"
    
    payload = {
        "chatId": chat_id,
        "text": mensagem,
        "session": session
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key
    }
    
    try:
        logger.debug(f"Enviando para {chat_id}...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            # Sucesso!
            return True
        else:
            logger.error(f"Erro API Waha ({response.status_code}): {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout ao conectar com {base_url}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de conexão: {e}")
        return False