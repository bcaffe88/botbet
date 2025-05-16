#!/usr/bin/env python3
import os
import asyncio
import logging
import signal
from telethon import TelegramClient, events
from telethon.sessions import SQLiteSession
from telegram import Bot
from telegram.constants import ParseMode
from ia_openai import gerar_resposta_ia

# Configuração
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
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_FILE = "sessao_sinais.session"

class BotSinais:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.client = TelegramClient(
            SQLiteSession(SESSION_FILE),
            API_ID,
            API_HASH
        )
        self.loop = asyncio.get_event_loop()
        self.should_run = True

        # Configura handlers de sinal
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

    def handle_signal(self, signum, frame):
        """Manipula sinais de desligamento"""
        logger.info(f"Recebido sinal {signum}, encerrando...")
        self.should_run = False

    async def start(self):
        """Inicia o bot"""
        try:
            await self.client.start()
            if not await self.client.is_user_authorized():
                raise RuntimeError("Autenticação falhou")

            me = await self.client.get_me()
            logger.info(f"✅ Conectado como: {me.first_name}")

            bot_info = await self.bot.get_me()
            logger.info(f"🤖 Bot pronto: @{bot_info.username}")

            self.client.add_event_handler(
                self.handle_message,
                events.NewMessage(chats=CHAT_ID_SINAL)
            )

            logger.info(f"👂 Monitorando canal: {CHAT_ID_SINAL}")
            logger.info(f"📤 Enviando para grupo: {CHAT_ID_DESTINO}")

            # Mantém o bot ativo
            while self.should_run:
                await asyncio.sleep(1)

        except Exception as e:
            logger.critical(f"⛔ Erro: {str(e)}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Encerra conexões"""
        if self.client.is_connected():
            await self.client.disconnect()
        logger.info("🛑 Bot encerrado")

    async def handle_message(self, event):
        """Processa mensagens recebidas"""
        try:
            logger.info(f"📩 Nova mensagem (ID: {event.id})")

            triggers = ["OVER 0.5 HT", "⚽️", "⏰", "ENTRADA", "GOL", "HT", "OVER"]
            if any(t in event.raw_text for t in triggers):
                logger.info("🎯 Sinal detectado")
                forwarded = await self.client.forward_messages(
                    CHAT_ID_DESTINO,
                    event.message
                )
                await self.send_analysis(event.raw_text, forwarded.id)

        except Exception as e:
            logger.error(f"❌ Erro: {str(e)}")

    async def send_analysis(self, text, reply_to_id):
        """Envia análise técnica"""
        try:
            analysis = await gerar_resposta_ia(f"Analise este sinal:\n\n{text[:1000]}")
            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"🔍 <b>Análise Técnica</b>\n\n{analysis or 'Sem análise disponível'}",
                reply_to_message_id=reply_to_id,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"❌ Falha na análise: {str(e)}")
            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"📩 Mensagem original:\n\n{text[:300]}...",
                reply_to_message_id=reply_to_id
            )

async def main():
    bot = BotSinais()
    await bot.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
