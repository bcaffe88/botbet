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

async def buscar_fixture_id(nome_jogo: str) -> int | None:
    if not nome_jogo or not FOOTBALL_API_KEY: return None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    time_busca = nome_jogo.split(' x ')[0].strip()
    datas_para_buscar = [
        datetime.now().strftime("%Y-%m-%d"),
        (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    for data_busca in datas_para_buscar:
        logger.info(f"🔎 Buscando fixture com data={data_busca} e search='{time_busca}'")
        url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={data_busca}&search={time_busca}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_fixtures, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("response") and data.get("results", 0) > 0:
                            jogos = data.get("response", [])
                            maior_similaridade = 0.75; fixture_id_encontrado = None
                            for item in jogos:
                                teams = item.get("teams", {}); casa = teams.get("home", {}).get("name", ""); fora = teams.get("away", {}).get("name", ""); nome_match_api = f"{casa} x {fora}"
                                sim = similaridade(nome_jogo, nome_match_api)
                                if sim > maior_similaridade: maior_similaridade = sim; fixture_id_encontrado = item.get("fixture", {}).get("id")
                            if fixture_id_encontrado:
                                logger.info(f"✅ Fixture encontrado na data {data_busca} para '{nome_jogo}': ID {fixture_id_encontrado}")
                                return fixture_id_encontrado
        except Exception as e:
            logger.error(f"Erro em buscar_fixture_id para data {data_busca}: {e}")
            continue
    logger.error(f"❌ Fixture não localizado para '{nome_jogo}' após buscar em 3 dias.")
    return None

# --- Funções do Bot 1 (Análise Climática, Odds, Veredito) ---

def analisar_clima(texto):
    pontos_clima = 0; criterios_clima = []
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
        if temperatura is not None and 18 <= temperatura <= 28: pontos_clima += 1; criterios_clima.append("Temperatura ideal")
        if nebulosidade is not None and nebulosidade >= 20: pontos_clima += 1; criterios_clima.append("Nebulosidade ideal (sem sol forte)")
        if umidade is not None and 50 <= umidade <= 75: pontos_clima += 1; criterios_clima.append("Umidade ideal")
        if vento is not None:
            if vento <= 7: pontos_clima += 1; criterios_clima.append("Vento ótimo")
            elif 7 < vento <= 10: pontos_clima += 0.5; criterios_clima.append("Vento moderado")
    except Exception as e: logger.error(f"Erro na análise climática: {e}")
    if pontos_clima >= 3.5: status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2: status_clima = "🟡 NEUTRO"
    else: status_clima = "🔴 DESFAVORÁVEL"
    logger.info(f"🌤️ Pontuação Climática Final: {pontos_clima}/4 - {status_clima}")
    return pontos_clima, criterios_clima, status_clima

async def buscar_odd_ao_vivo(fixture_id: int, goal_line: float) -> str:
    odd_encontrada = "N/D"
    if not fixture_id: return odd_encontrada
    goal_line_str = str(goal_line).replace('.0', '')
    goal_line_str_comma = goal_line_str.replace('.', ',')
    KEYWORDS_TEMPO = ['first half', '1st half', 'half time', 'ht', '1h', 'meio tempo', 'primeiro tempo', 'intervalo', '1º tempo']
    KEYWORDS_TIPO = ['over/under', 'total', 'goals', 'gols', 'line']
    OVER_PATTERNS = [f'over {goal_line_str}', f'over {goal_line_str_comma}', f'mais {goal_line_str}', f'mais {goal_line_str_comma}', f'> {goal_line_str}', f'> {goal_line_str_comma}']
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    url_odds = "https://v3.football.api-sports.io/odds/live"
    params = {"fixture": str(fixture_id)}
    logger.info(f"🔎 Buscando odd AO VIVO para Over {goal_line} HT no Fixture ID: {fixture_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_odds, headers=headers, params=params) as resp_odds:
                if resp_odds.status == 200:
                    data_odds = await resp_odds.json()
                    if data_odds.get('results', 0) > 0 and data_odds.get('response'):
                        fixture_data = data_odds['response'][0]
                        bookmakers = fixture_data.get('bookmakers', [])
                        if not bookmakers: logger.warning(f"⚠️ Nenhum bookmaker com odds ao vivo encontrado para fixture {fixture_id}"); return odd_encontrada
                        for bookmaker in bookmakers:
                            for market in bookmaker.get('bets', []):
                                market_name = market.get('name', '').lower()
                                if any(kw in market_name for kw in KEYWORDS_TEMPO) and any(kw in market_name for kw in KEYWORDS_TIPO):
                                    for value in market.get('values', []):
                                        value_name = value.get('value', '').lower().replace(',', '.')
                                        if any(pattern in value_name for pattern in OVER_PATTERNS):
                                            odd_value = value.get('odd'); logger.info(f"🎉 ODD AO VIVO ENCONTRADA (Over {goal_line} HT): {odd_value}"); return str(odd_value)
                        logger.warning(f"⚠️ Odd 'Over {goal_line} HT' não encontrada nos mercados para fixture {fixture_id}.")
                    else: logger.warning(f"⚠️ API /odds/live não retornou dados para fixture {fixture_id} (results: 0).")
                else: logger.error(f"❌ Erro na API /odds/live: Status {resp_odds.status}")
    except Exception as e: logger.error(f"❌ Erro crítico em buscar_odd_ao_vivo: {e}")
    return odd_encontrada

async def verificar_placar_ht_ao_vivo(fixture_id: int) -> int | None:
    if not fixture_id: return None
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
                        gols_casa = fixture.get('score', {}).get('halftime', {}).get('home')
                        gols_fora = fixture.get('score', {}).get('halftime', {}).get('away')
                        if gols_casa is not None and gols_fora is not None:
                            total_gols = gols_casa + gols_fora; logger.info(f"✅ Placar HT atual: {total_gols} gols."); return total_gols
                        else: logger.warning(f"⚠️ Placar HT indisponível na API. Assumindo 0 gols."); return 0
                else: logger.error(f"❌ Erro ao verificar placar: Status {resp.status}")
    except Exception as e: logger.error(f"❌ Erro crítico ao verificar placar: {e}")
    return None

async def tarefa_veredito_por_id(fixture_id, msg_original):
    resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"; try:
        logger.info(f"⏰ [0.5 HT] Aguardando 35 min para veredito do fixture ID: {fixture_id}"); await asyncio.sleep(2100)
        headers = {"x-apisports-key": FOOTBALL_API_KEY}; url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('results', 0) > 0:
                        fixture = data['response'][0]; gols_casa = fixture.get('score', {}).get('halftime', {}).get('home'); gols_fora = fixture.get('score', {}).get('halftime', {}).get('away')
                        if gols_casa is not None and gols_fora is not None: gols_ht = gols_casa + gols_fora; resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅" if gols_ht >= 1 else "R E D ❌"
                        else: logger.warning(f"⚠️ [0.5 HT] Dados de gols no HT indisponíveis na verificação final.")
                    else: logger.warning(f"⚠️ [0.5 HT] API não retornou dados para fixture na verificação final.")
                else: resultado_final = "⏳ ERRO NA API"
    except asyncio.CancelledError: logger.info(f"Tarefa de veredito (0.5 HT) para fixture {fixture_id} foi cancelada."); raise
    except Exception as e: logger.error(f"❌ [0.5 HT] Erro crítico na tarefa de veredito: {e}"); resultado_final = "⏳ ERRO AO VERIFICAR"
    finally:
        if not asyncio.current_task().cancelled():
            novo_texto = f"{msg_original.text}\n\n───────────────\n{resultado_final}"
            try: await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode='Markdown')
            except Exception as edit_error: logger.error(f"❌ Falha ao editar mensagem para fixture {fixture_id}: {edit_error}")

async def analisar(texto):
    """Função de análise principal com a estratégia adaptativa "Over Gol Limite" e formatação distinta."""
    logger.info("📊 Iniciando análise do sinal 'Over 0.5 HT'")
    try:
        # Etapa 1: Extração de dados e pontuação
        jogo_match = re.search(r'⚽️\s*(.+)', texto); jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        if "U20" in jogo.upper(): logger.info(f"🚫 Sinal para jogo U20 ('{jogo}') ignorado."); return
        
        logger.info(f"📌 Jogo detectado: {jogo}")
        minuto_match = re.search(r"⏰\s*(\d+)", texto); minuto = int(minuto_match.group(1)) if minuto_match else None
        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%\s*/\s*([\d.]+)%", texto); ia = None
        if ia_match: ia = max(map(float, ia_match.groups()))
        else:
            ia_match_antigo = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
            if ia_match_antigo: ia = float(ia_match_antigo.group(1))
        
        match_perigosos = re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto); perigosos = list(map(int, match_perigosos[0])) if match_perigosos else [0, 0]
        match_posse = re.findall(r"Posse de Bola:\s*(\d+)%\s*/\s*(\d+)%", texto); posse = list(map(int, match_posse[0])) if match_posse else [0, 0]
        match_escanteios = re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto); escanteios = list(map(int, match_escanteios[0])) if match_escanteios else [0, 0]
        match_no_gol = re.findall(r"No Gol:\s*(\d+)/(\d+)", texto); no_gol = list(map(int, match_no_gol[0])) if match_no_gol else [0, 0]
        match_chutes = re.findall(r"Total:\s*(\d+)/(\d+)", texto); chutes = list(map(int, match_chutes[0])) if match_chutes else [0, 0]

        pontos_clima, _, status_clima = analisar_clima(texto); criterios_tecnicos = []; pontos_tecnicos = 0
        if ia and ia >= 70: criterios_tecnicos.append("IA favorável"); pontos_tecnicos += 2
        if minuto and 16 <= minuto <= 22: criterios_tecnicos.append("Minuto ideal"); pontos_tecnicos += 1
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7: criterios_tecnicos.append("Ataques perigosos"); pontos_tecnicos += 2
        if sum(no_gol) >= 1: criterios_tecnicos.append("Finalizações no gol"); pontos_tecnicos += 2
        if sum(escanteios) >= 2: criterios_tecnicos.append("Escanteios"); pontos_tecnicos += 1
        if sum(chutes) >= 4: criterios_tecnicos.append("Chutes suficientes"); pontos_tecnicos += 1
        if posse[0] >= 60 or posse[1] >= 60: criterios_tecnicos.append("Posse dominante"); pontos_tecnicos += 1
        
        pontos_total = pontos_tecnicos + pontos_clima
        deve_entrar = pontos_total >= 9.0
        logger.info(f"📈 Pontos Técnicos: {pontos_tecnicos}/10 | 🌤️ Pontos Clima: {pontos_clima}/4 | 🎯 Total: {pontos_total}")

        if deve_entrar:
            logger.info(f"✅ Pontuação suficiente para '{jogo}'. Iniciando validação com API...")
            fixture_id = await buscar_fixture_id(jogo)
            
            # --- LÓGICA DE FORMATAÇÃO E ENVIO CONDICIONAL ---
            
            # Define a confiança primeiro, pois é usada em ambos os casos
            if pontos_total >= 12: confianca = "MUITO ALTA 🔥 STAKE 1%"
            elif pontos_total >= 10: confianca = "ALTA ✅ STAKE 0.75%"
            else: confianca = "MÉDIA ⚠️ STAKE 0.25%"

            resumo_clima = f" {status_clima} ({pontos_clima}/4pts)"; resumo_tecnico = f" {pontos_tecnicos}/10pts"
            
            # Se não encontrou o fixture, envia o sinal padrão de Over 0.5 HT sem dados da API
            if not fixture_id:
                odd_ht = "N/D"
                veredito = f"ENTRAR | CONFIANÇA: {confianca}"
                msg = f"""⚽️ {veredito}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD ATUAL: *{odd_ht}*\n▶️ ENTRADA: OVER 0.5 HT"""
                await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
                logger.info(f"✅ Sinal enviado para '{jogo}' (sem dados da API).")
                logger.warning(f"Veredito não agendado para '{jogo}' pois o fixture ID não pôde ser encontrado.")
                return

            # Se encontrou o fixture, aplica a lógica "Over Gol Limite"
            gols_ht_atuais = await verificar_placar_ht_ao_vivo(fixture_id)
            
            if gols_ht_atuais is not None and gols_ht_atuais >= 3:
                logger.info(f"🚫 SINAL INVÁLIDO! Jogo '{jogo}' já tem 3 ou mais gols no 1º tempo. Ignorando.")
                return
            
            mercado_alvo = f"Over {gols_ht_atuais + 0.5} HT"
            goal_line_alvo = gols_ht_atuais + 0.5
            odd_ht = await buscar_odd_ao_vivo(fixture_id, goal_line_alvo)

            # Formatação distinta baseada no placar
            if gols_ht_atuais > 0:
                veredito = f"ENTRADA LIMITE | CONFIANÇA: {confianca}"
                aviso_teste = "\n\n⚠️ *Estratégia 'Over Limite' em teste. Faça sua própria análise (DYOR).*"
            else:
                veredito = f"ENTRAR | CONFIANÇA: {confianca}"
                aviso_teste = ""

            msg = f"""⚽️ {veredito}\n🏟️ {jogo}\n🤖 OVERBOT ANÁLISE:\n⚽ CRITÉRIOS ATENDIDOS: {resumo_tecnico} \n🌤️ CLIMA: {resumo_clima}\n📊 ODD ATUAL: *{odd_ht}*\n▶️ ENTRADA: {mercado_alvo}{aviso_teste}"""
            
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, parse_mode='Markdown')
            logger.info(f"✅ Sinal '{mercado_alvo}' enviado para: {jogo}")
            asyncio.create_task(tarefa_veredito_por_id(fixture_id, msg_enviada))

        else:
            logger.info(f"❌ Critérios insuficientes para '{jogo}'. Sinal ignorado sem uso de API.")
    except Exception as e:
        logger.error(f"Erro na análise principal: {e}"); logger.error(traceback.format_exc())

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
    # --- CÓDIGO ATUALIZADO AQUI ---
    try:
        conteudo = event.message.message
        if not conteudo:
            return
        
        ESTRATEGIAS_DE_ENCAMINHAMENTO = [
            "Estratégia: (CT) Over Gol",
            "Estratégia: Over HT/FT" # Corrigido: Emoji removido
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
