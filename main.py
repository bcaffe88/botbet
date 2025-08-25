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
import traceback

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
    # (Sua função original aqui, sem alterações)
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

async def buscar_odd_ht(nome_jogo: str) -> (str, int | None):
    # (Mantendo a versão de depuração detalhada)
    odd_ht = "N/D"
    fixture_id = await buscar_fixture_id(nome_jogo)
    if not fixture_id:
        return "N/L", None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url_odds = "https://v3.football.api-sports.io/odds/live"
    params = {"fixture": str(fixture_id)}
    logger.info(f"🔎 Buscando APENAS odds AO VIVO para Fixture ID: {fixture_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                if resp_odds.status == 200:
                    data_odds = await resp_odds.json()
                    logger.info(f"📋 RESPOSTA COMPLETA /odds/live: {data_odds}")
                    if data_odds.get('results', 0) > 0 and data_odds.get('response'):
                        response_list = data_odds['response']
                        if not response_list:
                            logger.warning("⚠️ Lista de resposta vazia do /odds/live")
                            return "N/D", fixture_id
                        fixture_data = response_list[0]
                        bookmakers = fixture_data.get('bookmakers', [])
                        if not bookmakers:
                            logger.warning(f"⚠️ Nenhum bookmaker encontrado para fixture {fixture_id}")
                            return "N/D", fixture_id
                        for bookmaker in bookmakers:
                            for market in bookmaker.get('bets', []):
                                market_name = market.get('name', '').lower()
                                ht_indicators = ['first half', '1st half', 'half time', 'ht', '1h', 'primeiro tempo', 'intervalo', '1º tempo']
                                goals_indicators = ['over/under', 'total', 'goals', 'gols', 'line']
                                over_05_patterns = ['over 0.5', 'over 0,5', 'mais 0.5', 'mais 0,5', '> 0.5', '> 0,5']
                                if any(kw in market_name for kw in ht_indicators) and any(kw in market_name for kw in goals_indicators):
                                    logger.info(f"🎯 Mercado HT compatível encontrado: '{market.get('name')}' (Casa: {bookmaker.get('name')})")
                                    for value in market.get('values', []):
                                        value_name = value.get('value', '').lower().replace(',', '.')
                                        if any(pattern in value_name for pattern in over_05_patterns):
                                            odd_value = value.get('odd')
                                            logger.info(f"🎉 OVER 0.5 HT ENCONTRADO! Odd: {odd_value}")
                                            return str(odd_value), fixture_id
                        logger.warning(f"⚠️ Fixture {fixture_id} processado, mas nenhuma odd 'Over 0.5 HT' foi encontrada.")
                    else:
                        logger.warning(f"⚠️ API /odds/live não retornou dados para fixture {fixture_id} (results: 0).")
                else:
                    logger.error(f"❌ Erro na API /odds/live: Status {resp_odds.status}")
    except Exception as e:
        logger.error(f"❌ Erro crítico em buscar_odd_ht: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
    return "N/D", fixture_id

async def tarefa_veredito_por_id(fixture_id, msg_original):
    # (Sua função original aqui, sem alterações)
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
                            resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if gols_ht >= 1 else "R E D ❌"
                        else: logger.warning(f"⚠️ [0.5 HT] Dados de gols no HT indisponíveis para fixture {fixture_id}.")
                    else: logger.warning(f"⚠️ [0.5 HT] API não retornou dados para fixture {fixture_id} na verificação.")
                else:
                    resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError:
        logger.info(f"Tarefa de veredito (0.5 HT) para fixture {fixture_id} foi cancelada.")
        raise
    except Exception as e:
        logger.error(f"❌ [0.5 HT] Erro crítico na tarefa de veredito para fixture {fixture_id}: {e}")
        resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        if not asyncio.current_task().cancelled():
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try:
                await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode='Markdown')
            except Exception as edit_error:
                logger.error(f"❌ Falha ao editar mensagem para fixture {fixture_id}: {edit_error}")

async def analisar(texto):
    """
    Função de análise principal com lógica de extração e pontuação CORRIGIDA e MAIS ROBUSTA.
    """
    logger.info("📊 Iniciando análise do sinal 'Over 0.5 HT'")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        if "U20" in jogo.upper():
            logger.info(f"🚫 Sinal para jogo U20 ('{jogo}') ignorado conforme regra.")
            return
            
        logger.info(f"📌 Jogo detectado: {jogo}")
        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None
        
        # Lógica de IA (mantida)
        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%\s*/\s*([\d.]+)%", texto)
        ia = None
        if ia_match:
            ia = max(map(float, ia_match.groups()))
        else:
            ia_match_antigo = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
            if ia_match_antigo: ia = float(ia_match_antigo.group(1))
        
        # Extração de estatísticas
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

        # --- CORREÇÃO 1: Cálculo robusto dos chutes totais ---
        # Em vez de procurar "Total:", somamos os chutes no gol e fora do gol.
        chutes = [no_gol[0] + fora_gol[0], no_gol[1] + fora_gol[1]]
        
        pontos_clima, criterios_clima, status_clima = analisar_clima(texto)
        
        criterios_tecnicos = []
        pontos_tecnicos = 0
        if ia and ia >= 70: criterios_tecnicos.append("IA favorável"); pontos_tecnicos += 2
        if minuto and 16 <= minuto <= 22: criterios_tecnicos.append("Minuto ideal"); pontos_tecnicos += 1
        
        # --- CORREÇÃO 2: Regra de Ataques Perigosos mais flexível ---
        # Agora pontua se a SOMA for alta OU se houver um DOMÍNIO claro.
        soma_perigosos = sum(perigosos)
        diff_perigosos = abs(perigosos[0] - perigosos[1])
        if soma_perigosos >= 15 or (soma_perigosos >= 10 and diff_perigosos >= 5):
            criterios_tecnicos.append("Ataques perigosos")
            pontos_tecnicos += 2

        if sum(no_gol) >= 1: criterios_tecnicos.append("Finalizações no gol"); pontos_tecnicos += 2
        if sum(escanteios) >= 2: criterios_tecnicos.append("Escanteios"); pontos_tecnicos += 1
        if sum(chutes) >= 4: criterios_tecnicos.append("Chutes suficientes"); pontos_tecnicos += 1
        if posse[0] >= 60 or posse[1] >= 60: criterios_tecnicos.append("Posse dominante"); pontos_tecnicos += 1
        
        pontos_total = pontos_tecnicos + pontos_clima
        limite_minimo = 9.0
        deve_entrar = pontos_total >= limite_minimo

        logger.info(f"📈 Pontuação Técnica: {pontos_tecnicos}/10 | 🌤️ Pontuação Climática: {pontos_clima}/4 | 🎯 Pontuação Total: {pontos_total}")

        if deve_entrar:
            # (O resto da sua função de envio e agendamento de veredito continua aqui, sem alterações)
            logger.info(f"✅ Pontuação suficiente para '{jogo}'. Buscando odd e fixture ID...")
            odd_ht, fixture_id = await buscar_odd_ht(jogo)
            if pontos_total >= 12: confianca = "MUITO ALTA 🔥 STAKE 1%"
            elif pontos_total >= 10: confianca = "ALTA ✅ STAKE 0.75%"
            elif pontos_clima >= 3: confianca = "MÉDIA-ALTA ⚡ STAKE 0.5%"
            else: confianca = "MÉDIA ⚠️ STAKE 0.25%"
            veredito = f"ENTRAR | CONFIANÇA: {confianca}"
            resumo_clima = f" {status_clima} ({pontos_clima}/4pts)"
            resumo_tecnico = f" {pontos_tecnicos}/10pts"
            msg = f"""⚽️ {veredito}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD ATUAL: *{odd_ht}*\n▶️ ENTRADA: OVER 0.5 HT"""
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
    # (Seu código original completo aqui, sem alterações)
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"
    try:
        logger.info(f"⏰ [CT Over {goal_line}] Aguardando 45 min para veredito do fixture ID: {fixture_id}")
        await asyncio.sleep(3600)
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
                            resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if total_gols > goal_line else "R E D ❌"
                        else: logger.warning(f"⚠️ [CT Over {goal_line}] Dados de gols FT indisponíveis.")
                    else: logger.warning(f"⚠️ [CT Over {goal_line}] API não retornou dados para fixture.")
                else:
                    resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError:
        logger.info(f"Tarefa de veredito (CT) para fixture {fixture_id} foi cancelada.")
        raise
    except Exception as e:
        logger.error(f"❌ [CT Over {goal_line}] Erro na tarefa de veredito: {e}")
        resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        if not asyncio.current_task().cancelled():
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try:
                await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto)
            except Exception as edit_error:
                logger.error(f"❌ Falha ao editar mensagem (CT): {edit_error}")

