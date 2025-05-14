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
    update.message.reply_text("👋 Bot com IA via Webhook ativo!")

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
        minuto = int(re.search(r"⏰\s*(\d+)[\"'`]", texto).group(1))
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
        # Verifica quem é o time dominante
time_dominante = "mandante" if posse[0] > posse[1] else "visitante"
nome_time_dominante = jogo.split(" x ")[0].strip() if time_dominante == "mandante" else jogo.split(" x ")[1].strip()

# Scraping no SofaScore
historico = scraping_gols_1t_sofascore(nome_time_dominante)

if historico >= 2:
    criterios.append("Histórico de gols 1T")
resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}")

    try:
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        dominante = posse[1] > posse[0] and chutes[1] > chutes[0]
        if dominante:
            criterios.append("Dominância visitante""")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if dominante else '✘'}""")
    except: resumo.append("• Posse e dominância: não disponível ✘""")

    return criterios, resumo

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
        
# FUNÇÃO DE ANÁLISE FINAL
async def analisar(texto):
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não encontrados"

        minuto_match = re.search(r"⏰\s*(\d+)[\"'”]", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None

        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
        ia = float(ia_match.group(1)) if ia_match else None

        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))

        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)
        vento = float(vento_match.group(1)) if vento_match else None

        total_perigosos = sum(perigosos)
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7
        posse_dominante = posse[0] >= 60 or posse[1] >= 60
        total_chutes = sum(chutes)
        total_no_gol = sum(no_gol)

        # critérios técnicos
        criterios = []
        resumo = []

        if ia and ia >= 85:
            criterios.append("IA")
        resumo.append(f"• IA: {ia if ia else 'não encontrado'} {'✓' if ia and ia >= 85 else '✘'}")

        if minuto and 18 <= minuto <= 27:
            criterios.append("Minuto ideal")
        resumo.append(f"• Minuto: {minuto if minuto else 'não encontrado'} {'✓' if minuto and 18 <= minuto <= 27 else '✘'}")

        if total_perigosos >= 12 and desequilibrio:
            criterios.append("Ataques perigosos")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if total_perigosos >= 12 and desequilibrio else '✘'}")

        if total_no_gol >= 1:
            criterios.append("Finalizações no gol")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}")

        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")

        if vento is not None and vento < 20:
            criterios.append("Vento favorável")
        resumo.append(f"• Vento: {vento if vento else 'não encontrado'} m/s {'✓' if vento and vento < 20 else '✘'}")

        # Histórico fictício de exemplo (mock fixo)
        historico = 2
        if historico >= 2:
            criterios.append("Histórico de gols 1T")
        resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}")

        if posse_dominante:
            criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse_dominante else '✘'}")

        # Veredito com base na quantidade de critérios atendidos
        if len(criterios) >= 3:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Confluência positiva em múltiplos critérios técnicos."
        elif 1 <= len(criterios) < 3:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Alguns sinais presentes, mas insuficiente para entrada segura."
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Cenário com pouca convergência entre os indicadores."

        # Mensagem formatada
        msg = f"""{veredito} (Sinal Técnico) – {jogo}

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}
"""

        # IA explicativa
        try:
            explicacao = await gerar_resposta_ia(msg)
            msg += f"\n\n🧠 Avaliação IA:\n{explicacao}"
        except Exception as e:
            msg += f"\n\n🧠 Avaliação IA:\n❌ Erro da IA: {e}"

        # Enviar ao grupo
        bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as erro:
        print(f"❌ Erro na análise: {erro}")

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
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    threading.Thread(target=rodar_flask).start()
    client.start()
    client.run_until_disconnected()
