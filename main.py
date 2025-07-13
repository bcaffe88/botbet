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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validar e configurar variáveis de ambiente UNIFICADAS
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

# Inicializar bot (um único bot para tudo)
bot = Bot(token=BOT_TOKEN)

# --- Funções Utilitárias Comuns ---
def normalizar(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    if not a or not b: return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

async def buscar_fixture_id(nome_jogo: str) -> int | None:
    """Busca o fixture_id de um jogo pelo nome na API-Football."""
    if not nome_jogo or not FOOTBALL_API_KEY:
        return None

    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"
    fixture_id = None
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url_fixtures, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"Erro ao buscar fixtures: Status {resp.status}")
                    return None
                
                data = await resp.json()
                jogos = data.get("response", [])
                
                maior_similaridade = 0.75
                for item in jogos:
                    teams = item.get("teams", {})
                    casa = teams.get("home", {}).get("name", "")
                    fora = teams.get("away", {}).get("name", "")
                    nome_match_api = f"{casa} x {fora}"
                    
                    sim = similaridade(nome_jogo, nome_match_api)
                    if sim > maior_similaridade:
                        maior_similaridade = sim
                        fixture_id = item.get("fixture", {}).get("id")
                
                if fixture_id:
                    logger.info(f"🔍 Fixture encontrado para '{nome_jogo}': ID {fixture_id} (Similaridade: {maior_similaridade:.2f})")
                else:
                    logger.warning(f"Fixture não localizado para '{nome_jogo}'")
    except Exception as e:
        logger.error(f"Erro em buscar_fixture_id: {e}")
        return None
        
    return fixture_id

# --- Funções do Bot 1 (Análise Climática) ---

def analisar_clima(texto):
    """Analisa condições climáticas individualmente para maior robustez e retorna pontuação."""
    pontos_clima = 0
    criterios_clima = []
    
    logger.info("🌤️ Iniciando análise climática...")
    try:
        temp_match = re.search(r"🌡️\s*([\d.]+)\s*°C", texto)
        nuvens_match = re.search(r"☁️\s*([\d.]+)%", texto)
        umidade_match = re.search(r"💧\s*([\d.]+)%", texto)
        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)

        temperatura = float(temp_match.group(1)) if temp_match else None
        nebulosidade = float(nuvens_match.group(1)) if nuvens_match else None
        umidade = float(umidade_match.group(1)) if umidade_match else None
        vento = float(vento_match.group(1)) if vento_match else None
        
        log_clima = []
        if temperatura is not None:
            if 18 <= temperatura <= 28:
                pontos_clima += 1
                criterios_clima.append("Temperatura ideal")
            log_clima.append(f"Temperatura: {temperatura}°C → {'✅' if 18 <= temperatura <= 28 else '❌'}")
        if nebulosidade is not None:
            if 20 <= nebulosidade <= 70:
                pontos_clima += 1
                criterios_clima.append("Nebulosidade ideal")
            log_clima.append(f"Nebulosidade: {nebulosidade}% → {'✅' if 20 <= nebulosidade <= 70 else '❌'}")
        if umidade is not None:
            if 50 <= umidade <= 75:
                pontos_clima += 1
                criterios_clima.append("Umidade ideal")
            log_clima.append(f"Umidade: {umidade}% → {'✅' if 50 <= umidade <= 75 else '❌'}")
        if vento is not None:
            if vento <= 7:
                pontos_clima += 1
                criterios_clima.append("Vento ótimo")
            elif 7 < vento <= 10:
                pontos_clima += 0.5
                criterios_clima.append("Vento moderado")
            log_clima.append(f"Vento: {vento} m/s → {'✅' if vento <= 7 else '⚠️' if vento <= 10 else '❌'}")
        logger.info(f"🌤️ Detalhes Climáticos Extraídos: {' | '.join(log_clima)}")
    except Exception as e:
        logger.error(f"Erro na análise climática: {e}")

    if pontos_clima >= 3.5: status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2: status_clima = "🟡 NEUTRO"
    else: status_clima = "🔴 DESFAVORÁVEL"
    logger.info(f"🌤️ Pontuação Climática Final: {pontos_clima}/4 - {status_clima}")
    return pontos_clima, criterios_clima, status_clima

