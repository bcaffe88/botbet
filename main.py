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

# Inicializar bot
bot = Bot(token=BOT_TOKEN)

# --- Funções Utilitárias Comuns ---
def normalizar(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    if not a or not b: return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

# --- FUNÇÃO DE BUSCA DE FIXTURE RESTAURADA PARA A LÓGICA ORIGINAL ---
async def buscar_fixture_id(nome_jogo: str) -> int | None:
    """
    Busca o fixture ID usando a lógica original: baixa todos os jogos do dia
    e encontra o melhor resultado por similaridade de nome.
    """
    if not nome_jogo or not FOOTBALL_API_KEY:
        return None

    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"
    
    logger.info(f"🔎 Buscando fixture para '{nome_jogo}' em TODOS os jogos da data: {data_hoje}")
    
    fixture_id = None
    try:
        # Aumentado o timeout pois a resposta pode ser grande
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
                maior_similaridade = 0.75 # Limite mínimo de similaridade

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
                else:
                    logger.warning(f"Fixture não localizado para '{nome_jogo}' com similaridade > {maior_similaridade} nos {len(jogos)} jogos de hoje.")
    
    except asyncio.TimeoutError:
        logger.error("Timeout ao baixar a lista de jogos do dia. A resposta pode ser muito grande.")
        return None
    except Exception as e:
        logger.error(f"Erro em buscar_fixture_id: {e}")
        return None
        
    return fixture_id

# --- Funções do Bot 1 (Análise Climática) ---

def analisar_clima(texto):
    pontos_clima = 0
    criterios_clima = []
    logger.info("🌤️ Iniciando análise climática...")
    try:
        temp_match = re.search(r"🌡️\s*([\d.]+)\s*°C", texto)
        nuvens_match = re.search(r"☁\s*([\d.]+)%", texto)
        umidade_match = re.search(r"💧\s*([\d.]+)%", texto)
        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)
        temperatura = float(temp_match.group(1)) if temp_match else None
        nebulosidade = float(nuvens_match.group(1)) if nuvens_match else None
        umidade = float(umidade_match.group(1)) if umidade_match else None
        vento = float(vento_match.group(1)) if vento_match else None
        log_clima = []
        if temperatura is not None:
            if 18 <= temperatura <= 28: pontos_clima += 1; criterios_clima.append("Temperatura ideal")
            log_clima.append(f"Temperatura: {temperatura}°C → {'✅' if 18 <= temperatura <= 28 else '❌'}")
        if nebulosidade is not None:
            if 20 <= nebulosidade <= 70: pontos_clima += 1; criterios_clima.append("Nebulosidade ideal")
            log_clima.append(f"Nebulosidade: {nebulosidade}% → {'✅' if 20 <= nebulosidade <= 70 else '❌'}")
        if umidade is not None:
            if 50 <= umidade <= 75: pontos_clima += 1; criterios_clima.append("Umidade ideal")
            log_clima.append(f"Umidade: {umidade}% → {'✅' if 50 <= umidade <= 75 else '❌'}")
        if vento is not None:
            if vento <= 7: pontos_clima += 1; criterios_clima.append("Vento ótimo")
            elif 7 < vento <= 10: pontos_clima += 0.5; criterios_clima.append("Vento moderado")
            log_clima.append(f"Vento: {vento} m/s → {'✅' if vento <= 7 else '⚠️' if vento <= 10 else '❌'}")
        logger.info(f"🌤️ Detalhes Climáticos Extraídos: {' | '.join(log_clima)}")
    except Exception as e:
        logger.error(f"Erro na análise climática: {e}")

    if pontos_clima >= 3.5: status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2: status_clima = "🟡 NEUTRO"
    else: status_clima = "🔴 DESFAVORÁVEL"
    logger.info(f"🌤️ Pontuação Climática Final: {pontos_clima}/4 - {status_clima}")
    return pontos_clima, criterios_clima, status_clima

