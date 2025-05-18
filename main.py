# main.py - Sinais refinados com polling e telethon

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import os, re, asyncio, aiohttp, time, unicodedata, json

# Configurações
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

bot = Bot(token=BOT_TOKEN)

# Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais refinados ativo com polling!")

# Odds
def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

async def monitorar_odd(jogo, link, timeout=300):
    print(f"⏳ Iniciando monitoramento de odd para {jogo}")
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    print("🗕️ Resposta da API de odds recebida")
                    if isinstance(data, dict):
                        print("❌ Dados de odds inválidos (esperado lista):", data)
                        return None
                    for partida in data:
                        nome = partida.get("home_team", "") + " x " + partida.get("away_team", "")
                        if normalizar(jogo) in normalizar(nome):
                            for bk in partida.get("bookmakers", []):
                                for mkt in bk.get("markets", []):
                                    if mkt["key"] == "totals":
                                        for linha in mkt["outcomes"]:
                                            if linha["point"] == 0.5 and linha["name"] == "Over":
                                                odd = linha["price"]
                                                print(f"🔍 Odd encontrada: {odd} para jogo {nome}")
                                                if odd >= 1.50:
                                                    return odd
        except Exception as e:
            print("❌ Erro monitorando odd:", e)
        await asyncio.sleep(30)
    return None

# ANÁLISE
async def analisar(texto):
    print("📊 Iniciando análise do sinal")
    try:
        jogo = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo.group(1).strip() if jogo else "Times não identificados"
        print(f"📌 Jogo detectado: {jogo}")

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

        if ia and ia >= 80:
            criterios.append("IA")
            pontos += 2
        resumo.append(f"• IA: {ia} {'✓' if ia and ia >= 80 else '✗'}")

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

        if pontos >= 8:
            odd = await monitorar_odd(jogo, "https://bet365.com")
            veredito = "ENTRAR ✅"
            confianca = "Alta"
            conclusao = "100.00 responsabilidade."

            msg = f"""⚽️ {veredito} {jogo}

🤖 OVERBOT VIP:
{chr(10).join(resumo)}

📋 ODD: {odd if odd else 'A definir'}
Confiança: {confianca}
DYOR: {conclusao}"""
            await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
        else:
            print("❌ Veredito não é 'ENTRAR'. Nenhum envio será feito.")

    except Exception as e:
        print("❌ Erro ao analisar:", e)

# TELETHON
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    print(f"📨 Mensagem recebida de {event.chat_id}:")
    print(f"🔍 CHAT_ID recebido: {event.chat_id}")
    print(event.message.message)

    if str(event.chat_id) == str(CHAT_ID_SINAL) and "OVER 0.5 HT" in event.message.message:
        print("✅ Sinal detectado, enviando para análise.")
        await analisar(event.message.message)
    else:
        print("⚠️ Mensagem ignorada (ID ou palavra-chave não conferem).")

# Inicialização final correta
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    client.start()  # inicia o Telethon
    app.run_polling()  # inicia polling do bot
