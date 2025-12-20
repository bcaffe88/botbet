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
import traceback

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

# --- Funções Utilitárias ---
def normalizar(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    if not a or not b: return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

async def buscar_fixture_id(nome_jogo: str) -> int | None:
    if not nome_jogo or not FOOTBALL_API_KEY:
        return None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"
    
    logger.info(f"🔎 Buscando fixture para '{nome_jogo}' em TODOS os jogos da data: {data_hoje}")
    
    fixture_id = None
    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url_fixtures, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"Erro ao buscar fixtures: Status {resp.status}")
                    return None
                
                data = await resp.json()
                jogos = data.get("response", [])
                logger.info(f"API retornou {len(jogos)} jogos para o dia. Comparando nomes...")

                melhor_match = None
                maior_similaridade = 0.75

                # Primeira tentativa: busca exata por similaridade de nome completo
                logger.info("  1️⃣ Tentando busca por similaridade de nome completo...")
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
                    api_name = f"{melhor_match['teams']['home']['name']} x {melhor_match['teams']['away']['name']}"
                    logger.info(f"✅ Fixture encontrado para '{nome_jogo}' ≈ '{api_name}': ID {fixture_id} (Similaridade: {maior_similaridade:.2f})")
                    return fixture_id
                else:
                    logger.warning(f"  ❌ Primeira busca falhou. Nenhuma similaridade > {maior_similaridade} encontrada.")
                
                # Segunda tentativa: busca flexível por palavras-chave
                logger.info("  2️⃣ Tentando busca flexível por palavras-chave...")
                try:
                    time_casa_sinal, time_fora_sinal = nome_jogo.split(' x ')
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
                            api_name = f"{casa_api} x {fora_api}"
                            logger.info(f"✅ Fixture encontrado com busca flexível: '{nome_jogo}' ≈ '{api_name}': ID {fixture_id}")
                            return fixture_id
                except ValueError:
                    logger.warning("  ❌ Não foi possível dividir o nome do jogo para a busca flexível.")
                    
                logger.error(f"❌ Fixture não localizado para '{nome_jogo}' após todas as tentativas.")
                return None
    
    except asyncio.TimeoutError:
        logger.error("Timeout ao baixar a lista de jogos do dia. A resposta pode ser muito grande.")
        return None
    except Exception as e:
        logger.error(f"Erro em buscar_fixture_id: {e}")
        return None
        
    return fixture_id

