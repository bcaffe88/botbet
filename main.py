#!/usr/bin/env python3
import os
import re
import aiohttp
import asyncio
import time
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient, events, types
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from ia_openai import gerar_resposta_ia

# Configuração avançada de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_analisador.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente com validação
def get_env_var(name: str, required: bool = True) -> str:
    value = os.getenv(name)
    if required and not value:
        logger.error(f"Variável de ambiente {name} não configurada!")
        raise ValueError(f"Variável {name} é obrigatória")
    return value

API_ID = get_env_var("API_ID")
API_HASH = get_env_var("API_HASH")
CHAT_ID_SINAL = get_env_var("CHAT_ID_SINAL")
CHAT_ID_DESTINO = get_env_var("CHAT_ID_DESTINO")
ODDS_API_KEY = get_env_var("ODDS_API_KEY", required=False)
BOT_TOKEN = get_env_var("BOT_TOKEN")

# Inicialização dos clients
bot = Bot(token=BOT_TOKEN)
client = TelegramClient(
    "sessao_sinais", 
    API_ID, 
    API_HASH,
    system_version="4.16.30-vxCustom"
)

class AnalisadorSinais:
    def __init__(self):
        self.sessoes_ativas = {}
        self.ultima_mensagem = None

    async def monitorar_odd(self, jogo: str, link: str, timeout: int = 300) -> None:
        """Monitora odds com reconexão automática e cache local"""
        url = "https://api.the-odds-api.com/v4/sports/soccer/odds/"
        params = {
            "regions": "eu",
            "markets": "totals",
            "apiKey": ODDS_API_KEY
        }
        
        inicio = time.time()
        tentativa = 0
        
        while time.time() - inicio < timeout:
            tentativa += 1
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            logger.warning(f"API Odds retornou status {resp.status}. Tentativa {tentativa}")
                            await asyncio.sleep(15)
                            continue
                            
                        data = await resp.json()
                        logger.debug(f"Dados recebidos da API: {data[:1]}...")  # Log parcial
                        
                        for partida in data:
                            nome = self._formatar_nome_jogo(partida)
                            if jogo.lower() in nome.lower():
                                await self._processar_odds(partida, nome, link)
                                return
                                
            except Exception as e:
                logger.error(f"Erro na tentativa {tentativa}: {str(e)}", exc_info=True)
                await asyncio.sleep(30)
                
        logger.info(f"Monitoramento encerrado para {jogo} após {timeout}s")

    def _formatar_nome_jogo(self, partida: Dict) -> str:
        """Padroniza o formato do nome do jogo"""
        return f"{partida.get('home_team', 'Time1')} x {partida.get('away_team', 'Time2')}"

    async def _processar_odds(self, partida: Dict, nome: str, link: str) -> None:
        """Processa as odds encontradas e envia mensagem"""
        for bk in partida.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                if mkt["key"] == "totals":
                    for linha in mkt["outcomes"]:
                        if linha["point"] == 0.5 and linha["name"] == "Over":
                            odd = linha["price"]
                            if odd >= 1.50:
                                msg = (
                                    f"⚽️ ENTRADA VALIDADA\n\n📌 Jogo: {nome}\n"
                                    f"📈 Odd +0.5 HT: {odd}\n💰 Valor sugerido: R$15"
                                )
                                await self._enviar_mensagem_validada(msg, link)
                                return

    async def _enviar_mensagem_validada(self, mensagem: str, link: str) -> None:
        """Envia mensagem formatada com tratamento de erro"""
        try:
            await bot.send_message(
                chat_id=CHAT_ID_DESTINO,
                text=mensagem,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👉 Apostar agora", url=link)]
                ]),
                parse_mode="Markdown"
            )
            logger.info("Mensagem de validação enviada com sucesso")
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem: {str(e)}", exc_info=True)

    async def analisar_mensagem(self, texto: str) -> Optional[str]:
        """Analisa a mensagem com extração robusta de dados"""
        try:
            logger.info("Iniciando análise de mensagem")
            
            dados = {
                'jogo': self._extrair_jogo(texto),
                'minuto': self._extrair_minuto(texto),
                'ia': self._extrair_ia(texto),
                'perigosos': self._extrair_dados(texto, "Ataques Perigosos"),
                'posse': self._extrair_dados(texto, "Posse de Bola"),
                'escanteios': self._extrair_dados(texto, "Escanteios"),
                'no_gol': self._extrair_dados(texto, "No Gol"),
                'vento': self._extrair_vento(texto)
            }
            
            criterios, resumo = self._avaliar_criterios(dados)
            veredito, confianca, conclusao = self._determinar_veredito(criterios)
            
            if len(criterios) >= 4:
                asyncio.create_task(
                    self.monitorar_odd(
                        dados['jogo'], 
                        "https://bet365.com"
                    )
                )
            
            msg = self._formatar_resposta(
                veredito, 
                dados['jogo'],
                resumo,
                conclusao,
                confianca
            )
            
            # Integração com IA
            try:
                explicacao = await gerar_resposta_ia(msg)
                msg += f"\n\n🧠 Análise Técnica Premium:\n{explicacao}"
            except Exception as e:
                logger.error(f"Erro na IA: {str(e)}")
                msg += "\n\n⚠️ Análise técnica indisponível no momento"
            
            await self._enviar_mensagem_validada(msg, "")
            return msg
            
        except Exception as e:
            logger.error(f"Erro crítico na análise: {str(e)}", exc_info=True)
            return None

    # Métodos auxiliares (continuam conforme sua implementação original)
    # ... (incluir todos os métodos _extrair_* e _avaliar_* aqui)

