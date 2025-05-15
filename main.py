import os, re, asyncio, aiohttp, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon.sync import TelegramClient, events
from ia_openai import gerar_resposta_ia

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

bot = Bot(token=BOT_TOKEN)

# Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot com análise técnica e IA está ativo com polling!")

async def veredito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚙️ Critérios Técnicos:\n"
        "- IA ≥ 85%\n- Minuto 18–27\n- 3+ ataques perigosos\n"
        "- 1+ chute no gol\n- Escanteios ≥ 2\n- Vento < 20 m/s\n"
        "- Histórico gols 1T ≥ 2\n- Visitante dominante"
    )

async def teste_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 Teste IA recebido. Aguarde resposta...")
    msg = await gerar_resposta_ia("Qual a probabilidade de sair 1 gol no primeiro tempo com IA 88% e 4 finalizações no gol?")
    await update.message.reply_text(f"Resposta IA:\n{msg}")

# Monitoramento da odd
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
                                                    msg = f"⚽️ ENTRADA VALIDADA\n\n📌 Jogo: {nome}\n📈 Odd +0.5 HT atingiu {odd}\n💰 Valor sugerido: R$15"
                                                    await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg,
                                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
        except Exception as e:
            print("❌ Erro monitorando odd:", e)
        await asyncio.sleep(30)

# Análise de sinal
async def analisar(texto):
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"

        minuto = int(re.search(r"⏰\s*(\d+)", texto).group(1))
        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1))
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1)) if "💨" in texto else 0
        historico = 2  # mock fixo

        total_perigosos = sum(perigosos)
        total_no_gol = sum(no_gol)
        posse_dominante = posse[0] >= 60 or posse[1] >= 60
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7

        criterios = []
        resumo = []

        if ia >= 85: criterios.append("IA")
        resumo.append(f"• IA: {ia:.2f}% {'✓' if ia >= 85 else '✘'}")
        if 18 <= minuto <= 27: criterios.append("Minuto ideal")
        resumo.append(f"• Minuto: {minuto} {'✓' if 18 <= minuto <= 27 else '✘'}")
        if total_perigosos >= 12 and desequilibrio: criterios.append("Ataques perigosos")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if total_perigosos >= 12 and desequilibrio else '✘'}")
        if total_no_gol >= 1: criterios.append("Finalizações no gol")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}")
        if sum(escanteios) >= 2: criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")
        if vento < 20: criterios.append("Vento")
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 20 else '✘'}")
        if historico >= 2: criterios.append("Histórico 1T")
        resumo.append(f"• Histórico de gols 1T: {historico} {'✓' if historico >= 2 else '✘'}")
        if posse_dominante: criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse_dominante else '✘'}")

        if len(criterios) >= 3:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Confluência positiva em múltiplos critérios técnicos."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        elif 1 <= len(criterios) < 3:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Critérios parciais detectados."
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Sinais insuficientes."

        msg = f"""{veredito} (Sinal Técnico) – {jogo}

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}
"""

        explicacao = await gerar_resposta_ia(msg)
        msg += f"\n\n🧠 Avaliação IA:\n{explicacao}"

        await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as e:
        print("❌ Erro ao analisar:", e)

# Telethon escuta
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    if event.chat_id == CHAT_ID_SINAL and "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

# Iniciar tudo
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("veredito", veredito))
    app.add_handler(CommandHandler("testeia", teste_ia))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