# --- NOVO SISTEMA DE BUSCA DE ODDS (2 FUNÇÕES) ---
async def buscar_odd_ht(nome_jogo: str) -> (str, int | None):
    """
    Busca a odd para Over 0.5 HT APENAS EM JOGOS AO VIVO usando o endpoint /odds/live
    """
    odd_ht = "N/D"
    fixture_id = await buscar_fixture_id(nome_jogo)
    if not fixture_id:
        return "N/L", None

    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    
    # Endpoint exclusivo para odds AO VIVO
    url_odds = "https://v3.football.api-sports.io/odds/live"
    
    # SEM especificar bookmaker para pegar TODAS as casas de apostas
    params = {"fixture": str(fixture_id)}
    
    logger.info(f"🔎 Buscando APENAS odds AO VIVO para Fixture ID: {fixture_id}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                if resp_odds.status == 200:
                    data_odds = await resp_odds.json()
                    
                    # DEBUG: Log da resposta completa
                    logger.info(f"📋 RESPOSTA COMPLETA /odds/live: {data_odds}")
                    
                    # Verificar primeiro o status do jogo para entender se está ao vivo
                    status_jogo = await verificar_status_jogo(fixture_id)
                    logger.info(f"🎮 Status atual do jogo: {status_jogo}")
                    
                    if data_odds.get('results', 0) > 0 and data_odds.get('response'):
                        response_list = data_odds['response']
                        
                        if not response_list:
                            logger.warning("⚠️ Lista de resposta vazia do /odds/live")
                            return "N/D", fixture_id
                        
                        # A resposta é uma lista de fixtures
                        logger.info(f"📊 Total de fixtures retornados: {len(response_list)}")
                        
                        # Listar TODOS os fixtures retornados para debug
                        fixture_ids_retornados = []
                        for fixture_data in response_list:
                            fixture_response_id = fixture_data.get('fixture', {}).get('id')
                            fixture_ids_retornados.append(fixture_response_id)
                            
                        logger.info(f"🔍 Fixtures retornados do /odds/live: {fixture_ids_retornados}")
                        logger.info(f"🎯 Procurando especificamente pelo fixture: {fixture_id}")
                        
                        fixture_encontrado = False
                        for fixture_data in response_list:
                            fixture_response_id = fixture_data.get('fixture', {}).get('id')
                            logger.info(f"🎯 Processando fixture {fixture_response_id}")
                            
                            # Verificar se é o fixture correto
                            if str(fixture_response_id) != str(fixture_id):
                                logger.info(f"⏭️ Pulando fixture {fixture_response_id} (procurando {fixture_id})")
                                continue
                                
                            fixture_encontrado = True
                            
                            # CORREÇÃO: A estrutura real tem 'odds' diretamente, não 'bookmakers'
                            odds_markets = fixture_data.get('odds', [])
                            logger.info(f"📊 Total de mercados de odds para fixture {fixture_id}: {len(odds_markets)}")
                            
                            if not odds_markets:
                                logger.warning(f"⚠️ Nenhum mercado de odds encontrado para fixture {fixture_id}")
                                logger.info(f"📊 Estrutura do fixture: {fixture_data}")
                                continue
                            
                            # Percorrer TODOS os mercados de odds
                            for i, market in enumerate(odds_markets):
                                market_name = market.get('name', f'Market_{i}')
                                market_id = str(market.get('id', ''))
                                
                                logger.info(f"📈 [{i+1}/{len(odds_markets)}] Mercado: '{market_name}' (ID: {market_id})")
                                
                                # Listar todas as opções do mercado
                                values = market.get('values', [])
                                for k, value in enumerate(values):
                                    value_name = value.get('value', f'Value_{k}')
                                    odd_value = value.get('odd', 'N/A')
                                    handicap = value.get('handicap', '')
                                    logger.info(f"    💰 [{k+1}] '{value_name}' handicap='{handicap}' = {odd_value}")
                                
                                # Buscar mercados HT com critérios MUITO amplos
                                market_name_lower = market_name.lower()
                                
                                # Palavras-chave MUITO abrangentes para HT
                                ht_indicators = [
                                    'first half', '1st half', 'half time', 'half-time',
                                    'ht', '1h', 'primeiro tempo', 'meio tempo', 'intervalo',
                                    'first', 'half', 'tempo', '1º tempo', 'first 45',
                                    '45 min', 'primeros 45', 'primi 45', 'erste'
                                ]
                                
                                # Indicadores de goals/over-under
                                goals_indicators = [
                                    'over/under', 'total', 'goals', 'gols', 'over', 'under',
                                    'acima', 'abaixo', 'mais', 'menos', 'goal', 'gol',
                                    'buts', 'tore', 'mål', 'pero', 'más', 'menos'
                                ]
                                
                                # IDs conhecidos para mercados HT Goals (incluindo o 49 que vimos na resposta)
                                ht_goal_market_ids = [
                                    '8', '9', '25', '26', '27', '28', '37', '38', '39',
                                    '49', '24', '101', '102', '103', '104', '105', '106'
                                ]
                                
                                # Verificações mais flexíveis
                                has_ht_keyword = any(indicator in market_name_lower for indicator in ht_indicators)
                                has_goals_keyword = any(indicator in market_name_lower for indicator in goals_indicators)
                                is_ht_market_id = market_id in ht_goal_market_ids
                                
                                # Se parece ser um mercado de primeiro tempo
                                if has_ht_keyword or is_ht_market_id:
                                    logger.info(f"🎯 POSSÍVEL MERCADO HT: '{market_name}' (ID: {market_id})")
                                    
                                    # Se também tem indicadores de goals, é ainda mais provável
                                    if has_goals_keyword or is_ht_market_id:
                                        logger.info(f"✅ MERCADO HT GOALS CONFIRMADO: '{market_name}'")
                                        
                                        for value in values:
                                            value_name = value.get('value', '').lower()
                                            odd_value = value.get('odd')
                                            handicap = str(value.get('handicap', ''))
                                            
                                            # Buscar Over 0.5 - pode estar no value_name OU no handicap
                                            is_over = 'over' in value_name
                                            is_05_handicap = handicap == '0.5' or handicap == '0,5'
                                            
                                            # Padrões tradicionais no nome
                                            over_05_patterns = [
                                                'over 0.5', 'over 0,5', 'over0.5', 'over0,5',
                                                'mais 0.5', 'mais 0,5', 'acima 0.5', 'acima 0,5',
                                                '> 0.5', '> 0,5', 'more than 0.5', 'mais de 0.5'
                                            ]
                                            
                                            has_over_05_pattern = any(pattern in value_name for pattern in over_05_patterns)
                                            
                                            # Verificar se é Over 0.5 (no nome OU combinação over + handicap 0.5)
                                            if has_over_05_pattern or (is_over and is_05_handicap):
                                                logger.info(f"🎉 OVER 0.5 HT ENCONTRADO! Odd: {odd_value} | Mercado: '{market_name}' | Valor: '{value.get('value')}' | Handicap: '{handicap}'")
                                                return str(odd_value), fixture_id
                                            
                                            # Log valores interessantes para análise
                                            if '0.5' in value_name or '0,5' in value_name or handicap in ['0.5', '0,5']:
                                                logger.info(f"🔍 Valor interessante: '{value.get('value')}' handicap='{handicap}' = {odd_value}")
                        
                        if not fixture_encontrado:
                            logger.error(f"❌ Fixture {fixture_id} NÃO ENCONTRADO na resposta do /odds/live!")
                            logger.info(f"📊 Fixtures disponíveis: {fixture_ids_retornados}")
                            return "N/D", fixture_id
                        
                        logger.warning(f"⚠️ Nenhuma odd Over 0.5 HT encontrada para fixture {fixture_id}")
                        
                    else:
                        logger.warning(f"⚠️ API /odds/live não retornou dados para fixture {fixture_id}")
                        logger.info(f"📊 Results: {data_odds.get('results', 0)}")
                        logger.info(f"📊 Response exists: {bool(data_odds.get('response'))}")
                        
                elif resp_odds.status == 404:
                    logger.warning(f"⚠️ Fixture {fixture_id} não encontrado no endpoint /odds/live (pode não estar ao vivo)")
                    
                    # Verificar status do jogo para confirmar
                    status_jogo = await verificar_status_jogo(fixture_id)
                    logger.info(f"🎮 Status do jogo: {status_jogo}")
                    
                else:
                    logger.error(f"❌ Erro na API /odds/live: Status {resp_odds.status}")
                    error_text = await resp_odds.text()
                    logger.error(f"❌ Resposta: {error_text}")
                    
    except Exception as e:
        logger.error(f"❌ Erro crítico em buscar_odd_ht: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        
    return odd_ht, fixture_id


# Função auxiliar para verificar se o jogo está realmente ao vivo
async def verificar_status_jogo(fixture_id: int) -> str:
    """
    Verifica o status atual do jogo para confirmar se está ao vivo
    """
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url = f"https://v3.football.api-sports.io/fixtures"
    params = {"id": str(fixture_id)}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('response'):
                        fixture_info = data['response'][0]
                        fixture_data = fixture_info.get('fixture', {})
                        status = fixture_data.get('status', {})
                        status_short = status.get('short', 'N/A')
                        status_long = status.get('long', 'N/A')
                        
                        # Informações adicionais do jogo
                        home_team = fixture_info.get('teams', {}).get('home', {}).get('name', 'N/A')
                        away_team = fixture_info.get('teams', {}).get('away', {}).get('name', 'N/A')
                        league = fixture_info.get('league', {}).get('name', 'N/A')
                        
                        logger.info(f"🎮 Jogo: {home_team} vs {away_team}")
                        logger.info(f"🏆 Liga: {league}")
                        logger.info(f"📊 Status: {status_short} - {status_long}")
                        
                        return status_short
                except Exception as e:
                    logger.error(f"❌ Erro ao processar resposta do status: {e}")
    except Exception as e:
        logger.error(f"❌ Erro ao verificar status: {e}")
    
    return "N/A"

async def tarefa_veredito_por_id(fixture_id, msg_original):
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"
    try:
        logger.info(f"⏰ [0.5 HT] Aguardando 35 min para veredito do fixture ID: {fixture_id}")
        await asyncio.sleep(2100)
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]
                        gols_casa = fixture.get('score', {}).get('halftime', {}).get('home')
                        gols_fora = fixture.get('score', {}).get('halftime', {}).get('away')
                        if gols_casa is not None and gols_fora is not None:
                            gols_ht = gols_casa + gols_fora
                            logger.info(f"📊 [0.5 HT] Veredito para {fixture_id}: {gols_ht} gols no HT")
                            resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if gols_ht >= 1 else "R E D ❌"
                        else: logger.warning(f"⚠️ [0.5 HT] Dados de gols no HT indisponíveis para fixture {fixture_id}.")
                    else: logger.warning(f"⚠️ [0.5 HT] API não retornou dados para fixture {fixture_id} na verificação.")
                else:
                    logger.error(f"❌ [0.5 HT] Erro na API ao buscar veredito para {fixture_id}: Status {resp.status}")
                    resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError:
        logger.info(f"Tarefa de veredito (0.5 HT) para fixture {fixture_id} foi cancelada.")
        raise
    except Exception as e:
        logger.error(f"❌ [0.5 HT] Erro crítico na tarefa de veredito para fixture {fixture_id}: {e}")
        resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        if not asyncio.current_task().cancelled():
            logger.info(f"✅ [0.5 HT] Editando mensagem para fixture {fixture_id} com resultado: {resultado_final}")
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try:
                await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode='Markdown')
            except Exception as edit_error:
                logger.error(f"❌ Falha ao editar mensagem para fixture {fixture_id}: {edit_error}")

