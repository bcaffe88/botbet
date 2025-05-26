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

# FUNÇÃO DE ANÁLISE CLIMÁTICA ATUALIZADA
def analisar_clima(texto):
    """Analisa condições climáticas e retorna pontuação"""
    pontos_clima = 0
    criterios_clima = []
    detalhes_clima = {}

    try:
        # Expressão regular robusta com grupos nomeados
        clima_match = re.search(
            r"🌡️\s*(?P<temp>[\d.]+)\s*°C\s*(?:\||-)?\s*☁\s*☁️\s*(?P<nuvens>[\d.]+)%\s*(?:\||-)?\s*💧\s*(?P<umidade>[\d.]+)%\s*(?:\||-)?\s*💨\s*(?P<vento>[\d.]+)\s*m/s",
            texto,
            re.DOTALL
        )

        if clima_match:
            temperatura = float(clima_match.group("temp"))
            nebulosidade = float(clima_match.group("nuvens"))
            umidade = float(clima_match.group("umidade"))
            vento = float(clima_match.group("vento"))

            detalhes_clima = {
                'temperatura': temperatura,
                'nebulosidade': nebulosidade,
                'umidade': umidade,
                'vento': vento
            }

            # Análise Temperatura (18°C a 28°C)
            if 18 <= temperatura <= 28:
                pontos_clima += 1
                criterios_clima.append("Temperatura ideal")

            # Análise Nebulosidade (20% a 70%)
            if 20 <= nebulosidade <= 70:
                pontos_clima += 1
                criterios_clima.append("Nebulosidade ideal")

            # Análise Umidade (50% a 75%)
            if 50 <= umidade <= 75:
                pontos_clima += 1
                criterios_clima.append("Umidade ideal")

            # Análise Vento
            if vento <= 7:
                pontos_clima += 1
                criterios_clima.append("Vento ótimo")
            elif 7 < vento <= 10:
                pontos_clima += 0.5
                criterios_clima.append("Vento moderado")

            logger.info(f"🌤️ Análise Climática:")
            logger.info(f"  • Temperatura: {temperatura}°C → {'✅' if 18 <= temperatura <= 28 else '❌'}")
            logger.info(f"  • Nebulosidade: {nebulosidade}% → {'✅' if 20 <= nebulosidade <= 70 else '❌'}")
            logger.info(f"  • Umidade: {umidade}% → {'✅' if 50 <= umidade <= 75 else '❌'}")
            logger.info(f"  • Vento: {vento} m/s → {'✅' if vento <= 7 else '⚠️' if vento <= 10 else '❌'}")

        else:
            logger.warning("❌ Não foi possível extrair dados climáticos completos. Verifique o padrão da mensagem.")

    except Exception as e:
        logger.error(f"Erro na análise climática: {e}")

    # Classificação do clima
    if pontos_clima >= 3.5:
        status_clima = "🟢 FAVORÁVEL"
    elif pontos_clima >= 2:
        status_clima = "🟡 NEUTRO"
    else:
        status_clima = "🔴 DESFAVORÁVEL"

    logger.info(f"🌤️ Pontuação Climática: {pontos_clima}/4 - {status_clima}")

    return pontos_clima, criterios_clima, detalhes_clima, status_clima

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
        await update.message.reply_text("🤖 Bot de sinais refinados com análise climática ativo!")
        logger.info(f"Comando /start executado por {update.effective_user.username}")
    except Exception as e:
        logger.error(f"Erro no comando /start: {e}")

# Tarefa de veredito após 35 minutos (2100 segundos)
async def tarefa_veredito(jogo, msg_original):
    """Executa verificação do resultado após 35 minutos"""
    try:
        logger.info(f"⏰ Aguardando 35 minutos para verificar resultado de: {jogo}")
        await asyncio.sleep(2100)  # 35 minutos = 2100 segundos
        
        resultado = await verificar_gol_ht(jogo)
        logger.info(f"📊 Result para {jogo}: {resultado}")

        if resultado == "✅ BATEU":
            resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅"
        elif resultado == "❌ NÃO BATEU":
            resultado_final = "R E D ❌"
        else:
            resultado_final = "⏳ RESULTADO NÃO LOCALIZADO"

        novo_texto = f"""{msg_original.text}

───────────────
{resultado_final}"""

        await bot.edit_message_text(
            chat_id=CHAT_ID_DESTINO,
            message_id=msg_original.message_id,
            text=novo_texto
        )
        logger.info(f"✅ Veredito atualizado para: {jogo}")
        
    except Exception as e:
        logger.error(f"Erro na tarefa de veredito: {e}")