# --- Análise Climática ---
def analisar_clima(texto):
    pontos_clima = 0
    criterios_clima = []
    logger.info("🌤️ Iniciando análise climática...")
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
            criterios_clima.append("Nebulosidade ideal (sem sol forte)")
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
        logger.error(f"Erro na análise climática: {e}")
    
    if pontos_clima >= 3.5:
        status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2:
        status_clima = "🟡 NEUTRO"
    else:
        status_clima = "🔴 DESFAVORÁVEL"
    
    logger.info(f"🌤️ Pontuação Climática Final: {pontos_clima}/4 - {status_clima}")
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
    
    logger.info(f"🔎 Buscando odd AO VIVO para Over {goal_line} HT no Fixture ID: {fixture_id}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                if resp_odds.status == 200:
                    data_odds = await resp_odds.json()
                    
                    if data_odds.get('response'):
                        fixture_data = data_odds['response'][0]
                        bookmakers = fixture_data.get('bookmakers', [])
                        
                        if bookmakers:
                            for bookmaker in bookmakers:
                                for market in bookmaker.get('bets', []):
                                    market_name_lower = market.get('name', '').lower()
                                    if ('over' in market_name_lower or 'total' in market_name_lower) and ('half' in market_name_lower or 'first' in market_name_lower or 'tempo' in market_name_lower):
                                        logger.info(f"🎯 Mercado HT compatível encontrado: '{market.get('name')}'")
                                        
                                        for value in market.get('values', []):
                                            value_name = value.get('value', '').lower().replace(',', '.')
                                            if f'over {goal_line_str}' in value_name:
                                                odd_value = value.get('odd')
                                                logger.info(f"🎉 ODD AO VIVO ENCONTRADA (Over {goal_line} HT): {odd_value}")
                                                return str(odd_value)
                        
                        logger.warning(f"⚠️ Odd 'Over {goal_line} HT' não encontrada nos mercados.")
                    else:
                        logger.warning(f"⚠️ API /odds/live não retornou dados para fixture {fixture_id}.")
                else:
                    logger.error(f"❌ Erro na API /odds/live: Status {resp_odds.status}")
    except Exception as e:
        logger.error(f"❌ Erro crítico em buscar_odd_ao_vivo: {e}")
        
    return odd_encontrada

# --- Verificar Placar HT ao Vivo ---
async def verificar_placar_ht_ao_vivo(fixture_id: int) -> int | None:
    if not fixture_id:
        return None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
    logger.info(f"🔎 Verificando placar ao vivo para fixture ID: {fixture_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]
                        gols_casa = fixture.get('score', {}).get('halftime', {}).get('home', 0)
                        gols_fora = fixture.get('score', {}).get('halftime', {}).get('away', 0)
                        total_gols = gols_casa + gols_fora
                        logger.info(f"✅ Placar HT atual: {total_gols} gols.")
                        return total_gols
                    else:
                        logger.warning(f"⚠️ Placar HT indisponível na API. Assumindo 0 gols.")
                        return 0
                else:
                    logger.error(f"❌ Erro ao verificar placar: Status {resp.status}")
    except Exception as e:
        logger.error(f"❌ Erro crítico ao verificar placar: {e}")
    return None

# --- Tarefa de Veredito ---
async def tarefa_veredito_dinamico_ht(fixture_id, msg_original, goal_line):
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"
    try:
        logger.info(f"⏰ [Over {goal_line} HT] Aguardando 35 min para veredito do fixture ID: {fixture_id}")
        await asyncio.sleep(2300)
        
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]
                        gols_casa_ht = fixture.get('score', {}).get('halftime', {}).get('home', 0)
                        gols_fora_ht = fixture.get('score', {}).get('halftime', {}).get('away', 0)
                        
                        gols_ht = gols_casa_ht + gols_fora_ht
                        resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if gols_ht > goal_line else "R E D ❌"
                    else:
                        logger.warning(f"⚠️ [Over {goal_line} HT] API não retornou dados para fixture.")
                else:
                    resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError:
        logger.info(f"Tarefa de veredito (Over {goal_line} HT) para fixture {fixture_id} foi cancelada.")
        raise
    except Exception as e:
        logger.error(f"❌ [Over {goal_line} HT] Erro crítico na tarefa de veredito: {e}")
        resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        if not asyncio.current_task().cancelled():
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID_DESTINO,
                    message_id=msg_original.message_id,
                    text=novo_texto,
                    parse_mode='Markdown'
                )
            except Exception as edit_error:
                logger.error(f"❌ Falha ao editar mensagem para fixture {fixture_id}: {edit_error}")