async def analisar(texto):
    logger.info("📊 Iniciando análise do sinal 'Over 0.5 HT'")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        # Verifica se 'U20' (em maiúsculas ou minúsculas) está no nome do jogo
        if "U20" in jogo.upper():
            logger.info(f"🚫 Sinal para jogo U20 ('{jogo}') ignorado conforme regra.")
            return # Para a execução imediatamente
            
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
            logger.info(f"✅ Pontuação suficiente para '{jogo}'. Buscando odd e fixture ID...")
            odd_ht, fixture_id = await buscar_odd_ht(jogo)
            if pontos_total >= 12: confianca = "MUITO ALTA 🔥 STAKE 1%"
            elif pontos_total >= 10: confianca = "ALTA ✅ STAKE 0.75%"
            elif pontos_clima >= 3: confianca = "MÉDIA-ALTA ⚡ STAKE 0.5%"
            else: confianca = "MÉDIA ⚠️ STAKE 0.25%"
            veredito = f"ENTRAR | CONFIANÇA: {confianca}"
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
                logger.warning(f"Veredito não agendado para '{jogo}' pois o fixture ID não pôde ser encontrado pela API.")
        else:
            logger.info(f"❌ Critérios insuficientes para '{jogo}'. Sinal ignorado sem uso de API.")
    except Exception as e:
        logger.error(f"Erro na análise principal: {e}")

