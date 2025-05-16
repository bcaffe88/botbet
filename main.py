#!/usr/bin/env python3
import os
import re
import aiohttp
import asyncio
import logging
from typing import Optional
from telethon import TelegramClient, events
from telethon.sessions import SQLiteSession
from telegram import Bot
from telegram.constants import ParseMode
from ia_openai import gerar_resposta_ia

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL", 0))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO", 0))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Configuração de sessão
SESSION_FILE = "sessao_sinais.session"

class SignalProcessor:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.client = TelegramClient(
            session=SQLiteSession(SESSION_FILE),
            api_id=API_ID,
            api_hash=API_HASH,
            connection_retries=5
        )
        self.last_message_id = None

    async def initialize(self):
        """Inicializa conexões"""
        try:
            await self.client.start()
            if not await self.client.is_user_authorized():
                raise ConnectionError("Falha na autenticação com a sessão existente")
            
            me = await self.client.get_me()
            logger.info(f"✅ Telethon conectado como: {me.first_name} (ID: {me.id})")
            
            bot_info = await self.bot.get_me()
            logger.info(f"🤖 Bot pronto: @{bot_info.username}")
            
            logger.info(f"👂 Monitorando canal: {CHAT_ID_SINAL}")
            logger.info(f"📤 Enviando para grupo: {CHAT_ID_DESTINO}")
            
            return True
            
        except Exception as e:
            logger.critical(f"⛔ Falha na inicialização: {str(e)}")
            return False

    async def forward_signal(self, event):
        """Encaminha mensagem para o grupo destino"""
        try:
            forwarded = await self.client.forward_messages(
                entity=CHAT_ID_DESTINO,
                messages=event.message
            )
            self.last_message_id = forwarded.id
            logger.info(f"📨 Mensagem {event.id} encaminhada")
            return forwarded
        except Exception as e:
            logger.error(f"❌ Falha ao encaminhar: {str(e)}")
            raise

    async def send_analysis(self, event):
        """Envia análise refinada ao grupo"""
        try:
            analysis = await self.generate_analysis(event.raw_text)
            
            response = (
                "🔍 <b>Análise Técnica</b>\n\n"
                f"{analysis}\n\n"
                "📋 <i>Dados Originais</i>:\n"
                f"{event.raw_text[:300]}..."
            )
            
            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=response,
                reply_to_message_id=self.last_message_id,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Falha na análise: {str(e)}")
            await self.send_fallback(event)

    async def send_fallback(self, event):
        """Mensagem simplificada caso a análise falhe"""
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"📩 Mensagem recebida:\n\n{event.raw_text[:300]}...",
                reply_to_message_id=self.last_message_id
            )
        except Exception as e:
            logger.critical(f"⛔ Fallback falhou: {str(e)}")

    async def generate_analysis(self, text: str) -> str:
        """Gera análise usando IA"""
        try:
            prompt = (
                "Analise este sinal de aposta esportiva ao vivo considerando:\n"
                "1. Probabilidade baseada nos dados\n"
                "2. Minuto ideal do jogo (15-25 minutos)\n"
                "3. Estatísticas de ataques perigosos\n"
                "4. Fatores climáticos quando relevantes\n\n"
                f"Dados:\n{text}"
            )
            
            response = await gerar_resposta_ia(prompt)
            return response if response else "🔍 Análise não disponível"
            
        except Exception as e:
            logger.error(f"Erro na IA: {str(e)}")
            return "⚠️ Análise temporariamente indisponível"

    async def run(self):
        """Executa o loop principal"""
        try:
            if not await self.initialize():
                raise RuntimeError("Inicialização falhou")

            @self.client.on(events.NewMessage(chats=CHAT_ID_SINAL))
            async def handler(event):
                try:
                    logger.info(f"📥 Nova mensagem (ID: {event.id})")
                    
                    if "OVER 0.5 HT" in event.raw_text:
                        logger.info("🎯 Sinal detectado - Processando...")
                        try:
                            await self.forward_signal(event)
                            await self.send_analysis(event)
                        except Exception as e:
                            logger.error(f"❌ Pipeline falhou: {str(e)}")
                            await self.send_fallback(event)
                    else:
                        logger.debug("Mensagem sem trigger - Ignorando")
                        
                except Exception as e:
                    logger.error(f"💥 Erro no handler: {str(e)}")

            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.critical(f"💣 Erro não tratado: {str(e)}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    processor = SignalProcessor()
    
    try:
        asyncio.run(processor.run())
    except KeyboardInterrupt:
        logger.info("⏹ Bot encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"💥 Falha crítica: {str(e)}")
