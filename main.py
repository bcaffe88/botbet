# main.py - Sinais refinados com conta pessoal (Telethon) + análise automática

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import os, re, asyncio, aiohttp, time
from ia_openai import gerar_resposta_ia

# Configurações
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))       # Canal BETZORD (onde sua conta pessoal está)
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))   # Grupo onde o bot está como admin
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

bot = Bot(token=BOT_TOKEN)

# Comandos do Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais refinados ativo com polling!")

async def veredito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""⚙️ Critérios Técnicos de Entrada:
- IA ≥ 80%
- Minuto 16–22
- 3+ ataques perigosos recentes
- 1+ chute no gol
- Escanteios ≥ 2
- Vento < 15 m/s
- Histórico gols 1T ≥ 2 (5 jogos)
- Visitante dominante
Entrada apenas com 5 ou mais critérios.""")

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
                                                    msg = f"⚽️ ENTRADA VALIDADA\n\n📌 Jogo: {nome}\n📈 Odd +0.5 HT: {odd}\n💰 Valor sugerido: R$15"
                                                    await bot.send_message(
                                                        chat_id=CHAT_ID_DESTINO,
                                                        text=msg,
                                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
        except Exception as e:
            print("❌ Erro monitorando odd:", e)
        await asyncio.sleep(30)

# Análise
async def analisar(texto):
    try:
        jogo = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo.group(1).strip() if jogo else "Times não identificados"

        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None

        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
        ia = float(ia_match.group(1)) if ia_match else None

        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0])) if "Ataques Perigosos" in texto else [0, 0]
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0])) if "Posse de Bola" in texto else [0, 0]
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0])) if "Escanteios" in texto else [0, 0]
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0])) if "No Gol" in texto else [0, 0]
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0])) if "Total:" in texto else [0, 0]

        vento = float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1)) if "💨" in texto else None

        criterios, resumo, peso_total = [], [], 0

        if ia and ia >= 80:
            criterios.append("IA")
            peso_total += 2
        resumo.append(f"• IA: {ia:.2f}% {'✓' if ia and ia >= 80 else '✘'}")

        if minuto and 16 <= minuto <= 22:
            criterios.append("Minuto ideal")
            peso_total += 1
        resumo.append(f"• Minuto: {minuto} {'✓' if minuto and 16 <= minuto <= 22 else '✘'}")

        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            criterios.append("Ataques perigosos")
            peso_total += 2
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if sum(perigosos) >= 10 else '✘'}")

        if sum(no_gol) >= 1:
            criterios.append("Finalizações no gol")
            peso_total += 2
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if sum(no_gol) >= 1 else '✘'}")

        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
            peso_total += 1
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")

        if vento and vento < 15:
            criterios.append("Vento ideal")
            peso_total += 1
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 15 else '✘'}")

        if sum(chutes) >= 4:
            criterios.append("Chutes totais")
            peso_total += 1

        if posse[0] >= 60 or posse[1] >= 60:
            criterios.append("Posse dominante")
            peso_total += 1
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse[0] >= 60 or posse[1] >= 60 else '✘'}")

        if peso_total >= 8:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Cenário ideal com forte confluência de critérios."
        elif peso_total >= 5:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Critérios razoáveis, observar mais evolução."
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Confluência insuficiente."

        msg = f"""{veredito} (Sinal Técnico) – {jogo}

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}
"""

        prompt_ia = f"""
Você é um analista técnico especialista em sinais esportivos ao vivo para entradas Over 0.5 HT.

Com base na análise abaixo, responda de forma direta:
1. Quais critérios técnicos ainda estão faltando para validar a entrada?
2. Até qual minuto do jogo vale a pena aguardar para observar esses critérios?
3. Quando deve-se descartar definitivamente a entrada?

Análise:
{msg}
"""
        explicacao = await gerar_resposta_ia(prompt_ia)
        msg += f"\n\n🧠 Avaliação IA:\n{explicacao.strip()}"

        await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

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
    app.add_handler(CommandHandler("veredito", veredito))

    client.start()  # inicia o Telethon
    app.run_polling()  # inicia polling do bot