# --- Funções do Bot 2 ((CT) Over Gol) ---
async def verificar_resultado_final_ct(fixture_id, msg_original, goal_line):
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"
    try:
        logger.info(f"⏰ [CT Over {goal_line}] Aguardando 45 min para veredito do fixture ID: {fixture_id}")
        await asyncio.sleep(2700)
        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
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
                            logger.info(f"📊 [CT Over {goal_line}] Veredito para {fixture_id}: Total de Gols={total_gols}")
                            resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if total_gols > goal_line else "R E D ❌"
                        else: logger.warning(f"⚠️ [CT Over {goal_line}] Dados de gols FT indisponíveis para fixture {fixture_id}.")
                    else: logger.warning(f"⚠️ [CT Over {goal_line}] API não retornou dados para fixture {fixture_id} na verificação.")
                else:
                    logger.error(f"❌ [CT Over {goal_line}] Erro na API ao buscar veredito para {fixture_id}: Status {resp.status}")
                    resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError:
        logger.info(f"Tarefa de veredito (CT) para fixture {fixture_id} foi cancelada.")
        raise
    except Exception as e:
        logger.error(f"❌ [CT Over {goal_line}] Erro crítico na tarefa de veredito para fixture {fixture_id}: {e}")
        resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        if not asyncio.current_task().cancelled():
            logger.info(f"✅ [CT Over {goal_line}] Editando mensagem para fixture {fixture_id} com resultado: {resultado_final}")
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try:
                await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto)
            except Exception as edit_error:
                logger.error(f"❌ Falha ao editar mensagem (CT) para fixture {fixture_id}: {edit_error}")

