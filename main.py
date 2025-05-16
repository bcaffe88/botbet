#!/usr/bin/env python3
import os
import asyncio
import logging
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
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))  # Canal de origem
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))  # Grupo de destino
BOT_TOKEN = os.getenv("BOT_TOKEN")
ARQUIVO_SESSAO = "sessao_sinais.session"

class BotSinais:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.cliente = TelegramClient(
            SQLiteSession(ARQUIVO_SESSAO),
            API_ID,
            API_HASH
        )
        self.manter_rodando = True

    async def iniciar(self):
        """Inicia todos os serviços"""
        try:
            # Conecta o Telethon
            await self.cliente.start()
            if not await self.cliente.is_user_authorized():
                raise RuntimeError("Falha na autenticação com a sessão")

            usuario = await self.cliente.get_me()
            logger.info(f"✅ Conectado como: {usuario.first_name}")

            # Verifica o bot
            info_bot = await self.bot.get_me()
            logger.info(f"🤖 Bot pronto: @{info_bot.username}")

            # Configura handler de mensagens
            self.cliente.add_event_handler(
                self.processar_mensagem,
                events.NewMessage(chats=CHAT_ID_SINAL)
            )

            logger.info(f"👂 Monitorando canal: {CHAT_ID_SINAL}")
            logger.info(f"📤 Enviando para grupo: {CHAT_ID_DESTINO}")

            # Mantém o bot ativo
            while self.manter_rodando:
                await asyncio.sleep(10)  # Verifica a cada 10 segundos

        except Exception as e:
            logger.critical(f"⛔ Erro crítico: {str(e)}")
            raise
        finally:
            await self.encerrar()

    async def encerrar(self):
        """Encerra os serviços corretamente"""
        self.manter_rodando = False
        if self.cliente.is_connected():
            await self.cliente.disconnect()
        logger.info("🛑 Bot encerrado")

    async def processar_mensagem(self, evento):
        """Processa mensagens do canal"""
        try:
            logger.info(f"📩 Mensagem recebida (ID: {evento.id})")

            # Verifica se é um sinal válido
            palavras_trigger = [
                "OVER 0.5 HT", "⚽️", "⏰", "ENTRADA",
                "GOL", "HT", "OVER", "SINAL", "APOSTA"
            ]

            if any(trigger in evento.raw_text for trigger in palavras_trigger):
                logger.info("🎯 Sinal detectado - Processando...")
                
                try:
                    # 1. Encaminha mensagem original
                    mensagem_encaminhada = await self.cliente.forward_messages(
                        entity=CHAT_ID_DESTINO,
                        messages=evento.message
                    )

                    # 2. Envia análise técnica
                    await self.enviar_analise(
                        texto=evento.raw_text,
                        id_mensagem=mensagem_encaminhada.id
                    )

                except Exception as e:
                    logger.error(f"❌ Erro no processamento: {str(e)}")
                    await self.enviar_fallback(evento)

        except Exception as e:
            logger.error(f"💥 Erro no handler: {str(e)}")

    async def enviar_analise(self, texto, id_mensagem):
        """Envia análise técnica ao grupo"""
        try:
            analise = await gerar_resposta_ia(
                f"Analise este sinal de aposta considerando:\n"
                f"1. Probabilidade baseada nos dados\n"
                f"2. Momento ideal do jogo\n"
                f"3. Estatísticas apresentadas\n\n"
                f"Dados:\n{texto[:1000]}"
            ) or "Análise não disponível no momento"

            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"🔍 <b>Análise Técnica</b>\n\n{analise}",
                reply_to_message_id=id_mensagem,
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"❌ Falha na análise: {str(e)}")
            await self.enviar_fallback_simples(texto, id_mensagem)

    async def enviar_fallback(self, evento):
        """Mensagem de fallback para erros no processamento"""
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"⚠️ Mensagem recebida (análise falhou):\n\n{evento.raw_text[:300]}...",
                reply_to_message_id=self.ultima_mensagem
            )
        except Exception as e:
            logger.critical(f"⛔ Fallback falhou: {str(e)}")

    async def enviar_fallback_simples(self, texto, id_mensagem):
        """Fallback simplificado"""
        await self.bot.send_message(
            chat_id=CHAT_ID_DESTINO,
            text=f"📩 Mensagem original:\n\n{texto[:300]}...",
            reply_to_message_id=id_mensagem
        )

if __name__ == "__main__":
    bot = BotSinais()
    
    try:
        asyncio.run(bot.iniciar())
    except KeyboardInterrupt:
        logger.info("⏹ Encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"💥 Falha crítica: {str(e)}")
