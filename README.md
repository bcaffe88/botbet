# 🤖 BotBet - Sistema de Análise de Sinais Over 0.5 HT

Bot automatizado de análise e distribuição de sinais de apostas esportivas focado em **Over 0.5 HT** (gols no primeiro tempo), com sistema integrado de assinaturas via Stripe.

## 🎯 Funcionalidades Principais

### 1. Bot de Análise Inteligente
- ✅ Escuta sinais via Telegram Telethon
- ✅ Analisa 10+ critérios (IA, clima, estatísticas, histórico)
- ✅ Filtra apenas sinais de alta confiança (>= 10 pontos)
- ✅ Busca odds em tempo real via API Football
- ✅ Veredito automático após 35 minutos

### 2. Sistema de Assinaturas
- ✅ Landing page responsiva com 3 planos
- ✅ Integração completa com Stripe
- ✅ Trial gratuito de 3 dias
- ✅ Gerenciamento automático de convites VIP
- ✅ Expulsão automática de usuários expirados

### 3. Estatísticas e Histórico
- ✅ Histórico de confrontos diretos
- ✅ Métricas de gols no primeiro tempo
- ✅ Cache inteligente (7 dias)
- ✅ PostgreSQL + SQLite fallback

## 🚀 Início Rápido

### 1. Clone o repositório
```bash
git clone https://github.com/bcaffe88/botbet
cd botbet
```

### 2. Instale dependências
```bash
pip install -r requirements.txt
```

### 3. Configure variáveis de ambiente
Crie um arquivo `.env` com as variáveis necessárias (veja [DOCUMENTATION.md](DOCUMENTATION.md#variáveis-de-ambiente))

### 4. Execute

**Bot principal:**
```bash
python main.py
```

**Sistema de assinaturas:**
```bash
gunicorn overbot_vip:app --bind 0.0.0.0:8080
```

## 📋 Variáveis de Ambiente Obrigatórias

```bash
# Telegram
BOT_TOKEN=              # Token do bot
API_ID=                 # API ID do Telegram
API_HASH=               # API Hash
CHAT_ID_SINAL=          # Canal fonte de sinais
CHAT_ID_DESTINO=        # Canal destino (filtrado)

# API Football
FOOTBALL_API_KEY=       # Chave api-sports.io

# Sistema de Assinaturas
BOT_TOKEN_ADMIN=        # Bot admin
CHANNEL_ID_ADMIN=       # Canal VIP
DATABASE_URL=           # PostgreSQL URL
STRIPE_API_KEY=         # Stripe secret key
STRIPE_WEBHOOK_SECRET=  # Stripe webhook secret
STRIPE_LINK_MENSAL=     # Link checkout mensal
STRIPE_LINK_VITALICIO=  # Link checkout vitalício
STRIPE_LINK_OFERTA_VITALICIO= # Link oferta
```

👉 **Veja [DOCUMENTATION.md](DOCUMENTATION.md) para documentação completa**

## 📊 Planos de Assinatura

| Plano | Preço | Duração | Benefícios |
|-------|-------|---------|------------|
| **Trial** | Grátis | 3 dias | Teste completo do sistema |
| **Mensal** | R$ 29,87 | 30 dias | Acesso contínuo |
| **Vitalício** | R$ 197,87 | Eterno | Pagamento único |
| **Oferta** | R$ 49,90 | Eterno | Apenas para trials (últimas 24h) |

## 🔧 Tecnologias

- **Python 3.12+**
- **Telegram Bot API** + **Telethon**
- **Flask** + **SQLAlchemy**
- **PostgreSQL** / SQLite
- **Stripe** (pagamentos)
- **API Football** (api-sports.io)
- **pytest** (testes)

## 📁 Estrutura do Projeto

```
botbet/
├── main.py                 # Bot principal de análise
├── overbot_vip.py          # Sistema de assinaturas
├── estatisticas_time.py    # Estatísticas e histórico
├── ia_openai.py            # Integração OpenAI (inativa)
├── keep_alive.py           # Servidor de métricas
├── requirements.txt        # Dependências
├── Procfile               # Configuração deploy
├── pytest.ini             # Configuração testes
├── tests/                 # Testes unitários e E2E
│   ├── test_e2e.py
│   ├── test_botadmin.py
│   └── test_historico.py
├── DOCUMENTATION.md       # Documentação completa
└── README.md             # Este arquivo
```

## 🧪 Testes

```bash
# Rodar todos os testes
pytest

# Testes específicos
pytest tests/test_e2e.py -v
pytest tests/test_botadmin.py -v

# Com cobertura
pytest --cov=. --cov-report=html
```

**Cobertura atual:** 69 testes (66 E2E + 3 histórico + 15 botadmin)

## 📚 Documentação

- **[DOCUMENTATION.md](DOCUMENTATION.md)** - Documentação completa
- **[.env.example](.env.example)** - Exemplo de configuração
- **Inline docs** - Docstrings nas funções principais

## 🔒 Segurança

- ✅ Todas as secrets em variáveis de ambiente
- ✅ Logging detalhado sem expor dados sensíveis
- ✅ HTTPS obrigatório para webhooks
- ⚠️ Implemente validação de signature Stripe
- ⚠️ Adicione rate limiting nas rotas Flask

## 🚀 Deploy

### Railway.app (Recomendado)
1. Conecte repositório GitHub
2. Add PostgreSQL
3. Configure variáveis
4. Deploy automático ✅

### Heroku
```bash
heroku create nome-app
heroku addons:create heroku-postgresql
heroku config:set BOT_TOKEN=... # para cada variável
git push heroku main
```

### Docker (Opcional)
```bash
docker build -t botbet .
docker run -d --env-file .env botbet
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Add: nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## 📝 Changelog

### v3.3 (Atual)
- ✅ Fix: Indentação em buscar_odd_ao_vivo
- ✅ Add: 69 testes E2E e unitários
- ✅ Fix: Bugs no botadmin (_bootstrap_tables, BOT_USERNAME_ADMIN)
- ✅ Add: Documentação completa

### v3.2
- Sistema de assinaturas Stripe
- Landing page responsiva
- Health check periódico

### v3.1
- Histórico de confrontos
- Cache de fixtures
- Métricas de performance

## 📞 Suporte

- **Issues:** https://github.com/bcaffe88/botbet/issues
- **Admin:** @bcaffe

## 📄 Licença

Este projeto é privado. Todos os direitos reservados.

---

**Made with ⚽ by @bcaffe88**
