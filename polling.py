
from telethon import TelegramClient, events
import os
from main import analisar, CHAT_ID_SINAL

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

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

def iniciar_polling():
    client.start()
    client.run_until_disconnected()
