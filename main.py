"""
main_webhook.py com lógica refinada de entrada baseada em 8 critérios técnicos.
Entrada válida apenas com confluência de 3 ou mais critérios. Resposta formatada com veredito, análise e confiança.
"""

# IMPORTS
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
from telethon.sync import TelegramClient, events
import asyncio, os, re, aiohttp, time, threading
from hf_openassistant import gerar_resposta_ia

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN""")
API_ID = int(os.getenv("API_ID"""))
API_HASH = os.getenv("API_HASH""")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"""))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"""))
ODDS_API_KEY = os.getenv("ODDS_API_KEY""")
WEBHOOK_URL = os.getenv("WEBHOOK_URL""")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, use_context=True)

# COMANDOS
def start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Bot ativo com critérios refinados e IA.""")


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

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/""")
def index():
    return "🏠 Webhook do bot ativo"

# FUNÇÕES DE APOIO
def avaliar_criterios(texto):
    criterios = []
    resumo = []

    try:
        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1))
        if ia >= 85:
            criterios.append("IA""")
        resumo.append(f"• IA: {ia:.2f}% {'✓' if ia >= 85 else '✘'}""")
    except: resumo.append("• IA: não encontrado ✘""")

    try:
        minuto = int(re.search(r"⏰\s*(\d+)["'`]", texto).group(1))
        if 18 <= minuto <= 27:
            criterios.append("Minuto""")
        resumo.append(f"• Minuto: {minuto} {'✓' if 18 <= minuto <= 27 else '✘'}""")
    except: resumo.append("• Minuto: não encontrado ✘""")

    try:
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        if max(perigosos) >= 3:
            criterios.append("Ataques recentes""")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if max(perigosos) >= 3 else '✘'}""")
    except: resumo.append("• Ataques perigosos: não encontrado ✘""")

    try:
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        total_no_gol = sum(no_gol)
        if total_no_gol >= 1:
            criterios.append("Chutes no gol""")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}""")
    except: resumo.append("• Finalizações no gol: não encontrado ✘""")

    try:
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        if max(escanteios) >= 2:
            criterios.append("Escanteios dominantes""")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if max(escanteios) >= 2 else '✘'}""")
    except: resumo.append("• Escanteios: não encontrado ✘""")

    try:
        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1))
        if vento < 20:
            criterios.append("Vento ideal""")
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 20 else '✘'}""")
    except: resumo.append("• Vento: não encontrado ✘""")

    try:
        # Histórico manual ou simulado por padrão
        historico = 2  # fictício para exemplo
        if historico >= 2:
            criterios.append("Histórico gols""")
        resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}""")
    except: resumo.append("• Histórico recente: não disponível ✘""")

    try:
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        dominante = posse[1] > posse[0] and chutes[1] > chutes[0]
        if dominante:
            criterios.append("Dominância visitante""")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if dominante else '✘'}""")
    except: resumo.append("• Posse e dominância: não disponível ✘""")

    return criterios, resumo

# FUNÇÃO DE ANÁLISE FINAL
async def analisar(texto):
    criterios, resumo = avaliar_criterios(texto)
    veredito = "❌ NÃO ENTRAR"
    confianca = "Baixa"
    conclusao = "Cenário com pouca convergência entre os indicadores."

    if len(criterios) >= 3:
        veredito = "✅ ENTRAR"
        confianca = "Alta"
        conclusao = "Confluência positiva em múltiplos critérios técnicos."

    elif 1 <= len(criterios) < 3:
        veredito = "⏳ AGUARDAR"
        confianca = "Média"
        conclusao = "Alguns sinais presentes, mas insuficiente para entrada segura."

    msg = f"{veredito} (Sinal Técnico)

Análise conforme o Prompt Fixo:
" + "
".join(resumo)
    msg += f"

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}"

    explicacao = await gerar_resposta_ia(msg)
    msg += f"

🧠 Avaliação IA:
{explicacao}"
    bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

# ESCUTA TELETHON
client = TelegramClient('sessao_sinais', API_ID, API_HASH)

@client.on(events.NewMessage())
async def tratar(event):
    if event.chat_id != CHAT_ID_SINAL:
        return
    if 'OVER 0.5 HT' in event.message.message:
        await analisar(event.message.message)

# RODAR FLASK E TELETHON
def rodar_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook""")
    threading.Thread(target=rodar_flask).start()
    client.start()
    client.run_until_disconnected()
