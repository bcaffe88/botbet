# Arquivo reconstruído após reset — função analisar incluída
# Adicione o restante do código conforme necessário antes ou depois deste bloco

import re
import os
from telegram import Bot

CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
bot = Bot(token=os.getenv("BOT_TOKEN"))

async def gerar_resposta_ia(mensagem): return "Exemplo de resposta da IA"  # Simulado para testes

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

        historico = 2
        if historico >= 2:
            criterios.append("Histórico de gols 1T")
        resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}")

        if posse_dominante:
            criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse_dominante else '✘'}")

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
            msg += f"\n\n🧠 Avaliação IA:\n❌ Erro da IA: {e}"

        bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as erro:
        print(f"❌ Erro na análise: {erro}")
