import os
import re
import unicodedata
import asyncio
from typing import NamedTuple
from zoneinfo import ZoneInfo
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient
from telethon.sessions import StringSession
import aiohttp
import traceback
from keep_alive import keep_alive
from estatisticas_time import (
    resumo_estatistico,
    salvar_fixture_pendente,
    atualizar_fixture_resultado,
    obter_metricas_historicas,
    calcular_bonus_historico,
    metric,
    metrics_snapshot,
    rotular_odd,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validar e configurar variáveis de ambiente
required_vars = ["BOT_TOKEN", "API_ID", "API_HASH", "CHAT_ID_SINAL", "CHAT_ID_DESTINO", "FOOTBALL_API_KEY", "TELEGRAM_SESSION"]
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
    TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION")
except ValueError as e:
    raise ValueError(f"Erro ao converter variáveis numéricas: {e}")

# Inicializar bot
bot = Bot(token=BOT_TOKEN)

class OddResultado(NamedTuple):
    valor: str
    origem: str

ALTA_STAKE = "0.75%"
MUITO_ALTA_STAKE = "1%"
VERY_HIGH_CONFIDENCE_THRESHOLD = 12
OPERATING_START_HOUR = 8   # 08:00 local time
OPERATING_END_HOUR = 0     # 00:00 local time (next day boundary)
OPERATING_TZ = ZoneInfo("America/Sao_Paulo")
HIST_BONUS_HIGH = float(os.getenv("HIST_BONUS_HIGH", "0.65"))
HIST_BONUS_MED = float(os.getenv("HIST_BONUS_MED", "0.50"))
HIST_PENALTY_RED = float(os.getenv("HIST_PENALTY_RED", "0.50"))
CONFIDENCE_MAP = {
    "ALTA": f"ALTA ✅ STAKE {ALTA_STAKE}",
    "MUITO ALTA": f"MUITO ALTA ✅✅ STAKE {MUITO_ALTA_STAKE}"
}

def dentro_janela_operacao(hora: int) -> bool:
    if OPERATING_START_HOUR < OPERATING_END_HOUR:
        return OPERATING_START_HOUR <= hora < OPERATING_END_HOUR
    return hora >= OPERATING_START_HOUR or hora < OPERATING_END_HOUR

# --- Funções Utilitárias ---
def normalizar(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    if not a or not b: return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

def extrair_times(jogo: str) -> list[str]:
    try:
        partes = re.split(r"\s*(?:x|vs\.?|VS|v\.?|-|/)\s*", jogo, flags=re.IGNORECASE)
        partes = [p.strip() for p in partes if p.strip()]
        return partes if len(partes) == 2 else []
    except (AttributeError, ValueError, TypeError):
        return []

def extrair_liga(texto: str) -> str | None:
    try:
        m = re.search(r"liga[:\-]\s*(.+)", texto, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None

def extrair_pais(texto: str) -> str | None:
    try:
        m = re.search(r"pa[ií]s[:\-]\s*(.+)", texto, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None

def eh_mercado_primeiro_tempo_over(nome_mercado: str) -> bool:
    nome = (nome_mercado or "").lower()
    return ("over" in nome or "total" in nome) and ("half" in nome or "first" in nome or "tempo" in nome)

async def buscar_fixture_id(nome_jogo: str, liga_hint: str | None = None, pais_hint: str | None = None) -> int | None:
    if not nome_jogo or not FOOTBALL_API_KEY:
        return None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    base_data = datetime.now(OPERATING_TZ)
    datas_busca = [base_data.strftime("%Y-%m-%d"), (base_data + timedelta(days=1)).strftime("%Y-%m-%d")]
    fixture_id = None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for data_alvo in datas_busca:
                for tentativa in range(2):
                    url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={data_alvo}"
                    try:
                        async with session.get(url_fixtures, headers=headers) as resp:
                            if resp.status != 200:
                                continue
                            
                            data = await resp.json()
                            jogos = data.get("response", [])

                            if liga_hint or pais_hint:
                                jogos_filtrados = []
                                for j in jogos:
                                    liga_nome = j.get("league", {}).get("name", "")
                                    pais_nome = j.get("league", {}).get("country", "")
                                    liga_ok = similaridade(liga_hint, liga_nome) >= 0.5 if liga_hint else True
                                    pais_ok = similaridade(pais_hint, pais_nome) >= 0.5 if pais_hint else True
                                    if liga_ok and pais_ok:
                                        jogos_filtrados.append(j)
                                if jogos_filtrados:
                                    jogos = jogos_filtrados

                            melhor_match = None
                            maior_similaridade = 0.72

                            for item in jogos:
                                teams = item.get("teams", {})
                                casa = teams.get("home", {}).get("name", "")
                                fora = teams.get("away", {}).get("name", "")
                                nome_match_api = f"{casa} x {fora}"
                                
                                sim = similaridade(nome_jogo, nome_match_api)
                                if sim > maior_similaridade:
                                    maior_similaridade = sim
                                    melhor_match = item
                            
                            if melhor_match:
                                fixture_id = melhor_match.get("fixture", {}).get("id")
                                metric("fixture_found")
                                return fixture_id
                            
                            try:
                                partes = extrair_times(nome_jogo)
                                if len(partes) == 2:
                                    time_casa_sinal, time_fora_sinal = partes
                                    palavras_casa = set(normalizar(time_casa_sinal).split())
                                    palavras_fora = set(normalizar(time_fora_sinal).split())

                                    for item in jogos:
                                        teams = item.get("teams", {})
                                        casa_api = teams.get("home", {}).get("name", "")
                                        fora_api = teams.get("away", {}).get("name", "")
                                        
                                        palavras_casa_api = set(normalizar(casa_api).split())
                                        palavras_fora_api = set(normalizar(fora_api).split())
                                        
                                        match_casa = len(palavras_casa.intersection(palavras_casa_api)) / len(palavras_casa) if palavras_casa else 0
                                        match_fora = len(palavras_fora.intersection(palavras_fora_api)) / len(palavras_fora) if palavras_fora else 0

                                        if match_casa > 0.5 and match_fora > 0.5:
                                            fixture_id = item.get("fixture", {}).get("id")
                                            return fixture_id
                            except ValueError:
                                pass
                    except asyncio.TimeoutError:
                        metric("fixture_retry")
                        await asyncio.sleep(1)
                        continue
            return None
    except Exception:
        return None
    return fixture_id

# --- Análise Climática ---
def analisar_clima(texto):
    pontos_clima = 0
    criterios_clima = []
    try:
        temp_match = re.search(r"🌡️\s*([\d.]+)\s*°C", texto)
        nuvens_match = re.search(r"(☁️|☁)\s*([\d.]+)%", texto)
        umidade_match = re.search(r"💧\s*([\d.]+)%", texto)
        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)
        
        temperatura = float(temp_match.group(1)) if temp_match else None
        nebulosidade = float(nuvens_match.group(2)) if nuvens_match else None
        umidade = float(umidade_match.group(1)) if umidade_match else None
        vento = float(vento_match.group(1)) if vento_match else None
        
        if temperatura is not None and 18 <= temperatura <= 28:
            pontos_clima += 1
            criterios_clima.append("Temperatura ideal")
        if nebulosidade is not None and nebulosidade >= 20:
            pontos_clima += 1
            criterios_clima.append("Nebulosidade ideal")
        if umidade is not None and 50 <= umidade <= 75:
            pontos_clima += 1
            criterios_clima.append("Umidade ideal")
        if vento is not None:
            if vento <= 7:
                pontos_clima += 1
                criterios_clima.append("Vento ótimo")
            elif 7 < vento <= 10:
                pontos_clima += 0.5
                criterios_clima.append("Vento moderado")
    except Exception:
        pass
    
    if pontos_clima >= 3.5:
        status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2:
        status_clima = "🟡 NEUTRO"
    else:
        status_clima = "🔴 DESFAVORÁVEL"
    
    return pontos_clima, criterios_clima, status_clima

# --- Buscar Odd ao Vivo ---
async def buscar_odd_ao_vivo(fixture_id: int, goal_line: float) -> str:
    odd_encontrada = "N/D"
    if not fixture_id:
        return odd_encontrada
    
    goal_line_str = str(goal_line).replace('.0', '')
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url_odds = "https://v3.football.api-sports.io/odds/live"
    params = {"fixture": str(fixture_id)}
    
    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for tentativa in range(2):
                try:
                    async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                        if resp_odds.status == 200:
                            data_odds = await resp_odds.json()
                            if data_odds.get('response'):
                                fixture_data = data_odds['response'][0]
                                bookmakers = fixture_data.get('bookmakers', [])
                                if bookmakers:
                                    for bookmaker in bookmakers:
                                        for market in bookmaker.get('bets', []):
                                            if eh_mercado_primeiro_tempo_over(market.get('name', '')):
                                                for value in market.get('values', []):
                                                    value_name = value.get('value', '').lower().replace(',', '.')
                                                    if f'over {goal_line_str}' in value_name:
                                                        return str(value.get('odd'))
                except asyncio.TimeoutError:
                    metric("odds_retry")
                    await asyncio.sleep(1)
                    continue
    except Exception:
        pass
    return odd_encontrada

async def buscar_odd_pre_live(fixture_id: int, goal_line: float) -> OddResultado:
    odd_encontrada = "N/D"
    if not fixture_id:
        return OddResultado(odd_encontrada, "unavailable")

    goal_line_str = str(goal_line).replace(".0", "")
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url_odds = "https://v3.football.api-sports.io/odds"
    params = {"fixture": str(fixture_id)}

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for tentativa in range(2):
                try:
                    async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                        if resp_odds.status == 200:
                            data_odds = await resp_odds.json()
                            response_items = data_odds.get("response") or []
                            if response_items:
                                fixture_data = response_items[0]
                                bookmakers = fixture_data.get("bookmakers", [])
                                for bookmaker in bookmakers:
                                    for market in bookmaker.get("bets", []):
                                        if eh_mercado_primeiro_tempo_over(market.get("name", "")):
                                            for value in market.get("values", []):
                                                value_name = value.get("value", "").lower().replace(",", ".")
                                                if f"over {goal_line_str}" in value_name:
                                                    return OddResultado(str(value.get("odd")), "pre-live")
                except asyncio.TimeoutError:
                    metric("odds_pre_live_retry")
                    await asyncio.sleep(1)
                    continue
    except Exception:
        pass

    odd_live = await buscar_odd_ao_vivo(fixture_id, goal_line)
    if odd_live != "N/D":
        return OddResultado(odd_live, "live")
    return OddResultado(odd_encontrada, "unavailable")

# --- Verificar Placar HT ao Vivo ---
async def verificar_placar_ht_ao_vivo(fixture_id: int) -> int | None:
    if not fixture_id:
        return None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for tentativa in range(2):
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('results', 0) > 0:
                                fixture = data['response'][0]
                                gols_casa = fixture.get('score', {}).get('halftime', {}).get('home', 0)
                                gols_fora = fixture.get('score', {}).get('halftime', {}).get('away', 0)
                                return gols_casa + gols_fora
                            return 0
                except asyncio.TimeoutError:
                    metric("fixture_retry")
                    await asyncio.sleep(1)
                    continue
    except Exception:
        pass
    return None

# --- Tarefa de Veredito ---
async def tarefa_veredito_dinamico_ht(fixture_id, msg_original, goal_line):
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"
    try:
        await asyncio.sleep(2300)
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]
                        data_jogo = fixture.get('fixture', {}).get('date')
                        gols_casa_ht = fixture.get('score', {}).get('halftime', {}).get('home', 0)
                        gols_fora_ht = fixture.get('score', {}).get('halftime', {}).get('away', 0)
                        
                        gols_ht = gols_casa_ht + gols_fora_ht
                        gols_casa_ft = fixture.get('score', {}).get('fulltime', {}).get('home')
                        gols_fora_ft = fixture.get('score', {}).get('fulltime', {}).get('away')
                        total_ft = (gols_casa_ft or 0) + (gols_fora_ft or 0)
                        resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if gols_ht > goal_line else "R E D ❌"
                        try:
                            atualizar_fixture_resultado(fixture_id, gols_ht, total_ft if total_ft else None, resultado_final, data_jogo)
                        except Exception:
                            pass
                else:
                    resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError:
        raise
    except Exception:
        resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        try:
            logger.info(f"metrics.summary {metrics_snapshot()}")
        except Exception:
            pass
        if not asyncio.current_task().cancelled():
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try:
                await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode='Markdown')
            except Exception:
                pass

# --- Análise Principal ---
async def analisar(texto):
    hora_atual = datetime.now(OPERATING_TZ).hour
    if not dentro_janela_operacao(hora_atual):
        return
    logger.info("📊 Iniciando análise do sinal...")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        
        if "U20" in jogo.upper() or "U19" in jogo.upper():
            return
        
        logger.info(f"📌 Jogo detectado: {jogo}")
        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None
        
        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%\s*/\s*([\d.]+)%", texto)
        ia = max(map(float, ia_match.groups())) if ia_match else None
        if not ia:
            ia_match_antigo = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
            if ia_match_antigo: ia = float(ia_match_antigo.group(1))
        
        match_perigosos = re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)
        perigosos = list(map(int, match_perigosos[0])) if match_perigosos else [0, 0]
        match_posse = re.findall(r"Posse de Bola:\s*(\d+)%\s*/\s*(\d+)%", texto)
        posse = list(map(int, match_posse[0])) if match_posse else [0, 0]
        match_escanteios = re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)
        escanteios = list(map(int, match_escanteios[0])) if match_escanteios else [0, 0]
        match_no_gol = re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)
        no_gol = list(map(int, match_no_gol[0])) if match_no_gol else [0, 0]
        match_fora_gol = re.findall(r"Fora do Gol:\s*(\d+)/(\d+)", texto)
        fora_gol = list(map(int, match_fora_gol[0])) if match_fora_gol else [0, 0]
        
        chutes = [no_gol[0] + fora_gol[0], no_gol[1] + fora_gol[1]]

        pontos_clima, _, status_clima = analisar_clima(texto)
        criterios_tecnicos = []
        pontos_tecnicos = 0
        
        if ia and ia >= 70:
            criterios_tecnicos.append("IA favorável")
            pontos_tecnicos += 2
        if minuto and 16 <= minuto <= 22:
            pontos_tecnicos += 1
        
        soma_perigosos = sum(perigosos)
        diff_perigosos = abs(perigosos[0] - perigosos[1])
        if soma_perigosos >= 15 or (soma_perigosos >= 10 and diff_perigosos >= 5):
            pontos_tecnicos += 2
        
        if sum(no_gol) >= 1: pontos_tecnicos += 2
        if sum(escanteios) >= 2: pontos_tecnicos += 1
        if sum(chutes) >= 4: pontos_tecnicos += 1
        if posse[0] >= 60 or posse[1] >= 60: pontos_tecnicos += 1
        
        pontos_total = pontos_tecnicos + pontos_clima
        nomes_times = extrair_times(jogo)
        if len(nomes_times) == 2:
            perc_hist, ultimo_res = obter_metricas_historicas(nomes_times[0], nomes_times[1])
            bonus_hist, criterios_hist = calcular_bonus_historico(perc_hist, ultimo_res, HIST_BONUS_HIGH, HIST_BONUS_MED, HIST_PENALTY_RED)
            criterios_tecnicos.extend(criterios_hist)
            pontos_total += bonus_hist

        logger.info(f"📈 Pontos Técnicos: {pontos_tecnicos}/10 | 🌤️ Pontos Clima: {pontos_clima}/4 | 🎯 Total: {pontos_total}")

        if pontos_total >= 10:
            nivel_confianca = "ALTA" if pontos_total < VERY_HIGH_CONFIDENCE_THRESHOLD else "MUITO ALTA"
            confianca = CONFIDENCE_MAP[nivel_confianca]
            resumo_clima = f" {status_clima} ({pontos_clima}/4pts)"
            resumo_tecnico = f" {pontos_tecnicos}/10pts"

            liga_hint = extrair_liga(texto)
            pais_hint = extrair_pais(texto)
            fixture_id = await buscar_fixture_id(jogo, liga_hint, pais_hint)
            
            if not fixture_id:
                resumo_historico = None
                try:
                    if len(nomes_times) == 2:
                        resumo_historico = await resumo_estatistico(nomes_times[0], nomes_times[1])
                except Exception:
                    pass
                msg = f"""⚽️ ENTRAR | CONFIANÇA: {confianca}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD ATUAL: *N/D*\n▶️ ENTRADA: OVER 0.5 HT{f'\n\n{resumo_historico}' if resumo_historico else ''}"""
                await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
                return
            else:
                try:
                    if len(nomes_times) == 2:
                        salvar_fixture_pendente(nomes_times[0], nomes_times[1], fixture_id, None, None)
                except Exception:
                    pass

            gols_ht_atuais = await verificar_placar_ht_ao_vivo(fixture_id)

            if gols_ht_atuais is not None and gols_ht_atuais >= 3:
                return

            goal_line_alvo = (gols_ht_atuais or 0) + 0.5
            mercado_alvo = f"Over {goal_line_alvo} HT"
            odd_ht, odd_origem = await buscar_odd_pre_live(fixture_id, goal_line_alvo)
            odd_exibicao = rotular_odd(odd_ht, odd_origem if odd_ht != "N/D" else None)
            resumo_historico = None
            try:
                if len(nomes_times) == 2:
                    odd_ref = odd_ht if odd_ht != "N/D" else None
                    salvar_fixture_pendente(nomes_times[0], nomes_times[1], fixture_id, odd_ref, None)
                    resumo_historico = await resumo_estatistico(nomes_times[0], nomes_times[1], odd_ref)
            except Exception:
                pass

            veredito = f"ENTRADA HT LIMITE | CONFIANÇA: {confianca}" if gols_ht_atuais and gols_ht_atuais > 0 else f"ENTRAR | CONFIANÇA: {confianca}"
            
            msg = f"""⚽️ {veredito}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD: *{odd_exibicao}*\n▶️ ENTRADA: {mercado_alvo}{f'\n\n{resumo_historico}' if resumo_historico else ''}"""
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
            logger.info(f"✅ Sinal enviado para: {jogo}")
            asyncio.create_task(tarefa_veredito_dinamico_ht(fixture_id, msg_enviada, goal_line_alvo))
        else:
            logger.info(f"❌ Pontuação ({pontos_total}) insuficiente para '{jogo}'.")
    except Exception as e:
        logger.error(f"Erro na análise principal: {e}")

