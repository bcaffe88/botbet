import os
import re
import unicodedata
import asyncio
from datetime import datetime
from difflib import SequenceMatcher

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import aiohttp

from estatisticas_time import resumo_estatistico, resumo_estendido

# CONFIGURAÇÕES
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")

bot = Bot(token=BOT_TOKEN)

# UTILITÁRIOS
def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

# API-FOOTBALL - Verifica gol no HT
async def verificar_gol_ht(nome_jogo):
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY
    }
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                jogos = data.get("response", [])

                print(f"📅 {len(jogos)} jogos encontrados na API-Football em {data_hoje}")
                for item in jogos:
                    teams = item["teams"]
                    halftime = item["score"]["halftime"]

                    casa = teams["home"]["name"]
                    fora = teams["away"]["name"]
                    nome_match = f"{casa} x {fora}"
                    print(f"- {nome_match}")

                    if similaridade(normalizar(nome_jogo), normalizar(nome_match)) > 0.75:
                        gols_ht = (halftime["home"] or 0) + (halftime["away"] or 0)
                        print(f"🔍 Comparando: {nome_jogo} ≈ {nome_match} | Gols HT: {gols_ht}")
                        return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
    except Exception as e:
        print("❌ Erro ao consultar API-Football:", e)

    return "⏳ NÃO LOCALIZADO"
    
# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais refinados ativo!")

# Tarefa de veredito após 25 minutos
async def tarefa_veredito(jogo, msg_original):
    await asyncio.sleep(1500)
    resultado = await verificar_gol_ht(jogo)

    if resultado == "✅ BATEU":
        resultado_final = "G R E N N ✅✅✅✅✅✅✅✅✅✅ "
    elif resultado == "❌ NÃO BATEU":
        resultado_final = "R E D ❌"
    else:
        resultado_final = "⏳ BUSCANDO RESULTADO*"

    novo_texto = f"""{msg_original.text}

{resultado_final}"""

    await bot.edit_message_text(
        chat_id=CHAT_ID_DESTINO,
        message_id=msg_original.message_id,
        text=novo_texto,
        parse_mode="Markdown"
    )

# Análise do sinal
async def analisar(texto):
    print("📊 Iniciando análise do sinal")
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        print(f"📌 Jogo detectado: {jogo}")

        try:
            nome_mandante, nome_visitante = jogo.split(" x ")
            historico = resumo_estatistico(nome_mandante.strip(), nome_visitante.strip())
            liga_info = resumo_estendido(nome_mandante.strip())
        except Exception as e:
            print(f"⚠️ Erro ao gerar histórico: {e}")
            historico = "⚠️ Histórico indisponível"
            liga_info = "⚠️ Info da liga indisponível"

    except Exception as e:
        print("❌ Erro ao extrair dados do jogo:", e)
        jogo = "Times não identificados"
        historico = "⚠️ Histórico indisponível"
        liga_info = "⚠️ Info da liga indisponível"

    
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

        criterios, resumo = [], []
        pontos = 0

        if ia and ia >= 75:
            criterios.append("IA")
            pontos += 2
        resumo.append(f"• IA: {ia}%")

        if minuto and 16 <= minuto <= 22:
            criterios.append("Minuto ideal")
            pontos += 1

        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            criterios.append("Ataques perigosos")
            pontos += 2

        if sum(no_gol) >= 1:
            criterios.append("Finalizações no gol")
            pontos += 2

        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
            pontos += 1

        if vento and vento < 15:
            criterios.append("Vento ideal")
            pontos += 1

        if sum(chutes) >= 4:
            criterios.append("Chutes totais")
            pontos += 1

        if posse[0] >= 60 or posse[1] >= 60:
            criterios.append("Posse dominante")
            pontos += 1

        if pontos >= 7:
            veredito = "ENTRAR ✅"
            conclusao = "OVER 0.5 HT."

            msg = f"""⚽️ {veredito} 
🏟 {jogo}
🤖 OVERBOT VIP:
{chr(10).join(resumo)}
{liga_info}
▶ ENTRADA: {conclusao}
📊 Histórico:
{historico}

"""

            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
            asyncio.create_task(tarefa_veredito(jogo, msg_enviada))
        else:
            print("❌ Veredito não é 'ENTRAR'. Nenhum envio será feito.")

    except Exception as e:
        print("❌ Erro ao analisar:", e)

# MONITOR TELETHON
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    print(f"📨 Mensagem recebida de {event.chat_id}:")
    print(event.message.message)

    if str(event.chat_id) == str(CHAT_ID_SINAL) and "OVER 0.5 HT" in event.message.message:
        print("✅ Sinal detectado, enviando para análise.")
        await analisar(event.message.message)
    else:
        print("⚠️ Mensagem ignorada.")

# INICIALIZAÇÃO
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    client.start()
    app.run_polling()

    client.start()
    app.run_polling()