async def processar_sinal_ct(texto_original):
    # (Seu código original completo aqui, sem alterações)
    ID_PARA_IGNORAR = "1221386"
    if ID_PARA_IGNORAR in texto_original:
        logger.info(f"🚫 Sinal (CT) ignorado pois contém o ID de Seleção proibido: {ID_PARA_IGNORAR}")
        return
    logger.info("(CT) Over Gol: Iniciando processamento do sinal.")
    try:
        evento_match = re.search(r"Evento:\s*(.+)", texto_original)
        selecao_match = re.search(r"Seleção:\s*(.+)", texto_original)
        if not evento_match or not selecao_match:
            logger.warning("Sinal (CT) sem 'Evento' ou 'Seleção'. Abortando.")
            return
        evento = evento_match.group(1).strip()
        if "U20" in evento.upper():
            logger.info(f"🚫 Sinal (CT) para jogo U20 ('{evento}') ignorado.")
            return
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
        msg_formatada = f"""ANÁLISE OVERBOT VIP CT\nEvento: {evento}\nCompetição: {competicao_match.group(1).strip() if competicao_match else 'N/A'}\n\nMercado: {mercado_texto}\nSeleção: {selecao_texto}\nStake: {stake_match.group(1).strip() if stake_match else 'N/A'}\nOdd: {odd_match.group(1).strip() if odd_match else 'N/A'}\nTipo: {tipo_match.group(1).strip() if tipo_match else 'N/A'}\n\nEstratégia: {estrategia_match.group(1).strip() if estrategia_match else 'N/A'}"""
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
    # (Seu código original completo aqui, sem alterações)
    try:
        conteudo = event.message.message
        if not conteudo:
            return
        ESTRATEGIAS_DE_ENCAMINHAMENTO = [
            "Estratégia: (CT) Over Gol",
            "Estratégia: Over HT/FT"
        ]
        if "OVER 0.5 HT" in conteudo and "Inteligência Artificial" in conteudo:
            logger.info("Sinal 'OVER 0.5 HT' detectado. Roteando para análise principal.")
            await analisar(conteudo)
        elif any(estrategia in conteudo for estrategia in ESTRATEGIAS_DE_ENCAMINHAMENTO):
            matched_strategy = next((s for s in ESTRATEGIAS_DE_ENCAMINHAMENTO if s in conteudo), "N/A")
            logger.info(f"Sinal de encaminhamento '{matched_strategy}' detectado. Roteando para processador CT.")
            await processar_sinal_ct(conteudo)
    except Exception as e:
        logger.error(f"Erro no roteador de sinais: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot Unificado de Sinais ativo e escutando!")

async def main():
    # (Seu código original completo aqui, sem alterações)
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
    except Exception as e:
        logger.error(f"Erro na inicialização: {e}")