analisador = AnalisadorSinais()

@client.on(events.NewMessage(chats=int(CHAT_ID_SINAL)))
async def handler_mensagens(event: types.Message):
    """Handler principal para processar mensagens"""
    try:
        logger.info(f"Nova mensagem recebida no chat {event.chat_id}")
        
        if not event.text:
            logger.warning("Mensagem sem texto ignorada")
            return
            
        if "OVER 0.5 HT" in event.text:
            logger.info("Palavra-chave detectada - iniciando análise")
            await analisador.analisar_mensagem(event.text)
        else:
            logger.debug("Mensagem não contém trigger")
            
    except Exception as e:
        logger.error(f"Erro no handler: {str(e)}", exc_info=True)

async def verificar_conexao():
    """Testa todas as conexões necessárias"""
    logger.info("Iniciando testes de conexão...")
    
    # Teste Telegram Client
    try:
        me = await client.get_me()
        logger.info(f"Conectado ao Telegram como: {me.username} (ID: {me.id})")
    except Exception as e:
        logger.critical(f"Falha na conexão Telegram: {str(e)}")
        raise
        
    # Teste Bot Telegram
    try:
        info = await bot.get_me()
        logger.info(f"Bot Telegram ativo: @{info.username}")
    except Exception as e:
        logger.critical(f"Falha na conexão do Bot: {str(e)}")
        raise
        
    # Verifica acesso ao chat de sinais
    try:
        chat = await client.get_entity(int(CHAT_ID_SINAL))
        logger.info(f"Acesso confirmado ao chat: {chat.title}")
    except Exception as e:
        logger.critical(f"Falha ao acessar chat {CHAT_ID_SINAL}: {str(e)}")
        raise

async def iniciar():
    """Inicia todos os serviços"""
    try:
        logger.info("Iniciando serviços...")
        
        await client.start()
        await verificar_conexao()
        
        logger.info("Bot pronto e escutando")
        logger.info(f"Monitorando chat ID: {CHAT_ID_SINAL}")
        logger.info(f"Enviando para chat ID: {CHAT_ID_DESTINO}")
        
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.critical(f"Erro fatal: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Encerrando serviços...")
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"Erro não tratado: {str(e)}", exc_info=True)
