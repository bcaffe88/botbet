
# IMPORTS
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
    update.message.reply_text("👋 Bot com IA via Webhook ativo!")

def veredito_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("""⚙️ Critérios Técnicos de Entrada:
- IA ≥ 85%
- Minuto 18-27
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
    return "🏠 Webhook do bot ativo"

# FUNÇÃO DE SCRAPING
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
        print("Erro ao coletar histórico no SofaScore:", e)
        return 0

# RESTANTE DO CÓDIGO OMITIDO PARA BREVIDADE...