# FUNÇÃO DE ANÁLISE PRINCIPAL ATUALIZADA
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

        # NOVA ANÁLISE CLIMÁTICA
        pontos_clima, criterios_clima, detalhes_clima, status_clima = analisar_clima(texto)

        # Análise dos critérios técnicos
        criterios_tecnicos = []
        pontos_tecnicos = 0

        # Critério IA
        if ia and ia >= 70:
            criterios_tecnicos.append("IA favorável")
            pontos_tecnicos += 2

        # Critério minuto
        if minuto and 16 <= minuto <= 22:
            criterios_tecnicos.append("Minuto ideal")
            pontos_tecnicos += 1

        # Critério ataques perigosos
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            criterios_tecnicos.append("Ataques perigosos")
            pontos_tecnicos += 2

        # Critério finalizações no gol
        if sum(no_gol) >= 1:
            criterios_tecnicos.append("Finalizações no gol")
            pontos_tecnicos += 2

        # Critério escanteios
        if sum(escanteios) >= 2:
            criterios_tecnicos.append("Escanteios")
            pontos_tecnicos += 1

        # Critério chutes totais
        if sum(chutes) >= 4:
            criterios_tecnicos.append("Chutes suficientes")
            pontos_tecnicos += 1

        # Critério posse dominante
        if posse[0] >= 60 or posse[1] >= 60:
            criterios_tecnicos.append("Posse dominante")
            pontos_tecnicos += 1

        # SISTEMA DE PONTUAÇÃO INTEGRADO
        pontos_total = pontos_tecnicos + pontos_clima
        max_pontos_tecnicos = 10  # Máximo possível dos critérios técnicos
        max_pontos_clima = 4      # Máximo possível dos critérios climáticos
        max_pontos_total = max_pontos_tecnicos + max_pontos_clima  # 14 pontos totais

        # Todos os critérios atendidos
        todos_criterios = criterios_tecnicos + criterios_clima

        logger.info(f"📈 Pontuação Técnica: {pontos_tecnicos}/{max_pontos_tecnicos}")
        logger.info(f"🌤️ Pontuação Climática: {pontos_clima}/{max_pontos_clima} - {status_clima}")
        logger.info(f"🎯 Pontuação Total: {pontos_total}/{max_pontos_total}")
        logger.info(f"📋 Critérios Técnicos: {', '.join(criterios_tecnicos) if criterios_tecnicos else 'Nenhum'}")
        logger.info(f"🌤️ Critérios Climáticos: {', '.join(criterios_clima) if criterios_clima else 'Nenhum'}")

        # LÓGICA DE DECISÃO INTEGRADA
        # Critério flexível: 64% da pontuação total (9.0 pontos de 14)
        # Ou pelo menos 7 pontos técnicos + clima favorável/neutro
        limite_minimo = 9.0  # ~64% de 14 pontos
        
        condicao1 = pontos_total >= limite_minimo
        condicao2 = pontos_tecnicos >= 7 and pontos_clima >= 2  # Técnicos bons + clima pelo menos neutro
        condicao3 = pontos_tecnicos >= 8 and pontos_clima >= 1.5  # Técnicos muito bons + clima razoável
        
        deve_entrar = condicao1 or condicao2 or condicao3

        if deve_entrar:
            # Determinar nível de confiança
            if pontos_total >= 12:
                confianca = "MUITO ALTA 🔥"
            elif pontos_total >= 10:
                confianca = "ALTA ✅"
            elif pontos_clima >= 3:
                confianca = "MÉDIA-ALTA ⚡"
            else:
                confianca = "MÉDIA ⚠️"
            
            veredito = f"ENTRAR {confianca}"
            conclusao = "OVER 0.5 HT"

            # Preparar resumo para a mensagem
            resumo_clima = f"🌤️ {status_clima} ({pontos_clima}/4pts)"
            resumo_tecnico = f"⚽ {pontos_tecnicos}/10pts"
            
            msg = f"""⚽️ {veredito}
🏟️ {jogo}
🤖 OVERBOT VIP CLIMÁTICO

📊 ANÁLISE:
{resumo_tecnico} | {resumo_clima}
🎯 Total: {pontos_total}/14pts

▶️ ENTRADA: {conclusao}
⏰ Aguardando resultado..."""

            try:
                msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
                logger.info("✅ Sinal de entrada enviado com sucesso")
                
                # Agendar verificação do resultado
                asyncio.create_task(tarefa_veredito(jogo, msg_enviada))
                
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem: {e}")
        else:
            logger.info(f"❌ Critérios insuficientes. Pontuação: {pontos_total}/{max_pontos_total} (mín: {limite_minimo})")
            logger.info(f"   • Técnicos: {pontos_tecnicos}/{max_pontos_tecnicos}")
            logger.info(f"   • Climáticos: {pontos_clima}/{max_pontos_clima}")

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
        logger.info("🚀 Iniciando Bot de Sinais com Análise Climática")
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
