# Bot de Refinamento de Sinais com Webhook

Este bot escuta sinais via Telegram, aplica um sistema de análise com critérios técnicos, e envia um veredito estruturado para um grupo. Ele também monitora odds e envia alerta com link para aposta quando a odd atingir 1.50+.

## Comandos disponíveis:
- /start
- /veredito
- /testar
- /testefraco
- /testevento
- /id

## Requisitos de Ambiente (Secrets):
- BOT_TOKEN
- API_ID
- API_HASH
- CHAT_ID_SINAL
- CHAT_ID_DESTINO
- ODDS_API_KEY
- WEBHOOK_URL (ex: https://seu-projeto.up.railway.app)