async def buscar_odd_ht(nome_jogo: str) -> (str, int | None):
    """Busca o fixture_id e a odd para Over 0.5 HT de um jogo."""
    odd_ht = "N/D"
    fixture_id = await buscar_fixture_id(nome_jogo)

    if not fixture_id:
        return "N/L", None

    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url_odds = "https://v3.football.api-sports.io/odds"
    params = {"fixture": str(fixture_id), "market": "145", "bookmaker": "8"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                if resp_odds.status == 200:
                    data_odds = await resp_odds.json()
                    if data_odds.get('results', 0) > 0 and data_odds.get('response'):
                        bets = data_odds['response'][0].get('bookmakers', [{}])[0].get('bets', [])
                        if bets and bets[0].get('name') == 'Over/Under First Half':
                             for value in bets[0].get('values', []):
                                if value.get('value') == 'Over 0.5':
                                    odd_ht = value.get('odd', 'N/D')
                                    logger.info(f"📊 Odd encontrada para Over 0.5 HT: {odd_ht}")
                                    break
                else:
                    logger.error(f"Erro ao buscar odds: Status {resp_odds.status}")
                    return "API_ERR_ODD", fixture_id
    except Exception as e:
        logger.error(f"Erro em buscar_odd_ht: {e}")
        return "ERRO", fixture_id
    return odd_ht, fixture_id

async def tarefa_veredito_por_id(fixture_id, msg_original):
    """Executa verificação do resultado (Over 0.5 HT) após 35 minutos usando o ID."""
    try:
        logger.info(f"⏰ Aguardando 35 minutos para veredito (0.5 HT) do fixture ID: {fixture_id}")
        await asyncio.sleep(2100)
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        resultado = "⏳ RESULTADO NÃO LOCALIZADO"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]
                        gols_casa = fixture.get('score', {}).get('halftime', {}).get('home')
                        gols_fora = fixture.get('score', {}).get('halftime', {}).get('away')
                        gols_ht = (gols_casa or 0) + (gols_fora or 0)
                        resultado = "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
        resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if resultado == "✅ BATEU" else "R E D ❌" if resultado == "❌ NÃO BATEU" else resultado
        novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
        await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode='Markdown')
        logger.info(f"✅ Veredito (0.5 HT) atualizado para o fixture ID: {fixture_id}")
    except Exception as e:
        logger.error(f"Erro na tarefa de veredito (0.5 HT): {e}")

