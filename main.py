#!/usr/bin/env python3
import os
import re
import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient, events, types
from telethon.tl.types import PeerChannel
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from ia_openai import gerar_resposta_ia

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sinais_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))  # Canal de origem (-1001511464712)
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))  # Grupo de destino
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Inicialização dos clients
bot = Bot(token=BOT_TOKEN)
client = TelegramClient(
    "sessao_pessoal",  # Nome da sessão alterado para refletir que é sua conta
    API_ID,
    API_HASH,
    system_version="4.16.30-vxCustom",
    connection_retries=5
)

class ProcessadorSinais:
    def __init__(self):
        self.ultima_mensagem = None

    async def encaminhar_mensagem(self, event):
        """Encaminha mensagens usando sua conta pessoal via Telethon"""
        try:
            # Verifica se é uma mensagem de canal
            if isinstance(event.peer_id, PeerChannel):
                logger.info(f"📨 Mensagem recebida do canal (ID: {event.id})")
                
                # Encaminha a mensagem crua para o grupo destino
                forwarded = await client.forward_messages(
                    entity=CHAT_ID_DESTINO,
                    messages=event.message
                )
                
                self.ultima_mensagem = forwarded.id
                logger.info(f"✅ Encaminhada para grupo destino (ID: {forwarded.id})")
                return forwarded
                
        except Exception as e:
            logger.error(f"❌ Falha ao encaminhar: {str(e)}", exc_info=True)
            raise

    async def enviar_analise(self, event):
        """Envia análise refinada usando o bot"""
        try:
            texto = event.raw_text
            
            # Extrai dados básicos
            jogo = self.extrair_jogo(texto)
            
            # Gera análise IA
            analise = await self.gerar_analise_tecnica(texto)
            
            # Monta resposta
            resposta = (
                f"⚡️ **Análise Técnica** ⚡️\n\n"
                f"📌 **Jogo**: {jogo}\n"
                f"🔍 **Análise**:\n{analise}\n\n"
                f"📋 **Dados Originais**:\n"
                f"{texto[:300]}..."
            )
            
            # Envia via bot
            await bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=resposta,
                reply_to_message_id=self.ultima_mensagem,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Falha na análise: {str(e)}", exc_info=True)
            await self.enviar_fallback(event)

    async def enviar_fallback(self, event):
        """Fallback para quando a análise falha"""
        try:
            await bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"⚠️ Mensagem recebida (análise indisponível):\n\n{event.raw_text[:300]}...",
                reply_to_message_id=self.ultima_mensagem
            )
        except Exception as e:
            logger.critical(f"⛔ Fallback falhou: {str(e)}")

    async def gerar_analise_tecnica(self, texto: str) -> str:
        """Gera análise usando IA"""
        try:
            resposta = await gerar_resposta_ia(texto)
            return resposta if resposta else "🔍 Análise não disponível"
        except Exception as e:
            logger.error(f"Erro na IA: {str(e)}")
            return "⚠️ Sistema de análise temporariamente indisponível"

    def extrair_jogo(self, texto: str) -> str:
        """Extrai o nome do jogo com regex tolerante"""
        padroes = [
            r"(?:⚽️|🏆|📌)\s*([^\n]+)",  # Prefixos comuns
            r"(?:Jogo|Partida):?\s*([^\n]+)",  # Formato "Jogo: x vs y"
            r"([A-Z][^\n]+?)\s+vs\s+([A-Z][^\n]+)(?:\n|$)"  # Formato "TimeA vs TimeB"
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1).strip()
                
        return "Jogo não identificado"

processador = ProcessadorSinais()

@client.on(events.NewMessage(chats=CHAT_ID_SINAL))
async def handler_mensagens(event):
    """Handler para mensagens do canal"""
    try:
        logger.info(f"📩 Nova mensagem (ID: {event.id})")
        
        # Palavras-chave atualizadas
        triggers = [
            "OVER 0.5 HT", "⚽️", "⏰", "ENTRADA",
            "GOL", "HT", "OVER", "SINAL", "APOSTA"
        ]
        
        if any(trigger.lower() in event.raw_text.lower() for trigger in triggers):
            logger.info("🎯 Sinal detectado - Processando...")
            
            try:
                # 1. Encaminha via sua conta pessoal
                await processador.encaminhar_mensagem(event)
                
                # 2. Envia análise via bot
                await processador.enviar_analise(event)
                
            except Exception as e:
                logger.error(f"❌ Pipeline falhou: {str(e)}")
                await processador.enviar_fallback(event)
        else:
            logger.info("🔍 Mensagem sem trigger - Ignorando")
            
    except Exception as e:
        logger.critical(f"💥 Erro no handler: {str(e)}", exc_info=True)

async def verificar_conexoes():
    """Verifica todas as conexões necessárias"""
    try:
        # Verifica conta Telethon (sua conta pessoal)
        me = await client.get_me()
        logger.info(f"👤 Conta Telethon: {me.first_name} (ID: {me.id})")
        
        # Verifica bot
        bot_info = await bot.get_me()
        logger.info(f"🤖 Bot: @{bot_info.username}")
        
        # Verifica acesso ao canal
        try:
            channel = await client.get_entity(CHAT_ID_SINAL)
            logger.info(f"📢 Canal de origem: {channel.title}")
        except Exception as e:
            logger.error(f"❌ Falha ao acessar canal: {str(e)}")
            raise
        
        # Verifica permissões do bot no grupo destino
        try:
            chat = await bot.get_chat(CHAT_ID_DESTINO)
            member = await chat.get_member(bot_info.id)
            if member.status != "administrator":
                raise PermissionError("Bot não é administrador no grupo destino")
            logger.info(f"✅ Bot é admin em: {chat.title}")
        except Exception as e:
            logger.error(f"❌ Problema com o bot: {str(e)}")
            raise
            
    except Exception as e:
        logger.critical(f"⛔ Verificação falhou: {str(e)}")
        raise

async def iniciar():
    """Inicia o sistema"""
    try:
        await client.start()
        await verificar_conexoes()
        
        logger.info(f"👂 Escutando canal: {CHAT_ID_SINAL}")
        logger.info(f"📤 Enviando para grupo: {CHAT_ID_DESTINO}")
        
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.critical(f"⛔ Falha crítica: {str(e)}", exc_info=True)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar())
    except KeyboardInterrupt:
        logger.info("⏹ Encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"💣 Erro não tratado: {str(e)}", exc_info=True)
