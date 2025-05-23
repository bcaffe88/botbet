import os
import re
import unicodedata
import asyncio
import logging
from datetime import datetime
from difflib import SequenceMatcher
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import aiohttp
from estatisticas_time import resumo_estatistico

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validar e configurar variáveis de ambiente
required_vars = ["BOT_TOKEN", "API_ID", "API_HASH", "CHAT_ID_SINAL", "CHAT_ID_DESTINO", "FOOTBALL_API_KEY"]
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    raise ValueError(f"Variáveis de ambiente obrigatórias não encontradas: {', '.join(missing_vars)}")

try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
    CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
except ValueError as e:
    raise ValueError(f"Erro ao converter variáveis numéricas: {e}")

# Inicializar bot
bot = Bot(token=BOT_TOKEN)

# UTILITÁRIOS
def normalizar(texto):
    """Normaliza texto removendo acentos e convertendo para minúsculas"""
    if not texto:
        return ""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    """Calcula similaridade entre duas strings"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

# API-FOOTBALL - Verifica gol no HT
async def verificar_gol_ht(nome_jogo):
    """Verifica se houve gol no primeiro tempo através da API Football"""
    if not nome_jogo or not FOOTBALL_API_KEY:
        logger.warning("Nome do jogo ou API key não fornecidos")
        return "⏳ NÃO LOCALIZADO"
        
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY,
        "Accept": "application/json"
    }
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API Football: Status {resp.status}")
                    return "⏳ ERRO NA API"
                    
                data = await resp.json()
                jogos = data.get("response", [])

                logger.info(f"📅 {len(jogos)} jogos encontrados na API-Football em {data_hoje}")
                
                for item in jogos:
                    try:
                        teams = item.get("teams", {})
                        score = item.get("score", {})
                        halftime = score.get("halftime", {})

                        casa = teams.get("home", {}).get("name", "")
                        fora = teams.get("away", {}).get("name", "")
                        
                        if not casa or not fora:
                            continue
                            
                        nome_match = f"{casa} x {fora}"
                        logger.debug(f"- {nome_match}")

                        if similaridade(nome_jogo, nome_match) > 0.75:
                            gols_casa_ht = halftime.get("home") or 0
                            gols_fora_ht = halftime.get("away") or 0
                            gols_ht = gols_casa_ht + gols_fora_ht
                            
                            logger.info(f"🔍 Match encontrado: {nome_jogo} ≈ {nome_match} | Gols HT: {gols_ht}")
                            return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
                            
                    except (KeyError, TypeError) as e:
                        logger.warning(f"Erro ao processar jogo: {e}")
                        continue
                        
    except asyncio.TimeoutError:
        logger.error("Timeout ao consultar API-Football")
        return "⏳ TIMEOUT"
    except Exception as e:
        logger.error(f"Erro ao consultar API-Football: {e}")
        return "⏳ ERRO"

    return "⏳ NÃO LOCALIZADO"

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de inicialização do bot"""
    try:
        await update.message.reply_text("🤖 Bot de sinais refinados ativo!")
        logger.info(f"Comando /start executado por {update.effective_user.username}")
    except Exception as e:
        logger.error(f"Erro no comando /start: {e}")

# Tarefa de veredito após 35 minutos (1500 segundos)
async def tarefa_veredito(jogo, msg_original):
    """Executa verificação do resultado após 25 minutos"""
    try:
        logger.info(f"⏰ Aguardando 35 minutos para verificar resultado de: {jogo}")
        await asyncio.sleep(2100)  # 25 minutos = 1500 segundos
        
        resultado = await verificar_gol_ht(jogo)
        logger.info(f"📊 Result para {jogo}: {resultado}")

        if resultado == "✅ BATEU":
            resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅"
        elif resultado == "❌ NÃO BATEU":
            resultado_final = "R E D ❌"
        else:
            resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"

        novo_texto = f"""{msg_original.text}

─────────────────────
{resultado_final}"""

        await bot.edit_message_text(
            chat_id=CHAT_ID_DESTINO,
            message_id=msg_original.message_id,
            text=novo_texto
        )
        logger.info(f"✅ Veredito atualizado para: {jogo}")
        
    except Exception as e:
        logger.error(f"Erro na tarefa de veredito: {e}")