async def analisar(texto):
    """Função de análise principal completa para sinais 'Over 0.5 HT'."""
    logger.info("📊 Iniciando análise do sinal 'Over 0.5 HT'")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        logger.info(f"📌 Jogo detectado: {jogo}")

        odd_ht, fixture_id = await buscar_odd_ht(jogo)

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

        pontos_clima, criterios_clima, status_clima = analisar_clima(texto)
        
        criterios_tecnicos = []
        pontos_tecnicos = 0
        if ia and ia >= 70: criterios_tecnicos.append("IA favorável"); pontos_tecnicos += 2
        if minuto and 16 <= minuto <= 22: criterios_tecnicos.append("Minuto ideal"); pontos_tecnicos += 1
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7: criterios_tecnicos.append("Ataques perigosos"); pontos_tecnicos += 2
        if sum(no_gol) >= 1: criterios_tecnicos.append("Finalizações no gol"); pontos_tecnicos += 2
        if sum(escanteios) >= 2: criterios_tecnicos.append("Escanteios"); pontos_tecnicos += 1
        if sum(chutes) >= 4: criterios_tecnicos.append("Chutes suficientes"); pontos_tecnicos += 1
        if posse[0] >= 60 or posse[1] >= 60: criterios_tecnicos.append("Posse dominante"); pontos_tecnicos += 1
        
        pontos_total = pontos_tecnicos + pontos_clima
        max_pontos_total = 14
        limite_minimo = 9.0
        
        condicao1 = pontos_total >= limite_minimo
        condicao2 = pontos_tecnicos >= 7 and pontos_clima >= 2
        condicao3 = pontos_tecnicos >= 8 and pontos_clima >= 1.5
        deve_entrar = condicao1 or condicao2 or condicao3

        logger.info(f"📈 Pontuação Técnica: {pontos_tecnicos}/10 | 🌤️ Pontuação Climática: {pontos_clima}/4 | 🎯 Pontuação Total: {pontos_total}/{max_pontos_total}")

        if deve_entrar:
            if pontos_total >= 12: confianca = "MUITO ALTA 🔥 STAKE 1%"
            elif pontos_total >= 10: confianca = "ALTA ✅ STAKE 0.75%"
            elif pontos_clima >= 3: confianca = "MÉDIA-ALTA ⚡ STAKE 0.5%"
            else: confianca = "MÉDIA ⚠️ STAKE 0.25%"
            
            veredito = f"CONFIANÇA: {confianca}"
            resumo_clima = f" {status_clima} ({pontos_clima}/4pts)"
            resumo_tecnico = f" {pontos_tecnicos}/10pts"
            
            msg = f"""⚽️ {veredito}
🏟️ {jogo}
🤖 OVERBOT ANÁLISE:
⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} 
🌤️ CLIMA: {resumo_clima}
📊 ODD ATUAL: *{odd_ht}*
▶️ ENTRADA: OVER 0.5 HT"""
            
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
            logger.info(f"✅ Sinal 'Over 0.5 HT' enviado para: {jogo}")
            if fixture_id:
                asyncio.create_task(tarefa_veredito_por_id(fixture_id, msg_enviada))
        else:
            logger.info(f"❌ Critérios insuficientes para 'Over 0.5 HT' em {jogo}.")
    except Exception as e:
        logger.error(f"Erro na análise principal: {e}")

# --- Funções do Bot 2 ((CT) Over Gol) ---

async def verificar_resultado_final_ct(fixture_id, msg_original, goal_line):
    """Verifica o resultado final (Over X.5) de um jogo após 45 minutos."""
    try:
        logger.info(f"⏰ Aguardando 45 minutos para veredito (CT Over {goal_line}) do fixture ID: {fixture_id}")
        await asyncio.sleep(2700)
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        resultado = "⏳ RESULTADO NÃO LOCALIZADO"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]
                        gols_casa = fixture.get('score', {}).get('fulltime', {}).get('home')
                        gols_fora = fixture.get('score', {}).get('fulltime', {}).get('away')
                        if gols_casa is not None and gols_fora is not None:
                            total_gols = gols_casa + gols_fora
                            logger.info(f"📊 Veredito para {fixture_id}: Total de Gols={total_gols}, Linha > {goal_line}")
                            resultado = "✅ BATEU" if total_gols > goal_line else "❌ NÃO BATEU"
        resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if resultado == "✅ BATEU" else "R E D ❌" if resultado == "❌ NÃO BATEU" else resultado
        novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
        await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto)
        logger.info(f"✅ Veredito (CT) atualizado para o fixture ID: {fixture_id}")
    except Exception as e:
        logger.error(f"Erro na tarefa de veredito (CT): {e}")

