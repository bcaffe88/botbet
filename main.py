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

def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

async def verificar_gol_ht(nome_jogo):
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                jogos = data.get("response", [])
                for item in jogos:
                    casa = item["teams"]["home"]["name"]
                    fora = item["teams"]["away"]["name"]
                    halftime = item["score"]["halftime"]
                    nome_match = f"{casa} x {fora}"
                    if similaridade(normalizar(nome_jogo), normalizar(nome_match)) > 0.75:
                        gols_ht = (halftime["home"] or 0) + (halftime["away"] or 0)
                        return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
    except Exception as e:
        print("❌ Erro ao consultar API-Football:", e)
    return "⏳ NÃO LOCALIZADO"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais refinados ativo!")

async def tarefa_veredito(jogo, msg_original):
    await asyncio.sleep(1500)
    resultado = await verificar_gol_ht(jogo)
    resultado_final = "✅✅✅ GREEN ✅✅✅" if resultado == "✅ BATEU" else ("❌ RED ❌" if resultado == "❌ NÃO BATEU" else "⏳ BUSCANDO RESULTADO*")
    novo_texto = f"{msg_original.text}\n\n{resultado_final}"
    await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode="Markdown")

async def analisar(texto):
    try:
        print("📊 Iniciando análise do sinal")
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"

        minuto = int(re.search(r"⏰\s*(\d+)", texto).group(1)) if re.search(r"⏰\s*(\d+)", texto) else None
        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1)) if re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto) else None
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto) else [0, 0]
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto) else [0, 0]
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto) else [0, 0]
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"No Gol:\s*(\d+)/(\d+)", texto) else [0, 0]
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Total:\s*(\d+)/(\d+)", texto) else [0, 0]
        vento = float(re.search(r"🌬️\s*([\d.]+)\s*m/s", texto).group(1)) if re.search(r"🌬️\s*([\d.]+)\s*m/s", texto) else None

        pontos = 0
        resumo = []

        if ia and ia >= 75:
            pontos += 2
            resumo.append(f"• IA: {ia}%")
        if minuto and 16 <= minuto <= 22:
            pontos += 1
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            pontos += 2
        if sum(no_gol) >= 1:
            pontos += 2
        if sum(escanteios) >= 2:
            pontos += 1
        if vento and vento < 15:
            pontos += 1
        if sum(chutes) >= 4:
            pontos += 1
        if posse[0] >= 60 or posse[1] >= 60:
            pontos += 1

        try:
            nome_mandante, nome_visitante = jogo.split(" x ")
            historico = resumo_estatistico(nome_mandante.strip(), nome_visitante.strip())
            liga_info = resumo_estendido(nome_mandante.strip())
        except Exception as e:
            print(f"❌ Erro ao buscar histórico: {e}")
            historico = "⚠️ Histórico indisponível"
            liga_info = "⚠️ Info da liga indisponível"

        if pontos >= 7:
            veredito = "ENTRAR ✅"
            conclusao = "OVER 0.5 HT"
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

client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    if str(event.chat_id) == str(CHAT_ID_SINAL) and "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    client.start()
    app.run_polling()
