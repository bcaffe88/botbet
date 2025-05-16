import asyncio
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest

# Configurações do canal e sessão
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))  # -100... do canal Betzord

# Referência à função de análise que você já criou
de main import analisar  # Certifique-se que 'main.py' tem essa função importável

# Iniciar o cliente Telethon
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

# Função que busca novas mensagens do canal a cada 10s
async def escutar_canal():
    await client.start()
    canal = await client.get_entity(CHAT_ID_SINAL)
    ultima_id = 0
    while True:
        try:
            history = await client(GetHistoryRequest(
                peer=canal,
                limit=1,
                offset_date=None,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0
            ))
            if history.messages:
                msg = history.messages[0]
                if msg.id != ultima_id:
                    ultima_id = msg.id
                    print(f"\n📨 Nova do canal: {msg.message}")
                    if "OVER 0.5 HT" in msg.message:
                        await analisar(msg.message)
        except Exception as e:
            print(f"❌ Erro ao buscar mensagem no canal: {e}")

        await asyncio.sleep(10)