# Análise do sinal
async def analisar(texto):
    """Analisa o sinal recebido e decide se deve enviar entrada"""
    logger.info("📊 Iniciando análise do sinal")
    
    if not texto:
        logger.warning("Texto vazio recebido para análise")
        return
        
    try:
        # Extrair informações do sinal
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        logger.info(f"📌 Jogo detectado: {jogo}")

        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None

        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
        ia = float(ia_match.group(1)) if ia_match else None

        match_perigosos = re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)
        perigosos = list(map(int, match_perigosos[0])) if match_perigosos else [0, 0]

        match_posse = re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)
        posse = list(map(int, match_posse[0])) if match_posse else [0, 0]

        match_escanteios = re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)
        escanteios = list(map(int, match_escanteios[0])) if match_escanteios else [0, 0]

        match_no_gol = re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)
        no_gol = list(map(int, match_no_gol[0])) if match_no_gol else [0, 0]

        match_chutes = re.findall(r"Total:\s*(\d+)/(\d+)", texto)
        chutes = list(map(int, match_chutes[0])) if match_chutes else [0, 0]

        vento_match = re.search(r"🌬️\s*([\d.]+)\s*m/s", texto)
        vento = float(vento_match.group(1)) if vento_match else None

        # Análise dos critérios
        criterios = []
        resumo = []
        pontos = 0

        # Critério IA
        if ia and ia >= 75:
            criterios.append("IA favorável")
            pontos += 2
        resumo.append(f"{ia}%" if ia else "N/A")

        # Critério minuto
        if minuto and 16 <= minuto <= 22:
            criterios.append("Minuto ideal")
            pontos += 1

        # Critério ataques perigosos
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            criterios.append("Ataques perigosos")
            pontos += 2

        # Critério finalizações no gol
        if sum(no_gol) >= 1:
            criterios.append("Finalizações no gol")
            pontos += 2

        # Critério escanteios
        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
            pontos += 1

        # Critério vento
        if vento and vento < 15:
            criterios.append("Vento favorável")
            pontos += 1

        # Critério chutes totais
        if sum(chutes) >= 4:
            criterios.append("Chutes suficientes")
            pontos += 1

        # Critério posse dominante
        if posse[0] >= 60 or posse[1] >= 60:
            criterios.append("Posse dominante")
            pontos += 1

        logger.info(f"📈 Pontuação: {pontos}/10 | Critérios atendidos: {len(criterios)}")
        logger.info(f"📋 Critérios: {', '.join(criterios) if criterios else 'Nenhum'}")

        # Decisão final
        if pontos >= 7:
            veredito = "ENTRAR ✅"
            conclusao = "OVER 0.5 HT"

            msg = f"""⚽️ {🏟️ {jogo}
🤖 OVERBOT VIP
{chr(10).join(resumo)}
▶️ ENTRADA: {conclusao}"""

# 🔍 Estatísticas do confronto
try:
    nomes_times = jogo.split(" x ")
    if len(nomes_times) == 2:
        resumo_stats = await resumo_estatistico(nomes_times[0], nomes_times[1])
    else:
        resumo_stats = "📊 Estatísticas indisponíveis para o confronto"
except Exception as e:
    logger.error(f"Erro ao gerar estatísticas: {e}")
    resumo_stats = "⚠️ Erro ao obter dados históricos"

msg += f"\n\n{resumo_stats}"

            try:
                msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
                logger.info("✅ Sinal de entrada enviado com sucesso")
                
                # Agendar verificação do resultado
                asyncio.create_task(tarefa_veredito(jogo, msg_enviada))
                
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem: {e}")
        else:
            logger.info(f"❌ Critérios insuficientes ({pontos}/7). Sinal não enviado.")

    except Exception as e:
        logger.error(f"Erro na análise do sinal: {e}")

# MONITOR TELETHON
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    """Monitora mensagens do canal de sinais"""
    try:
        logger.debug(f"📨 Mensagem recebida de {event.chat_id}")
        
        if event.chat_id == CHAT_ID_SINAL and event.message.message:
            conteudo = event.message.message
            
            if "OVER 0.5 HT" in conteudo:
                logger.info("✅ Sinal OVER 0.5 HT detectado, enviando para análise")
                await analisar(conteudo)
            else:
                logger.debug("⚠️ Mensagem não contém sinal OVER 0.5 HT")
        else:
            logger.debug("⚠️ Mensagem de chat incorreto ou vazia")
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

# INICIALIZAÇÃO
async def main():
    """Função principal para iniciar ambos os serviços"""
    app = None
    try:
        logger.info("🚀 Iniciando Bot de Sinais")
        logger.info(f"📍 Monitorando chat: {CHAT_ID_SINAL}")
        logger.info(f"📍 Enviando para: {CHAT_ID_DESTINO}")
        
        # Inicializar aplicação Telegram Bot
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        
        # Inicializar a aplicação do bot
        await app.initialize()
        await app.start()
        logger.info("✅ Bot Telegram inicializado")
        
        # Inicializar cliente Telethon
        await client.start()
        me = await client.get_me()
        logger.info(f"✅ Telethon conectado como: {me.first_name} (@{me.username})")
        
        # Iniciar o updater do bot em background
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Bot Telegram polling iniciado")
        
        # Manter o cliente Telethon rodando
        logger.info("🔄 Serviços rodando... Pressione Ctrl+C para parar")
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("🛑 Aplicação interrompida pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
    finally:
        # Cleanup adequado
        try:
            if app and app.updater.running:
                await app.updater.stop()
                logger.info("📴 Bot polling parado")
            
            if app:
                await app.stop()
                await app.shutdown()
                logger.info("📴 Bot Telegram encerrado")
                
            if client.is_connected():
                await client.disconnect()
                logger.info("📴 Telethon desconectado")
        except Exception as cleanup_error:
            logger.error(f"Erro no cleanup: {cleanup_error}")
        
        logger.info("👋 Aplicação encerrada")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro na inicialização: {e}")
