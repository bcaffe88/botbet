import os
import re
import unicodedata
import asyncio
from datetime import datetime
from difflib import SequenceMatcher

from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import aiohttp

from estatisticas_time import buscar_team_id, gols_primeiro_tempo, media_gols_liga, confrontos_diretos

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

# VERIFICAR GOL HT + PONTUAÇÃO EXTRA
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
                    teams = item["teams"]
                    halftime = item["score"]["halftime"]
                    casa = teams["home"]["name"]
                    fora = teams["away"]["name"]
                    nome_match = f"{casa} x {fora}"

                    if similaridade(normalizar(nome_jogo), normalizar(nome_match)) > 0.75:
                        gols_ht = (halftime["home"] or 0) + (halftime["away"] or 0)

                        id_casa = buscar_team_id(casa)
                        id_fora = buscar_team_id(fora)
                        gols_1t_casa = gols_primeiro_tempo(id_casa)
                        gols_1t_fora = gols_primeiro_tempo(id_fora)
                        confrontos = confrontos_diretos(id_casa, id_fora)

                        pontos_extra = 0
                        if gols_1t_casa >= 3: pontos_extra += 1
                        if gols_1t_fora >= 3: pontos_extra += 1
                        if any("1" in c or "2" in c for c in confrontos): pontos_extra += 1

                        return ("✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU", pontos_extra)
    except Exception as e:
        print("❌ Erro ao consultar API-Football:", e)
    return ("⏳ NÃO LOCALIZADO", 0)

# FUNÇÃO ANALISAR
async def analisar(texto):
    print("📊 Iniciando análise do sinal")
    nome_liga = "Liga não identificada"
    tendencia_liga = "Tendência desconhecida"

    try:
        print("📝 Texto recebido:\n", texto)
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        ia_match = re.search(r"OVER 0\\.5 HT[:\s]*([\d.]+)%", texto)

        if not jogo_match or not minuto_match or not ia_match:
            print("❌ Jogo, Minuto ou IA não encontrados")
            return

        jogo = jogo_match.group(1).strip()
        minuto = int(minuto_match.group(1))
        ia = float(ia_match.group(1))

        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto) else [0, 0]
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto) else [0, 0]
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto) else [0, 0]
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"No Gol:\s*(\d+)/(\d+)", texto) else [0, 0]
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Total:\s*(\d+)/(\d+)", texto) else [0, 0]
        vento = float(re.search(r"🌬️\s*([\d.]+)\s*m/s", texto).group(1)) if re.search(r"🌬️\s*([\d.]+)\s*m/s", texto) else None

        criterios, resumo = [], []
        pontos = 0

        if ia >= 80:
            criterios.append("IA")
            pontos += 2
        resumo.append(f"• IA: {ia} ✓" if ia >= 80 else f"• IA: {ia} ✗")

        if 16 <= minuto <= 22: pontos += 1
        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7: pontos += 2
        if sum(no_gol) >= 1: pontos += 2
        if sum(escanteios) >= 2: pontos += 1
        if vento and vento < 15: pontos += 1
        if sum(chutes) >= 4: pontos += 1
        if posse[0] >= 60 or posse[1] >= 60: pontos += 1

        _, pontos_extra = await verificar_gol_ht(jogo)
        pontos += pontos_extra

        headers = {"x-apisports-key": FOOTBALL_API_KEY}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://v3.football.api-sports.io/fixtures?date={datetime.now().strftime('%Y-%m-%d')}", headers=headers) as resp:
                data = await resp.json()
                for item in data.get("response", []):
                    casa = item["teams"]["home"]["name"]
                    fora = item["teams"]["away"]["name"]
                    nome_match = f"{casa} x {fora}"
                    if similaridade(normalizar(jogo), normalizar(nome_match)) > 0.75:
                        nome_liga = item["league"]["name"]
                        liga_id = item["league"]["id"]
                        temporada = item["league"]["season"]
                        media = media_gols_liga(liga_id, temporada)
                        tendencia_liga = "Tendência OVER 1T" if media >= 1.2 else "Tendência UNDER 1T"
                        if media >= 1.2:
                            pontos += 2
                        break

        print(f"📊 Pontuação final: {pontos}")

        if pontos >= 9:
            veredito = "ENTRAR ✅"
            confianca = "Alta"
            conclusao = "100.00 responsabilidade."
            msg = f"""⚽️ {veredito} {jogo}

🤖 OVERBOT VIP:
{chr(10).join(resumo)}

Confiança: {confianca}
🏆 Liga: {nome_liga} | {tendencia_liga}
DYOR: {conclusao}"""
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
            await asyncio.sleep(1500)
            resultado_final, _ = await verificar_gol_ht(jogo)
            editado = f"{msg}\n\n📢 Resultado do sinal: {resultado_final}"
            await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_enviada.message_id, text=editado)
        else:
            print("❌ Veredito: NÃO ENTRAR - Pontuação insuficiente.")

    except Exception as e:
        print("❌ Erro ao analisar:", e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais ativo!")

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
