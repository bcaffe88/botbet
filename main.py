import os
import re
import aiohttp
import asyncio
import logging
from telethon import TelegramClient, events
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from ia_openai import gerar_resposta_ia

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
CHAT_ID_SINAL = os.getenv("CHAT_ID_SINAL")
if not CHAT_ID_SINAL:
    raise ValueError("CHAT_ID_SINAL não configurado!")

logger.info(f"CHAT_ID_SINAL configurado como: {CHAT_ID_SINAL}")

@client.on(events.NewMessage(chats=int(CHAT_ID_SINAL)))
async def escutar(event):
    try:
        logger.info(f"Mensagem recebida no chat {event.chat_id}")
        logger.debug(f"Conteúdo: {event.raw_text[:200]}...")  # Log parcial do conteúdo

        if "OVER 0.5 HT" in event.raw_text:
            logger.info("Sinal detectado - Iniciando análise...")
            await analisar(event.raw_text)
        else:
            logger.info("Mensagem não contém a palavra-chave 'OVER 0.5 HT'")
            
    except Exception as e:
        logger.error(f"Erro no handler de mensagens: {str(e)}", exc_info=True)

async def iniciar():
    try:
        await client.start()
        logger.info("Client iniciado com sucesso")
        
        # Verifica conexão
        me = await client.get_me()
        logger.info(f"Conectado como: {me.username} (ID: {me.id})")
        
        # Lista os chats/diálogos ativos
        logger.info("Verificando acesso aos chats...")
        dialogs = await client.get_dialogs()
        logger.info(f"Total de chats acessíveis: {len(dialogs)}")
        
        # Filtra para encontrar o chat de sinais
        target_chat = next((d for d in dialogs if str(d.id) == CHAT_ID_SINAL), None)
        if target_chat:
            logger.info(f"Chat de sinais encontrado: {target_chat.name} (ID: {target_chat.id})")
        else:
            logger.warning(f"Chat de sinais (ID: {CHAT_ID_SINAL}) não encontrado nos diálogos!")
        
        await client.run_until_disconnected()
    except Exception as e:
        logger.critical(f"Erro fatal na inicialização: {str(e)}", exc_info=True)
        raise
