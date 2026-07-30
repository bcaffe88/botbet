import os
import re
import unicodedata
import asyncio
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
from telethon.sessions import MemorySession
import aiohttp
import traceback

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuração de Confiança
VERY_HIGH_CONFIDENCE_THRESHOLD = 12

# Validar variáveis de ambiente UNIFICADAS
required_vars = ["BOT_TOKEN", "API_ID", "API_HASH", "CHAT_ID_SINAL", "CHAT_ID_DESTINO", "FOOTBALL_API_KEY"]
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    raise ValueError(f"Variáveis obrigatórias não encontradas: {', '.join(missing_vars)}")

try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
    CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
except ValueError as e:
    raise ValueError(f"Erro ao converter variáveis numéricas: {e}")

bot = Bot(token=BOT_TOKEN)

# --- Utilitários ---
def normalizar(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    if not a or not b: return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

# --- BUSCA DE FIXTURE (Com D e D+1 para fuso horário) ---
async def buscar_fixture_id(nome_jogo: str) -> int | None:
    if not nome_jogo or not FOOTBALL_API_KEY:
        return None
    
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    hoje = datetime.now()
    amanha = hoje + timedelta(days=1)
    datas_busca = [hoje.strftime("%Y-%m-%d"), amanha.strftime("%Y-%m-%d")]
    
    fixture_id = None
    maior_similaridade = 0.75
    melhor_match = None

    logger.info(f"🔎 Buscando fixture para '{nome_jogo}' nas datas: {datas_busca}")

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for data in datas_busca:
                url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={data}"
                async with session.get(url_fixtures, headers=headers) as resp:
                    if resp.status == 200:
                        json_data = await resp.json()
                        jogos = json_data.get("response", [])
                        
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
                    break # Se achou no dia de hoje, não precisa buscar amanhã

            if melhor_match:
                fixture_id = melhor_match.get("fixture", {}).get("id")
                api_name = f"{melhor_match['teams']['home']['name']} x {melhor_match['teams']['away']['name']}"
                logger.info(f"✅ Fixture encontrado: '{api_name}' | ID: {fixture_id} | Similaridade: {maior_similaridade:.2f}")
            else:
                logger.warning(f"⚠️ Fixture não localizado para '{nome_jogo}'.")
                
    except Exception as e:
        logger.error(f"❌ Erro em buscar_fixture_id: {e}")
        
    return fixture_id

# --- MOTOR DUPLO DE ODDS (Pré-Live + Live) ---
async def buscar_odd_ht(fixture_id: int | None) -> str:
    if not fixture_id:
        return "N/L"
    
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    params = {"fixture": str(fixture_id)}
    
    odd_value = "N/D"
    ht_indicators = ['first half', '1st half', 'half time', 'ht', '1h', 'primeiro tempo']
    goals_indicators = ['over/under', 'total', 'goals', 'gols']
    over_05_patterns = ['over 0.5', 'over 0,5', 'mais 0.5', '> 0.5']

    async def extrair_odd_do_json(json_response):
        if json_response.get('results', 0) > 0:
            for bookmaker in json_response['response'][0].get('bookmakers', []):
                for market in bookmaker.get('bets', []):
                    market_name = market.get('name', '').lower()
                    if any(kw in market_name for kw in ht_indicators) and any(kw in market_name for kw in goals_indicators):
                        for value in market.get('values', []):
                            val_str = str(value.get('value', '')).lower().replace(',', '.')
                            if any(p in val_str for p in over_05_patterns):
                                return str(value.get('odd'))
        return None

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Tenta buscar no Pré-Live primeiro (mais estável)
            url_pre = "https://v3.football.api-sports.io/odds"
            logger.info(f"🔎 Buscando ODD PRÉ-LIVE para ID {fixture_id}...")
            async with session.get(url_pre, headers=headers, params=params) as resp:
                if resp.status == 200:
                    odd_encontrada = await extrair_odd_do_json(await resp.json())
                    if odd_encontrada:
                        logger.info(f"🎉 ODD PRÉ-LIVE Encontrada: {odd_encontrada}")
                        return odd_encontrada

            # 2. Se falhou, tenta no Live (Ao Vivo)
            url_live = "https://v3.football.api-sports.io/odds/live"
            logger.info(f"⚠️ Odd Pré-live não achada. Buscando ODD AO VIVO para ID {fixture_id}...")
            async with session.get(url_live, headers=headers, params=params) as resp:
                if resp.status == 200:
                    odd_encontrada = await extrair_odd_do_json(await resp.json())
                    if odd_encontrada:
                        logger.info(f"🎉 ODD AO VIVO Encontrada: {odd_encontrada}")
                        return odd_encontrada
                        
            logger.warning(f"⚠️ Nenhuma ODD Over 0.5 HT localizada na API para o ID {fixture_id}.")
            
    except Exception as e:
        logger.error(f"❌ Erro ao buscar ODD: {e}")
        
    return odd_value

# --- VEREDITO 2.0 (Validação de Status) ---
async def tarefa_veredito_por_id(fixture_id, msg_original):
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"
    try:
        # Aguarda 35 minutos para o fim do primeiro tempo
        logger.info(f"⏰ [0.5 HT] Aguardando 35 min para veredito do ID: {fixture_id}")
        await asyncio.sleep(2100) 
        
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture_data = data['response'][0]
                        status_curto = fixture_data.get('fixture', {}).get('status', {}).get('short', '')
                        
                        # Verifica os gols no intervalo
                        score = fixture_data.get('score', {}).get('halftime', {})
                        gols_casa = score.get('home')
                        gols_fora = score.get('away')
                        
                        if gols_casa is not None and gols_fora is not None:
                            gols_ht = gols_casa + gols_fora
                            if gols_ht >= 1:
                                resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅"
                            else:
                                resultado_final = "R E D ❌"
                        elif status_curto in ['HT', '2H', 'FT']:
                            # Se o status diz que o 1º tempo acabou, mas os gols são 'None', foi 0x0
                            resultado_final = "R E D ❌"
                        else:
                            resultado_final = f"⏳ JOGO AINDA ROLANDO (Status: {status_curto})"
                            logger.warning(f"⚠️ [0.5 HT] Jogo {fixture_id} não finalizou o HT ainda.")
                else:
                    logger.error("❌ [0.5 HT] Erro de status HTTP na API de Veredito.")
    except Exception as e:
        logger.error(f"❌ [0.5 HT] Erro no Veredito para ID {fixture_id}: {e}")
    finally:
        try:
            texto_antigo = msg_original.text or msg_original.caption
            novo_texto = f"{texto_antigo}\n\n───────────────\n{resultado_final}"
            await bot.edit_message_text(
                chat_id=CHAT_ID_DESTINO, 
                message_id=msg_original.message_id, 
                text=novo_texto
            )
            logger.info(f"✅ Veredito atualizado com sucesso: {resultado_final}")
        except Exception as edit_error:
            logger.error(f"❌ Falha ao editar mensagem com veredito: {edit_error}")

# --- ANÁLISE CLIMÁTICA ---
def analisar_clima(texto):
    pontos_clima = 0
    criterios_clima = []
    
    try:
        temp_match = re.search(r"🌡️\s*([\d.]+)\s*°C", texto)
        nuvens_match = re.search(r"☁\s*([\d.]+)%", texto)
        umidade_match = re.search(r"💧\s*([\d.]+)%", texto)
        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)
        
        temperatura = float(temp_match.group(1)) if temp_match else None
        nebulosidade = float(nuvens_match.group(1)) if nuvens_match else None
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
                
    except Exception as e:
        logger.error(f"Erro no clima: {e}")

    if pontos_clima >= 3.5: status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2: status_clima = "🟡 NEUTRO"
    else: status_clima = "🔴 DESFAVORÁVEL"
    
    return pontos_clima, criterios_clima, status_clima

