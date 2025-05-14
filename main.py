
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon.sync import TelegramClient, events
import os, re, asyncio, aiohttp, time, requests
from bs4 import BeautifulSoup
from hf_openassistant import gerar_resposta_ia

# CONFIGURAÇÕES
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

bot = Bot(token=BOT_TOKEN)

# COMANDOS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Bot com IA e polling ativo!")

async def veredito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """⚙️ Critérios Técnicos de Entrada:
- IA ≥ 85%
- Minuto 18–27
- 3+ ataques perigosos recentes
- 1+ chute no gol
- Escanteios ≥ 2
- Vento < 20 m/s
- Histórico gols 1T ≥ 2 (últimos 5 jogos)
- Visitante dominante"""
    )

# MONITORAMENTO DE ODDS
async def monitorar_odd(jogo, link, timeout=300):
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
    inicio = time.time()
    while True:
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
                                                    msg = f"⚽️ ENTRADA VALIDADA\n\n📌 Jogo: {nome}\n📈 Odd +0.5 HT atingiu {odd}\n💰 Valor sugerido: R$15"
                                                    await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
            await asyncio.sleep(30)
            if time.time() - inicio > timeout:
                return
        except Exception as e:
            print("❌ Erro no monitoramento de odd:", e)
            return

# SCRAPING SOFASCORE
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
        max_jogos = 5
        for link in partidas:
            if "/" in link['href'] and "match" in link['href'] and contagem < max_jogos:
                partida_url = "https://www.sofascore.com" + link['href']
                jogo_html = requests.get(partida_url, headers={"User-Agent": "Mozilla/5.0"})
                jogo_soup = BeautifulSoup(jogo_html.text, 'html.parser')
                score_tag = jogo_soup.find("div", {"class": "scoreBox__score"})
                if score_tag:
                    placar = score_tag.get_text().strip()
                    if placar and "(" in placar:
                        placar_1t = placar.split("(")[-1].replace(")", "").split(":")
                        gols_time = int(placar_1t[0])
                        contagem += gols_time
        return contagem
    except Exception as e:
        print("Erro no scraping:", e)
        return 0

# ANÁLISE
async def analisar(texto):
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"
        minuto_match = re.search(r"⏰\s*(\d+)[\"'”]", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None
        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
        ia = float(ia_match.group(1)) if ia_match else None
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1)) if "💨" in texto else None

        criterios, resumo = [], []
        total_perigosos = sum(perigosos)
        total_no_gol = sum(no_gol)
        posse_dominante = posse[0] >= 60 or posse[1] >= 60
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7

        if ia and ia >= 85: criterios.append("IA")
        resumo.append(f"• IA: {ia:.2f}% {'✓' if ia and ia >= 85 else '✘'}")
        if minuto and 18 <= minuto <= 27: criterios.append("Minuto ideal")
        resumo.append(f"• Minuto: {minuto} {'✓' if minuto and 18 <= minuto <= 27 else '✘'}")
        if total_perigosos >= 12 and desequilibrio: criterios.append("Ataques perigosos")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if total_perigosos >= 12 and desequilibrio else '✘'}")
        if total_no_gol >= 1: criterios.append("Finalizações no gol")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}")
        if sum(escanteios) >= 2: criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")
        if vento is not None and vento < 20: criterios.append("Vento ideal")
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 20 else '✘'}")
        historico = scraping_gols_1t_sofascore(jogo.split(" x ")[0].strip())
        if historico >= 2: criterios.append("Histórico 1T")
        resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}")
        if posse_dominante: criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse_dominante else '✘'}")

        if len(criterios) >= 3:
            veredito, confianca, conclusao = "✅ ENTRAR", "Alta", "Confluência positiva em múltiplos critérios técnicos."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        elif 1 <= len(criterios) < 3:
            veredito, confianca, conclusao = "⏳ AGUARDAR", "Média", "Critérios parciais, aguardar evolução do jogo."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        else:
            veredito, confianca, conclusao = "❌ NÃO ENTRAR", "Baixa", "Sinais insuficientes para entrada segura."

        msg = f"""{veredito} (Sinal Técnico) – {jogo}

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}
"""
        try:
            explicacao = await gerar_resposta_ia(msg)
            msg += f"\n\n🧠 Avaliação IA:\n{explicacao}"
        except Exception as e:
            msg += f"\n\n🧠 Avaliação IA:\n❌ Erro: {e}"

        await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as e:
        print("❌ Erro ao analisar:", e)

# TELEGRAM + TELETHON
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    if event.chat_id == CHAT_ID_SINAL and "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

# MAIN
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("veredito", veredito))

    loop = asyncio.get_event_loop()
    loop.create_task(app.run_polling())
    client.start()
    client.run_until_disconnected()
