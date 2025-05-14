from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon.sync import TelegramClient, events
import os, re, asyncio, aiohttp, time, requests
from bs4 import BeautifulSoup
from hf_openassistant import gerar_resposta_ia

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

bot = Bot(token=BOT_TOKEN)

def scraping_gols_1t_sofascore(nome_time):
    try:
        nome_formatado = nome_time.lower().replace(" ", "-")
        url = f"https://www.sofascore.com/team/football/{nome_formatado}/"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return 0
        soup = BeautifulSoup(r.text, 'html.parser')
        partidas = soup.find_all("a", href=True)
        contagem = 0
        for link in partidas[:5]:
            if "match" in link['href']:
                r2 = requests.get("https://www.sofascore.com" + link['href'], headers={"User-Agent": "Mozilla/5.0"})
                inner = BeautifulSoup(r2.text, 'html.parser')
                placar = inner.find("div", {"class": "scoreBox__score"})
                if placar and "(" in placar.get_text():
                    gols = placar.get_text().split("(")[-1].replace(")", "").split(":")
                    contagem += int(gols[0])
        return contagem
    except:
        return 0

async def monitorar_odd(jogo, link, timeout=300):
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    for partida in data:
                        nome = partida.get("home_team", "") + " x " + partida.get("away_team", "")
                        if jogo.lower() in nome.lower():
                            for bk in partida.get("bookmakers", []):
                                for mkt in bk.get("markets", []):
                                    if mkt["key"] == "totals":
                                        for linha in mkt["outcomes"]:
                                            if linha["point"] == 0.5 and linha["name"] == "Over":
                                                odd = linha["price"]
                                                if odd >= 1.50:
                                                    msg = f"""⚽️ ENTRADA VALIDADA

📌 Jogo: {nome}
📈 Odd +0.5 HT: {odd}
💰 Valor sugerido: R$15"""
                                                    await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg,
                                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
        except Exception as e:
            print(f"Erro monitorando odds: {e}")
        await asyncio.sleep(30)

async def analisar(texto):
    try:
        jogo = re.search(r'⚽️\s*(.+)', texto).group(1).strip()
        minuto = int(re.search(r"⏰\s*(\d+)", texto).group(1))
        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1))
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1))

        criterios = []
        resumo = []
        total_perigosos = sum(perigosos)
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7
        total_no_gol = sum(no_gol)
        posse_dominante = posse[0] >= 60 or posse[1] >= 60
        historico = scraping_gols_1t_sofascore(jogo.split(" x ")[0].strip())

        if ia >= 85: criterios.append("IA")
        resumo.append(f"• IA: {ia}% {'✓' if ia >= 85 else '✘'}")
        if 18 <= minuto <= 27: criterios.append("Minuto")
        resumo.append(f"• Minuto: {minuto} {'✓' if 18 <= minuto <= 27 else '✘'}")
        if total_perigosos >= 12 and desequilibrio: criterios.append("Ataques")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if total_perigosos >= 12 and desequilibrio else '✘'}")
        if total_no_gol >= 1: criterios.append("Finalizações no gol")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}")
        if sum(escanteios) >= 2: criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")
        if vento < 20: criterios.append("Vento ideal")
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 20 else '✘'}")
        if historico >= 2: criterios.append("Histórico 1T")
        resumo.append(f"• Histórico gols 1T: {historico} {'✓' if historico >= 2 else '✘'}")
        if posse_dominante: criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]} x {posse[1]} {'✓' if posse_dominante else '✘'}")

        if len(criterios) >= 3:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Confluência positiva em múltiplos critérios técnicos."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        elif 1 <= len(criterios) < 3:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Critérios parciais, aguardar evolução."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Sinais insuficientes."

        msg = f"""{veredito} ({jogo})

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}
"""
        try:
            explicacao = await gerar_resposta_ia(msg)
            msg += f"

🧠 Avaliação IA:
{explicacao}"
        except Exception as e:
            msg += f"

🧠 Avaliação IA:
❌ Erro: {e}"

        await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as e:
        print("❌ Erro ao analisar:", e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot ativo com análise técnica e IA!")

async def veredito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Critérios técnicos: IA, minuto, ataques perigosos, finalizações no gol, escanteios, vento, histórico e posse.")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("veredito", veredito))

client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    if event.chat_id == CHAT_ID_SINAL and "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

if __name__ == "__main__":
    async def main():
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await client.start()
        await client.run_until_disconnected()

    asyncio.run(main())