# --- LÓGICA PRINCIPAL OVER 0.5 HT ---
async def analisar(texto):
    logger.info("📊 Iniciando análise do sinal 'Over 0.5 HT'")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        
        if "U20" in jogo.upper():
            logger.info(f"🚫 Jogo U20 ('{jogo}') ignorado.")
            return

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
        pontos_tecnicos = 0
        
        if ia and ia >= 70: pontos_tecnicos += 2
        if minuto and 16 <= minuto <= 22: pontos_tecnicos += 1
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7: pontos_tecnicos += 2
        if sum(no_gol) >= 1: pontos_tecnicos += 2
        if sum(escanteios) >= 2: pontos_tecnicos += 1
        if sum(chutes) >= 4: pontos_tecnicos += 1
        if posse[0] >= 60 or posse[1] >= 60: pontos_tecnicos += 1
        
        pontos_total = pontos_tecnicos + pontos_clima

        # === A SUA LÓGICA FLEXÍVEL 3 CONDIÇÕES ===
        condicao1 = pontos_total >= 9.0
        condicao2 = pontos_tecnicos >= 7 and pontos_clima >= 2
        condicao3 = pontos_tecnicos >= 8 and pontos_clima >= 1.5
        
        deve_entrar = condicao1 or condicao2 or condicao3

        logger.info(f"📈 Téc: {pontos_tecnicos} | 🌤️ Clima: {pontos_clima} | 🎯 Total: {pontos_total}")

        if deve_entrar:
            logger.info(f"✅ Sinal validado: '{jogo}'. Buscando ID e Odd...")
            
            fixture_id = await buscar_fixture_id(jogo)
            odd_ht = await buscar_odd_ht(fixture_id)
            
            if pontos_total >= VERY_HIGH_CONFIDENCE_THRESHOLD:
                confianca = "MUITO ALTA 🔥 STAKE 1%"
            elif pontos_total >= 10: 
                confianca = "ALTA ✅ STAKE 0.75%"
            elif pontos_clima >= 3: 
                confianca = "MÉDIA-ALTA ⚡ STAKE 0.5%"
            else: 
                confianca = "MÉDIA ⚠️ STAKE 0.25%"
            
            msg = f"""⚽️ ENTRAR | CONFIANÇA: {confianca}
🏟️ {jogo}
🤖 OVERBOT ANÁLISE:
⚽ CRITÉRIOS ATENDIDOS:  {pontos_tecnicos}/10pts 
🌤️ CLIMA:  {status_clima} ({pontos_clima}/4pts)
📊 ODD ATUAL: *{odd_ht}*
▶️ ENTRADA: OVER 0.5 HT"""
            
            # Envio sem o parse_mode='Markdown' estrito para evitar crashes com caracteres especiais
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
            logger.info(f"✅ Sinal enviado: {jogo}")
            
            if fixture_id:
                asyncio.create_task(tarefa_veredito_por_id(fixture_id, msg_enviada))
        else:
            logger.info(f"❌ Critérios insuficientes para '{jogo}'.")
    except Exception as e:
        logger.error(f"❌ Erro na análise principal: {e}")
        logger.error(traceback.format_exc())

# --- ROTEADOR E INICIALIZAÇÃO BLINDADA (SEM ARQUIVO .SESSION) ---
client = TelegramClient(MemorySession(), API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHAT_ID_SINAL))
async def roteador_de_sinais(event):
    try:
        # Extração blindada (Previews)
        conteudo = getattr(event.message, 'raw_text', getattr(event.message, 'message', ''))
        
        if not conteudo:
            return

        if "OVER 0.5 HT" in conteudo and "Inteligência Artificial" in conteudo:
            logger.info("📡 Sinal 'OVER 0.5 HT' capturado pelo roteador.")
            await analisar(conteudo)
            
    except Exception as e:
        logger.error(f"Erro no roteador: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot 2.0 ativo, sem sessões físicas, com duplo motor de odd!")

async def main():
    try:
        logger.info("🚀 Iniciando Bot 2.0")
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        
        # Conexão direta usando apenas o Token (Resolve o EOF na Railway)
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Telethon conectado em Memória com sucesso!")
        logger.info("🔄 Bot rodando e escutando os sinais...")
        
        await client.run_until_disconnected()
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
    except Exception as e:
        logger.error(f"Erro na inicialização: {e}")