async def processar_sinal_ct(texto_original):
    """Extrai, formata e encaminha o sinal (CT) Over Gol."""
    logger.info("(CT) Over Gol: Iniciando processamento do sinal.")
    try:
        evento_match = re.search(r"Evento:\s*(.+)", texto_original)
        selecao_match = re.search(r"Seleção:\s*(.+?)\s*\|", texto_original)
        
        if not evento_match or not selecao_match:
            logger.warning("Sinal (CT) sem 'Evento' ou 'Seleção'. Abortando.")
            return

        evento = evento_match.group(1).strip()
        selecao_texto = selecao_match.group(1).strip()

        # Extração dinâmica da linha de gol
        goal_line_match = re.search(r"([\d.]+)", selecao_texto)
        if not goal_line_match:
            logger.warning(f"Não foi possível extrair a linha de gol da seleção: '{selecao_texto}'. Abortando.")
            return
        goal_line = float(goal_line_match.group(1))

        # Extração dos outros campos (são opcionais na formatação)
        competicao_match = re.search(r"Competição:\s*(.+)", texto_original)
        mercado_match = re.search(r"Mercado:\s*(.+?)\s*\|", texto_original)
        stake_match = re.search(r"Stake:\s*(.+)", texto_original)
        odd_match = re.search(r"Odd:\s*(.+)", texto_original)
        tipo_match = re.search(r"Tipo:\s*(.+)", texto_original)
        estrategia_match = re.search(r"Estratégia:\s*(.+)", texto_original)

        msg_formatada = f"""ANÁLISE OVERBOT VIP CT
Evento: {evento}
Competição: {competicao_match.group(1).strip() if competicao_match else 'N/A'}

Mercado: {mercado_match.group(1).strip() if mercado_match else 'N/A'}
Seleção: {selecao_texto}
Stake: {stake_match.group(1).strip() if stake_match else 'N/A'}
Odd: {odd_match.group(1).strip() if odd_match else 'N/A'}
Tipo: {tipo_match.group(1).strip() if tipo_match else 'N/A'}

Estratégia: {estrategia_match.group(1).strip() if estrategia_match else 'N/A'}"""

        msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg_formatada)
        logger.info(f"✅ Sinal (CT) enviado para o canal de destino: {evento}")
        
        fixture_id = await buscar_fixture_id(evento)
        if fixture_id:
            asyncio.create_task(verificar_resultado_final_ct(fixture_id, msg_enviada, goal_line))
        else:
            logger.warning(f"Não foi possível agendar o veredito para '{evento}' pois o fixture ID não foi encontrado.")
    except Exception as e:
        logger.error(f"Erro ao processar sinal (CT): {e}")

# --- ROTEADOR E INICIALIZAÇÃO ---

client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHAT_ID_SINAL))
async def roteador_de_sinais(event):
    """Monitora o canal e direciona a mensagem para a função correta."""
    try:
        conteudo = event.message.message
        if not conteudo:
            return

        # Rota para o sinal de análise complexa (Over 0.5 HT)
        if "OVER 0.5 HT" in conteudo and "Inteligência Artificial" in conteudo:
            logger.info("Sinal 'OVER 0.5 HT' detectado. Roteando para análise principal.")
            await analisar(conteudo)
            
        # Rota para o sinal '(CT) Over Gol'
        elif "Estratégia: (CT) Over Gol" in conteudo:
            logger.info("Sinal '(CT) Over Gol' detectado. Roteando para processador CT.")
            await processar_sinal_ct(conteudo)
            
    except Exception as e:
        logger.error(f"Erro no roteador de sinais: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de inicialização do bot para verificação."""
    await update.message.reply_text("🤖 Bot Unificado de Sinais ativo e escutando!")

async def main():
    """Função principal para iniciar todos os serviços."""
    try:
        logger.info("🚀 Iniciando Bot Unificado de Sinais")
        logger.info(f"📍 Monitorando chat: {CHAT_ID_SINAL}")
        logger.info(f"📍 Enviando para: {CHAT_ID_DESTINO}")
        
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Bot do Telegram (para comandos) inicializado")

        await client.start()
        me = await client.get_me()
        logger.info(f"✅ Telethon conectado como: {me.first_name} (@{me.username})")

        logger.info("🔄 Bot Unificado rodando... Pressione Ctrl+C para parar")
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("🛑 Aplicação interrompida pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
    finally:
        if 'app' in locals() and app.updater.running:
            await app.updater.stop()
            logger.info("📴 Bot polling parado")
        if 'app' in locals():
            await app.shutdown()
            logger.info("📴 Bot Telegram encerrado")
        if client.is_connected():
            await client.disconnect()
            logger.info("📴 Telethon desconectado")
        logger.info("👋 Aplicação encerrada")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Interrompido pelo usuário")