async def processar_sinal_ct(texto_original):
    logger.info("(CT) Over Gol: Iniciando processamento do sinal.")
    try:
        evento_match = re.search(r"Evento:\s*(.+)", texto_original)
        selecao_match = re.search(r"Seleção:\s*(.+)", texto_original)
        if not evento_match or not selecao_match:
            logger.warning("Sinal (CT) sem 'Evento' ou 'Seleção'. Abortando.")
            return
        evento = evento_match.group(1).strip()
        selecao_texto = selecao_match.group(1).strip().split('|')[0].strip()
        goal_line_match = re.search(r"([\d.]+)", selecao_texto)
        if not goal_line_match:
            logger.warning(f"Não foi possível extrair a linha de gol da seleção: '{selecao_texto}'.")
            return
        goal_line = float(goal_line_match.group(1))
        logger.info(f"✅ (CT) Evento: '{evento}' | Seleção: '{selecao_texto}' | Linha de Gol: {goal_line}")
        competicao_match = re.search(r"Competição:\s*(.+)", texto_original)
        mercado_match = re.search(r"Mercado:\s*(.+)", texto_original)
        stake_match = re.search(r"Stake:\s*(.+)", texto_original)
        odd_match = re.search(r"Odd:\s*(.+)", texto_original)
        tipo_match = re.search(r"Tipo:\s*(.+)", texto_original)
        estrategia_match = re.search(r"Estratégia:\s*(.+)", texto_original)
        mercado_texto = mercado_match.group(1).strip().split('|')[0].strip() if mercado_match else "N/A"
        msg_formatada = f"""ANÁLISE OVERBOT VIP CT
Evento: {evento}
Competição: {competicao_match.group(1).strip() if competicao_match else 'N/A'}

Mercado: {mercado_texto}
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
            logger.warning(f"Veredito não agendado para '{evento}' (CT) pois o fixture ID não foi encontrado.")
    except Exception as e:
        logger.error(f"Erro ao processar sinal (CT): {e}")

# --- ROTEADOR E INICIALIZAÇÃO ---
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHAT_ID_SINAL))
async def roteador_de_sinais(event):
    try:
        conteudo = event.message.message
        if not conteudo:
            return
        if "OVER 0.5 HT" in conteudo and "Inteligência Artificial" in conteudo:
            logger.info("Sinal 'OVER 0.5 HT' detectado. Roteando para análise principal.")
            await analisar(conteudo)
        elif "Estratégia: (CT) Over Gol" in conteudo:
            logger.info("Sinal '(CT) Over Gol' detectado. Roteando para processador CT.")
            await processar_sinal_ct(conteudo)
    except Exception as e:
        logger.error(f"Erro no roteador de sinais: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot Unificado de Sinais ativo e escutando!")

async def main():
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