# --- Análise Principal (SOMENTE CONFIANÇA MUITO ALTA) ---
async def analisar(texto):
    logger.info("📊 Iniciando análise do sinal 'Over 0.5 HT'")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        
        if "U20" in jogo.upper() or "U19" in jogo.upper():
            logger.info(f"🚫 Sinal para jogo U20/U19 ('{jogo}') ignorado.")
            return
        
        logger.info(f"📌 Jogo detectado: {jogo}")
        
        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None
        
        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%\s*/\s*([\d.]+)%", texto)
        ia = None
        if ia_match:
            ia = max(map(float, ia_match.groups()))
        else:
            ia_match_antigo = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
            if ia_match_antigo:
                ia = float(ia_match_antigo.group(1))
        
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
            criterios_tecnicos.append("Minuto ideal")
            pontos_tecnicos += 1
        
        soma_perigosos = sum(perigosos)
        diff_perigosos = abs(perigosos[0] - perigosos[1])
        if soma_perigosos >= 15 or (soma_perigosos >= 10 and diff_perigosos >= 5):
            criterios_tecnicos.append("Ataques perigosos")
            pontos_tecnicos += 2
        
        if sum(no_gol) >= 1:
            criterios_tecnicos.append("Finalizações no gol")
            pontos_tecnicos += 2
        if sum(escanteios) >= 2:
            criterios_tecnicos.append("Escanteios")
            pontos_tecnicos += 1
        if sum(chutes) >= 4:
            criterios_tecnicos.append("Chutes suficientes")
            pontos_tecnicos += 1
        if posse[0] >= 60 or posse[1] >= 60:
            criterios_tecnicos.append("Posse dominante")
            pontos_tecnicos += 1
        
        pontos_total = pontos_tecnicos + pontos_clima
        
        logger.info(f"📈 Pontos Técnicos: {pontos_tecnicos}/10 | 🌤️ Pontos Clima: {pontos_clima}/4 | 🎯 Total: {pontos_total}")

        # SOMENTE CONFIANÇA ALTA (>= 10 pontos)
        if pontos_total >= 10:
            nivel_confianca = "ALTA" if pontos_total < 12 else "MUITO ALTA"
            confianca = "ALTA ✅ STAKE 0.75%" if nivel_confianca == "ALTA" else "MUITO ALTA ✅✅ STAKE 1%"
            logger.info(f"✅ Pontuação {nivel_confianca} ({pontos_total}) para '{jogo}'. Iniciando validação com API...")

            resumo_clima = f" {status_clima} ({pontos_clima}/4pts)"
            resumo_tecnico = f" {pontos_tecnicos}/10pts"

            fixture_id = await buscar_fixture_id(jogo)
            
            if not fixture_id:
                veredito = f"ENTRAR | CONFIANÇA: {confianca}"
                odd_ht = "N/D"
                msg = f"""⚽️ {veredito}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD ATUAL: *{odd_ht}*\n▶️ ENTRADA: OVER 0.5 HT"""
                await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
                logger.info(f"✅ Sinal enviado para '{jogo}' (sem dados da API).")
                logger.warning(f"Veredito não agendado para '{jogo}' pois o fixture ID não pôde ser encontrado.")
                return

            gols_ht_atuais = await verificar_placar_ht_ao_vivo(fixture_id)

            # Validação com placar
            if gols_ht_atuais is not None and gols_ht_atuais >= 3:
                logger.info(f"🚫 SINAL INVÁLIDO! Jogo '{jogo}' já tem 3 ou mais gols no 1º tempo. Ignorando.")
                return

            goal_line_alvo = (gols_ht_atuais or 0) + 0.5
            mercado_alvo = f"Over {goal_line_alvo} HT"
            odd_ht = await buscar_odd_ao_vivo(fixture_id, goal_line_alvo)

            if gols_ht_atuais is not None and gols_ht_atuais > 0:
                veredito = f"ENTRADA HT LIMITE | CONFIANÇA: {confianca}"
            else:
                veredito = f"ENTRAR | CONFIANÇA: {confianca}"
            
            msg = f"""⚽️ {veredito}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD ATUAL: *{odd_ht}*\n▶️ ENTRADA: {mercado_alvo}"""
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
            logger.info(f"✅ Sinal '{mercado_alvo}' enviado para: {jogo}")
            asyncio.create_task(tarefa_veredito_dinamico_ht(fixture_id, msg_enviada, goal_line_alvo))
        
        else:
            logger.info(f"❌ Pontuação insuficiente ({pontos_total}) para '{jogo}'. Necessário >= 10 para CONFIANÇA ALTA/MUITO ALTA. Sinal ignorado.")
    
    except Exception as e:
        logger.error(f"Erro na análise principal: {e}")
        logger.error(traceback.format_exc())

# --- Telethon Client ---
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHAT_ID_SINAL))
async def roteador_de_sinais(event):
    try:
        conteudo = event.message.message
        if not conteudo:
            return
        
        # Apenas processar sinais "OVER 0.5 HT"
        if "OVER 0.5 HT" in conteudo and "Inteligência Artificial" in conteudo:
            logger.info("Sinal 'OVER 0.5 HT' detectado. Roteando para análise principal.")
            await analisar(conteudo)
    except Exception as e:
        logger.error(f"Erro no roteador de sinais: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot Over HT (Confiança Alta) ativo e escutando!")

async def main():
    try:
        logger.info("🚀 Iniciando Bot Over HT - Apenas Confiança ALTA")
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
        logger.info("🔄 Bot rodando... Pressione Ctrl+C para parar")
        
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
    except Exception as e:
        logger.error(f"Erro na inicialização: {e}")
