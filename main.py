
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
from telethon.sync import TelegramClient, events
import asyncio, os, re, aiohttp, time, threading
from hf_openassistant import gerar_resposta_ia

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

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Bot com IA via Webhook ativo!")

def veredito_cmd(update: Update, context: CallbackContext):
    texto = (
        "📊 Critérios para ENTRAR:
"
        "- IA ≥ 85%
"
        "- Minuto ideal: 18’–22’ (aceitável: 15’–35’)
"
        "- Ataques perigosos ≥ 12 com desequilíbrio
"
        "- Chutes ≥ 3 (≥ 2 no gol)
"
        "- Escanteios ≥ 1
"
        "- Posse ≥ 60% ou compensação
"
        "- Vento ideal: 3–8 m/s (ou compensado)"
    )
    update.message.reply_text(texto)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("veredito", veredito_cmd))

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "🤖 Bot com Webhook ativo"

async def monitorar_odd(jogo, link, timeout=300):
    print(f"🔎 Monitorando odd para: {jogo}")
    inicio = time.time()
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
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
                                                    msg = f"⚽️ ENTRADA VALIDADA

📌 Jogo: {nome}
📈 Odd +0.5 HT atingiu {odd}
💰 Valor sugerido: R$15"
                                                    bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
            await asyncio.sleep(30)
            if time.time() - inicio > timeout:
                return
        except Exception as e:
            print(f"❌ Erro ao monitorar odd: {e}")
            return

async def analisar_sinal(texto, link):
    try:
        jogo = texto.splitlines()[0].replace("⚽️", "").strip()
        minuto = int(re.search(r"⏰\s*(\d+)["'`]", texto).group(1))
        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1))
        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1))
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = sum(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        total_perigosos = sum(perigosos)
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7
        posse_dominante = posse[0] >= 60 or posse[1] >= 60
        total_chutes = sum(chutes)
        total_no_gol = sum(no_gol)

        linhas = [f"• IA: {ia:.2f}% {'✅' if ia >= 85 else '❌'}",
                  f"• Minuto: {minuto} {'✅' if 18 <= minuto <= 22 else ('⏳' if minuto < 18 else '⚠️')}",
                  f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✅' if total_perigosos >= 12 and desequilibrio else '❌'}",
                  f"• Posse de bola: {posse[0]}x{posse[1]} {'✅' if posse_dominante else '⚠️'}",
                  f"• Escanteios: {escanteios} {'✅' if escanteios >= 1 else '❌'}",
                  f"• Finalizações: {total_chutes} | No Gol: {no_gol[0]}x{no_gol[1]} {'✅' if total_no_gol >= 2 else '❌'}",
                  f"• Vento: {vento} m/s {'✅' if 3 <= vento <= 8 else '⚠️'}"]

        if ia >= 85 and 15 <= minuto <= 35 and total_perigosos >= 12 and desequilibrio and total_chutes >= 3 and total_no_gol >= 2 and escanteios >= 1 and (posse_dominante or total_chutes >= 4):
            decisao = "✅ ENTRAR"
            confianca = "Alta"
            asyncio.create_task(monitorar_odd(jogo, link))
        elif 0 < minuto < 15:
            decisao = "⏳ AGUARDAR"
            confianca = "Média"
            asyncio.create_task(monitorar_odd(jogo, link))
        else:
            decisao = "❌ NÃO ENTRAR"
            confianca = "Baixa"

        mensagem = f"{decisao} ({jogo})

Análise conforme o Prompt Fixo:
" + "
".join(linhas)
        mensagem += f"

📌 Conclusão:
{'Situação ideal para entrada com confluência total.' if decisao=='✅ ENTRAR' else 'Cenário ainda incompleto ou fora da janela ideal.'}"
        mensagem += f"

Veredito: {decisao} (Confiança: {confianca})"

        resposta_ia = await gerar_resposta_ia(mensagem)
        mensagem += f"

🧠 Avaliação IA:
{resposta_ia}"

        if decisao in ["✅ ENTRAR", "⏳ AGUARDAR"]:
            bot.send_message(chat_id=CHAT_ID_DESTINO, text=mensagem, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Apostar agora", url=link)]]))
        else:
            bot.send_message(chat_id=CHAT_ID_DESTINO, text=mensagem)

    except Exception as e:
        print(f"❌ Erro na análise: {e}")

client = TelegramClient('sessao_sinais', API_ID, API_HASH)

@client.on(events.NewMessage())
async def tratar(event):
    if event.chat_id != CHAT_ID_SINAL:
        return
    if 'OVER 0.5 HT' in event.message.message:
        texto = event.message.message
        link = "https://bet365.com"
        await analisar_sinal(texto, link)

def rodar_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

    flask_thread = threading.Thread(target=rodar_flask)
    flask_thread.start()

    client.start()
    client.run_until_disconnected()
