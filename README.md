# Bot de Sinais Telegram (Refinador)

Este é um bot Telegram para receber sinais de futebol, analisar com base em critérios técnicos e enviar vereditos automáticos.

## ✔️ Recursos
- Recebe sinais da Betzord
- Refina com critérios técnicos (IA, minuto, vento, ataques etc.)
- Envia para grupo do Telegram
- Comandos: /start, /veredito, /testar, etc.

## 🚀 Como rodar na Railway

1. Crie conta em https://railway.app
2. Crie novo projeto > Deploy from GitHub
3. Adicione os seguintes Secrets:

```
API_ID = seu valor
API_HASH = seu valor
BOT_TOKEN = seu valor
CHAT_ID_SINAL = -100xxxxxxxxx
CHAT_ID_DESTINO = -100xxxxxxxxx
```

4. Railway detectará `Procfile` e iniciará com `python3 main.py`

✅ Rodando 24h em nuvem gratuitamente.
