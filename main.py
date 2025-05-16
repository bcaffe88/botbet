#!/usr/bin/env python3
import os
import asyncio
import logging
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
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))  # Canal de origem
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))  # Grupo de destino
BOT_TOKEN = os.getenv("BOT_TOKEN")
ARQUIVO_SESSAO = "sessao_sinais.session"

class BotDeSinais:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.cliente = TelegramClient(
            SQLiteSession(ARQUIVO_SESSAO),
            API_ID,
            API_HASH
        )
        self.rodando = True

    async def iniciar_servicos(self):
        """Inicializa todos os serviços"""
        try:
            # Conecta o Telethon (sua conta pessoal)
            await self.cliente.start()
            if not await self.cliente.is_user_authorized():
                raise RuntimeError("Autenticação do Telethon falhou")

            usuario = await self.cliente.get_me()
            logger.info(f"✅ Telethon conectado como: {usuario.first_name}")

            # Verifica o bot
            info_bot = await self.bot.get_me()
            logger.info(f"🤖 Bot pronto: @{info_bot.username}")

            # Configura o handler de mensagens
            self.cliente.add_event_handler(
                self.processar_mensagem,
                events.NewMessage(chats=CHAT_ID_SINAL)
            )

            logger.info(f"👂 Monitorando canal: {CHAT_ID_SINAL}")
            logger.info(f"📤 Enviando para grupo: {CHAT_ID_DESTINO}")

            # Mantém o bot em execução
            while self.rodando:
                await asyncio.sleep(1)

        except Exception as e:
            logger.critical(f"⛔ Falha na inicialização: {str(e)}")
            raise
        finally:
            await self.parar_servicos()

    async def parar_servicos(self):
        """Desligamento adequado"""
        self.rodando = False
        if self.cliente.is_connected():
            await self.cliente.disconnect()
        logger.info("🛑 Serviços encerrados")

    async def processar_mensagem(self, evento):
        """Processa mensagens recebidas"""
        try:
            logger.info(f"📩 Nova mensagem (ID: {evento.id})")

            # Palavras-chave para identificar sinais
            palavras_chave = [
                "OVER 0.5 HT", "⚽️", "⏰", "ENTRADA",
                "GOL", "HT", "OVER", "SINAL", "APOSTA"
            ]

            if any(palavra in evento.raw_text for palavra in palavras_chave):
                logger.info("🎯 Sinal detectado - Processando...")
                
                # Encaminha a mensagem original
                mensagem_encaminhada = await self.cliente.forward_messages(
                    CHAT_ID_DESTINO,
                    evento.message
                )
                
                # Envia análise
                await self.enviar_analise_tecnica(
                    evento.raw_text,
                    mensagem_encaminhada.id
                )

        except Exception as e:
            logger.error(f"❌ Falha no processamento: {str(e)}")

    async def enviar_analise_tecnica(self, texto, id_resposta):
        """Gera e envia análise técnica"""
        try:
            analise = await gerar_resposta_ia(
                f"Analise este sinal de aposta:\n\n{texto[:1000]}"
            ) or "Análise indisponível"

            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"🔍 <b>Análise Técnica</b>\n\n{analise}",
                reply_to_message_id=id_resposta,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"❌ Falha na análise: {str(e)}")
            # Mensagem de fallback
            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"📩 Mensagem original:\n\n{texto[:300]}...",
                reply_to_message_id=id_resposta
            )

if __name__ == "__main__":
    bot = BotDeSinais()
    
    try:
        asyncio.run(bot.iniciar_servicos())
    except KeyboardInterrupt:
        logger.info("⏹ Encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"💥 Falha crítica: {str(e)}")
