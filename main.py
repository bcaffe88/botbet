import os
import re
import aiohttp
import asyncio
import time
from telethon import TelegramClient, events
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from ia_openai import gerar_resposta_ia  # Você precisa criar este módulo

# Configurações (melhor usar um arquivo .env)
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Inicialização
bot = Bot(token=BOT_TOKEN)
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

async def monitorar_odd(jogo, link, timeout=300):
    """Monitora odds via API com tratamento de erros robusto"""
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
    inicio = time.time()
    
    while time.time() - inicio < timeout:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        print(f"⚠️ API retornou status {resp.status}")
                        await asyncio.sleep(30)
                        continue

                    data = await resp.json()
                    for partida in data:
                        nome = f"{partida.get('home_team', '')} x {partida.get('away_team', '')}"
                        if jogo.lower() in nome.lower():
                            for bk in partida.get("bookmakers", []):
                                for mkt in bk.get("markets", []):
                                    if mkt["key"] == "totals":
                                        for linha in mkt["outcomes"]:
                                            if linha["point"] == 0.5 and linha["name"] == "Over":
                                                odd = linha["price"]
                                                if odd >= 1.50:
                                                    msg = (
                                                        f"⚽️ ENTRADA VALIDADA\n\n📌 Jogo: {nome}\n"
                                                        f"📈 Odd +0.5 HT: {odd}\n💰 Valor sugerido: R$15"
                                                    )
                                                    await bot.send_message(
                                                        chat_id=CHAT_ID_DESTINO,
                                                        text=msg,
                                                        reply_markup=InlineKeyboardMarkup([
                                                            [InlineKeyboardButton("👉 Apostar agora", url=link)]
                                                        ])
                                                    )
                                                    return
        except Exception as e:
            print(f"❌ Erro ao monitorar odd: {str(e)}")
            await asyncio.sleep(30)

async def analisar(texto):
    """Analisa mensagem com regex e critérios técnicos"""
    try:
        # Extração de dados
        jogo = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo.group(1).strip() if jogo else "Times não identificados"
        
        dados = {
            'minuto': int(re.search(r"⏰\s*(\d+)", texto).group(1)) if "⏰" in texto else None,
            'ia': float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1)) if "OVER 0.5 HT" in texto else None,
            'perigosos': list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0])) if "Ataques Perigosos" in texto else [0, 0],
            'posse': list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0])) if "Posse de Bola" in texto else [0, 0],
            'escanteios': list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0])) if "Escanteios" in texto else [0, 0],
            'no_gol': list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0])) if "No Gol" in texto else [0, 0],
            'vento': float(re.search(r"💨\s*([\d.]+)\s*m/s", texto).group(1)) if "💨" in texto else None
        }

        # Análise de critérios
        criterios = []
        resumo = []

        # IA
        if dados['ia'] and dados['ia'] >= 80:
            criterios.append("IA")
        resumo.append(f"• IA: {dados['ia'] or 'N/A'} {'✓' if dados['ia'] and dados['ia'] >= 80 else '✘'}")

        # Minuto ideal
        if dados['minuto'] and 16 <= dados['minuto'] <= 22:
            criterios.append("Minuto ideal")
        resumo.append(f"• Minuto: {dados['minuto']} {'✓' if dados['minuto'] and 16 <= dados['minuto'] <= 22 else '✘'}")

        # Ataques perigosos
        total_perigosos = sum(dados['perigosos'])
        desequilibrio = abs(dados['perigosos'][0] - dados['perigosos'][1]) >= 7
        if total_perigosos >= 10 and desequilibrio:
            criterios.append("Ataques perigosos")
        resumo.append(f"• Ataques perigosos: {dados['perigosos'][0]} x {dados['perigosos'][1]} "
                     f"{'✓' if total_perigosos >= 10 and desequilibrio else '✘'}")

        # ... (continuar com outros critérios)

        # Tomada de decisão
        if len(criterios) >= 5:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Cenário ideal com múltiplos critérios técnicos atendidos."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        elif len(criterios) == 4:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Critérios parciais, cenário ainda incompleto."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Falta de confluência entre os critérios."

        # Montagem da mensagem
        msg = (
            f"{veredito} (Sinal Técnico) – {jogo}\n\n"
            f"Análise conforme o Prompt Fixo:\n{chr(10).join(resumo)}\n\n"
            f"📌 Conclusão:\n{conclusao}\n\n"
            f"Veredito: {veredito}\n"
            f"Confiança: {confianca}"
        )

        # Integração com IA
        try:
            explicacao = await gerar_resposta_ia(msg)
            msg += f"\n\n🧠 Avaliação IA:\n{explicacao}"
        except Exception as e:
            print(f"❌ Erro ao chamar IA: {e}")
            msg += f"\n\n🧠 Avaliação IA:\n❌ Erro: {e}"

        await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as e:
        print(f"❌ Erro crítico na análise: {e}")

async def iniciar():
    """Inicia todos os serviços"""
    await client.start()
    print("✅ Bot iniciado e escutando...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(iniciar())