# --- Telethon Client ---
client = TelegramClient(StringSession(TELEGRAM_SESSION), API_ID, API_HASH)

# --- Radar de Sinais BLINDADO COM RAIO-X PROFUNDO ---
async def radar_anti_restricao():
    logger.info("📡 Iniciando radar de escuta (Modo Polling Anti-Restrição)...")
    ultimo_id = 0
    try:
        msgs = await client.get_messages(CHAT_ID_SINAL, limit=1)
        if msgs:
            ultimo_id = msgs[0].id
            logger.info(f"📡 Radar calibrado. Ignorando mensagens antigas até ID {ultimo_id}.")
    except Exception as e:
        logger.error(f"Erro ao calibrar radar: {e}")

    while True:
        await asyncio.sleep(3) 
        try:
            msgs = await client.get_messages(CHAT_ID_SINAL, limit=10)
            if not msgs:
                continue
            
            novas_msgs = [m for m in msgs if m.id > ultimo_id]
            
            if novas_msgs:
                ultimo_id = novas_msgs[0].id
                
                for msg in reversed(novas_msgs):
                    logger.info(f"👀 Nova mensagem capturada no VIP (ID: {msg.id})")
                    
                    # EXTRAÇÃO BRUTA: Tenta pegar o texto de TODAS as propriedades possíveis
                    conteudo_bruto = ""
                    if hasattr(msg, 'text') and msg.text:
                        conteudo_bruto = msg.text
                    elif hasattr(msg, 'raw_text') and msg.raw_text:
                        conteudo_bruto = msg.raw_text
                    elif hasattr(msg, 'message') and msg.message:
                        conteudo_bruto = msg.message
                    elif hasattr(msg, 'caption') and msg.caption:
                        conteudo_bruto = msg.caption
                    
                    # SE AINDA ASSIM VIER VAZIO, VAMOS IMPRIMIR A ESTRUTURA PARA DESCOBRIR O PORQUÊ
                    if not conteudo_bruto:
                        logger.info(f"📝 TEXTO BRUTO: VAZIO. O Telegram enviou um pacote sem texto.")
                        logger.info(f"🔎 RAIOS-X DA MENSAGEM ID {msg.id}:\n{msg.stringify()}")
                        continue
                    
                    logger.info(f"📝 TEXTO BRUTO CAPTURADO: {repr(conteudo_bruto)}")
                    
                    # Faxina
                    conteudo_limpo = conteudo_bruto.replace('\u2060', '').replace('\u200b', '').strip()
                    
                    # Filtro de Segurança
                    if not conteudo_limpo:
                        logger.info(f"⚠️ Mensagem limpa ficou vazia (ID {msg.id}). Ignorada.")
                        continue
                        
                    if "⚽" not in conteudo_limpo and "HT" not in conteudo_limpo.upper():
                        logger.info(f"⚠️ Mensagem sem padrão de sinal (ID {msg.id}). Ignorada.")
                        continue
                    
                    logger.info(f"✅ Mensagem ID {msg.id} é um sinal válido. Encaminhando para análise...")
                    
                    asyncio.create_task(analisar(conteudo_limpo))
                    
        except Exception as e:
            logger.error(f"⚠️ Erro no radar: {e}")
            await asyncio.sleep(5)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot Over HT ativo!")

async def main():
    try:
        logger.info("🚀 Iniciando Bot Over HT")
        try:
            keep_alive()
        except Exception:
            pass
        
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        
        await client.connect()
        if not await client.is_user_authorized():
            raise ValueError("Sessão Inválida. Atualize a TELEGRAM_SESSION.")
            
        logger.info("🔄 Bot rodando...")
        
        asyncio.create_task(radar_anti_restricao())
        
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
    finally:
        if 'app' in locals() and app.updater.running:
            await app.updater.stop()
        if 'app' in locals():
            await app.shutdown()
        if client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        pass
