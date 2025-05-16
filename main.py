#!/usr/bin/env python3
import os
import re
import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient, events, types
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
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))  # Grupo de origem
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))  # Grupo de destino
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Inicialização dos clients
bot = Bot(token=BOT_TOKEN)
client = TelegramClient(
    "sessao_sinais",
    API_ID,
    API_HASH,
    system_version="4.16.30-vxCustom",
    connection_retries=5
)

class ProcessadorSinais:
    def __init__(self):
        self.ultima_mensagem = None
        self.contador = 0

    async def encaminhar_mensagem(self, event):
        """Encaminha a mensagem original para o grupo destino"""
        try:
            forwarded = await client.forward_messages(
                entity=CHAT_ID_DESTINO,
                messages=event.message
            )
            self.ultima_mensagem = forwarded.id
            logger.info(f"✅ Mensagem {event.id} encaminhada como ID {forwarded.id}")
            return forwarded
        except Exception as e:
            logger.error(f"❌ Falha ao encaminhar: {str(e)}")
            raise

    async def enviar_analise(self, event, mensagem_original):
        """Envia a análise refinada como resposta à mensagem encaminhada"""
        try:
            texto = event.raw_text
            jogo = self.extrair_jogo(texto)
            
            analise = await self.gerar_analise_tecnica(texto)
            
            resposta = (
                f"⚡️ **Análise Técnica** ⚡️\n\n"
                f"📌 **Jogo**: {jogo}\n"
                f"🔍 **Detalhes**:\n{analise}\n\n"
                f"📊 **Sinal Original**:\n"
                f"{texto[:300]}..."
            )
            
            await bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=resposta,
                reply_to_message_id=self.ultima_mensagem,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar análise: {str(e)}")
            await self.enviar_fallback(event)

    async def enviar_fallback(self, event):
        """Mensagem de fallback caso ocorra erro na análise"""
        try:
            await bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=f"⚠️ Análise automática indisponível. Mensagem original: {event.raw_text[:200]}...",
                reply_to_message_id=self.ultima_mensagem
            )
        except Exception as e:
            logger.critical(f"⛔ Falha crítica no fallback: {str(e)}")

    async def gerar_analise_tecnica(self, texto: str) -> str:
        """Gera a análise técnica usando IA"""
        try:
            prompt = (
                "Analise este sinal de aposta considerando:\n"
                "1. Probabilidade baseada nos dados\n"
                "2. Momento ideal do jogo\n"
                "3. Estatísticas apresentadas\n"
                "4. Fatores externos como clima\n\n"
                f"Dados:\n{texto}"
            )
            
            resposta = await gerar_resposta_ia(prompt)
            return resposta if resposta else "Análise não disponível no momento"
            
        except Exception as e:
            logger.error(f"Erro na análise IA: {str(e)}")
            return "⚠️ Sistema de análise temporariamente indisponível"

    def extrair_jogo(self, texto: str) -> str:
        """Extrai o nome do jogo da mensagem"""
        padrao = r"(?:⚽️|🏆|📌)\s*([^\n]+)"
        match = re.search(padrao, texto)
        return match.group(1).strip() if match else "Jogo não identificado"

processador = ProcessadorSinais()

@client.on(events.NewMessage(chats=CHAT_ID_SINAL))
async def handler_mensagens(event):
    """Processa mensagens do grupo de origem"""
    try:
        logger.info(f"📥 Nova mensagem recebida (ID: {event.id})")
        
        if not any(keyword in event.raw_text for keyword in ["OVER 0.5 HT", "⚽️", "⏰"]):
            logger.debug("Mensagem não contém palavras-chave - ignorando")
            return
            
        try:
            forwarded = await processador.encaminhar_mensagem(event)
            await processador.enviar_analise(event, forwarded)
            logger.info("✅ Processamento concluído com sucesso")
            
        except Exception as e:
            logger.error(f"❌ Erro no processamento: {str(e)}")
            await processador.enviar_fallback(event)
            
    except Exception as e:
        logger.critical(f"💥 Erro crítico no handler: {str(e)}", exc_info=True)

async def verificar_permissoes():
    """Verifica se o bot tem permissões necessárias - CORRIGIDO"""
    try:
        # Corrigido: await adicionado corretamente
        me = await bot.get_me()
        chat = await bot.get_chat(CHAT_ID_DESTINO)
        member = await chat.get_member(me.id)
        
        logger.info(f"Permissões no grupo destino: {member.status}")
        logger.debug(f"Detalhes: {member}")
        
        if member.status != "administrator":
            logger.warning("⚠️ O bot não é administrador no grupo destino!")
            return False
            
        # Verifica permissões específicas
        required_permissions = [
            'can_post_messages',
            'can_edit_messages',
            'can_delete_messages'
        ]
        
        for perm in required_permissions:
            if not getattr(member, perm, False):
                logger.warning(f"⚠️ Falta permissão: {perm}")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Erro ao verificar permissões: {str(e)}")
        return False

async def iniciar():
    """Inicia todos os serviços - VERSÃO CORRIGIDA"""
    try:
        await client.start()
        logger.info("✅ Telethon conectado")
        
        # Verificação corrigida com await
        if not await verificar_permissoes():
            logger.error("❌ Verificação de permissões falhou")
            raise RuntimeError("Permissões insuficientes no grupo destino")
        
        me = await client.get_me()
        logger.info(f"👤 Sessão iniciada como: {me.first_name} (ID: {me.id})")
        
        bot_info = await bot.get_me()
        logger.info(f"🤖 Bot Telegram pronto: @{bot_info.username}")
        
        logger.info(f"👂 Escutando mensagens no chat: {CHAT_ID_SINAL}")
        logger.info(f"📤 Enviando para o chat: {CHAT_ID_DESTINO}")
        
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.critical(f"⛔ Falha na inicialização: {str(e)}", exc_info=True)
        raise
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar())
    except KeyboardInterrupt:
        logger.info("⏹ Bot encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"💣 Erro não tratado: {str(e)}", exc_info=True)
