
# -*- coding: utf-8 -*-
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
from telethon.sync import TelegramClient, events
import asyncio, os, re, aiohttp, time, threading
from hf_openassistant import gerar_resposta_ia
import requests
from bs4 import BeautifulSoup

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, use_context=True)

# COMANDOS
def start(update: Update, context: CallbackContext):
    update.message.reply_text("🤖 Bot pronto para refinar sinais com IA e análise técnica!")

def veredito_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("""⚙️ Critérios Técnicos de Entrada:
- IA ≥ 85%
- Minuto 18–27
- 3+ ataques perigosos recentes
- 1+ chute no gol
- Escanteios ≥ 2
- Vento < 20 m/s
- Histórico gols 1T ≥ 2 (últimos 5 jogos)
- Visitante dominante""")

dispatcher.add_handler(CommandHandler("veredito", veredito_cmd))
dispatcher.add_handler(CommandHandler("start", start))

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "🏠 Webhook ativo!"

# Scraping histórico
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
        for link in partidas:
            if "/" in link['href'] and "match" in link['href']:
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
                if contagem >= 5:
                    break
        return contagem
    except:
        return 0

# Monitorar odd após veredito positivo
async def monitorar_odd(jogo, link, timeout=300):
    print(f"🎯 Monitorando odd para {jogo}")
    inicio = time.time()
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
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
                                                    msg = f"⚽️ ENTRADA VALIDADA

📌 Jogo: {nome}
📈 Odd +0.5 HT: {odd}
💰 Valor: R$15"
                                                    bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg,
                                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
        except Exception as e:
            print(f"Erro no monitoramento: {e}")
        await asyncio.sleep(30)

# Função principal
async def analisar(texto):
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Jogo não encontrado"
        minuto = int(re.search(r"⏰\s*(\d+)["'”]", texto).group(1))
        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1))
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1))

        resumo = []
        criterios = []

        if ia >= 85:
            criterios.append("IA")
        resumo.append(f"• IA: {ia} {'✓' if ia >= 85 else '✘'}")
        if 18 <= minuto <= 27:
            criterios.append("Minuto")
        resumo.append(f"• Minuto: {minuto} {'✓' if 18 <= minuto <= 27 else '✘'}")
        if max(perigosos) >= 3:
            criterios.append("Ataques perigosos")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if max(perigosos) >= 3 else '✘'}")
        if sum(no_gol) >= 1:
            criterios.append("Finalizações no gol")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if sum(no_gol) >= 1 else '✘'}")
        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")
        if vento < 20:
            criterios.append("Vento ideal")
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 20 else '✘'}")

        time_dominante = "mandante" if posse[0] > posse[1] else "visitante"
        nome_time_dominante = jogo.split(" x ")[0].strip() if time_dominante == "mandante" else jogo.split(" x ")[1].strip()
        historico = scraping_gols_1t_sofascore(nome_time_dominante)
        if historico >= 2:
            criterios.append("Histórico gols")
        resumo.append(f"• Histórico gols (últimos 5j): {historico} {'✓' if historico >= 2 else '✘'}")

        dominante = posse[1] > posse[0] and chutes[1] > chutes[0]
        if dominante:
            criterios.append("Visitante dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if dominante else '✘'}")

        if len(criterios) >= 3:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Sinal técnico com forte confluência"
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        elif len(criterios) == 2:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Sinal promissor mas incompleto"
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Critérios insuficientes"

        msg = f"""{veredito} ({jogo})

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}"""

        try:
            explicacao = await gerar_resposta_ia(msg)
            msg += f"\n\n🧠 Avaliação IA:\n{explicacao}"
        except Exception as e:
            msg += f"\n\n🧠 Avaliação IA:\nErro IA: {e}"

        bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as e:
        print("Erro na análise:", e)

# ESCUTA TELEGRAM
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def tratar(event):
    if event.chat_id != CHAT_ID_SINAL:
        return
    if "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

# START
def rodar_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    threading.Thread(target=rodar_flask).start()
    client.start()
    client.run_until_disconnected()
