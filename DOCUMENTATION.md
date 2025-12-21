# 📚 DOCUMENTAÇÃO COMPLETA - BOTBET

## 📋 ÍNDICE
1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Funcionalidades](#funcionalidades)
4. [Variáveis de Ambiente](#variáveis-de-ambiente)
5. [Como Obter as Chaves](#como-obter-as-chaves)
6. [Deploy](#deploy)
7. [Melhorias Recomendadas](#melhorias-recomendadas)

---

## 🎯 VISÃO GERAL

Sistema automatizado de análise e distribuição de sinais de apostas esportivas focado em **Over 0.5 HT** (gols no primeiro tempo).

### Componentes:
- **Bot de Análise** - Filtra sinais de alta qualidade (confiança >= 10 pontos)
- **Sistema de Assinaturas** - Monetização via Stripe (Trial/Mensal/Vitalício)
- **Landing Page** - Frontend para conversão de clientes
- **API de Métricas** - Monitoramento em tempo real

---

## 🏗️ ARQUITETURA

```
┌─────────────────────────────────────────────────────────┐
│                    TELEGRAM SOURCE                       │
│              (Canal com sinais originais)                │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  BOT PRINCIPAL (main.py)                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │ 1. Telethon escuta mensagens                      │  │
│  │ 2. Extrai dados (jogo, stats, clima)             │  │
│  │ 3. Calcula pontuação (10+ critérios)             │  │
│  │ 4. Busca fixture_id na API Football              │  │
│  │ 5. Verifica placar HT atual                       │  │
│  │ 6. Busca odds (pre-live → fallback live)         │  │
│  │ 7. Se >= 10 pts: envia sinal + agenda veredito   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              TELEGRAM DESTINATION                        │
│         (Canal VIP com sinais filtrados)                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│          SISTEMA DE ASSINATURAS (overbot_vip.py)         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Landing Page → Telegram Bot → Stripe Checkout     │  │
│  │ ↓ Payment ↓ Webhook ↓ Ativa Assinatura           │  │
│  │ ↓ Cria Convite → Envia ao usuário                 │  │
│  │ Health Check (1h) → Verifica expirados → Expulsa │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│       ESTATÍSTICAS (estatisticas_time.py)                │
│  PostgreSQL/SQLite → Cache 7 dias → API Football        │
│  Histórico H2H → Bônus/Penalidade → Métricas            │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ FUNCIONALIDADES

### 1. BOT PRINCIPAL (main.py) - ATIVO ✅

**Fluxo:**
1. Escuta sinais via Telethon do CHAT_ID_SINAL
2. Filtra apenas mensagens com "OVER 0.5 HT" + "Inteligência Artificial"
3. Extrai dados: jogo, minuto, IA%, ataques, posse, escanteios, clima
4. Calcula pontuação técnica (0-10 pts) + clima (0-4 pts) + histórico
5. Se total >= 10 pontos (ALTA/MUITO ALTA):
   - Busca fixture_id na API Football
   - Verifica placar atual (rejeita se >= 3 gols HT)
   - Busca odd pre-live (fallback para odd ao vivo)
   - Envia sinal formatado para CHAT_ID_DESTINO
   - Agenda veredito automático após 35 minutos
6. Se < 10 pontos: ignora sinal

**Critérios de Pontuação (máx 14+ pts):**
- IA >= 70%: +2 pts
- Minuto 16-22: +1 pt
- Ataques perigosos: +2 pts
- Finalizações no gol: +2 pts
- Escanteios >= 2: +1 pt
- Chutes >= 4: +1 pt
- Posse >= 60%: +1 pt
- Temperatura 18-28°C: +1 pt
- Nebulosidade >= 20%: +1 pt
- Umidade 50-75%: +1 pt
- Vento <= 7 m/s: +1 pt (ou 0.5 se 7-10 m/s)
- Histórico favorável: +1 pt
- Histórico moderado: +0.5 pt
- Último resultado RED: -0.5 pt

**Filtros:**
- Ignora U20/U19
- Ignora fora da janela 08:00-00:00 (São Paulo)
- Ignora se >= 3 gols HT

### 2. SISTEMA DE ASSINATURAS (overbot_vip.py) - ATIVO ✅

**Funcionalidades:**
- Landing page HTML5 responsiva com 3 planos
- Bot Telegram admin com comandos (/start)
- Integração completa Stripe (checkout + webhook)
- Criação automática de convites únicos para canal VIP
- Gerenciamento de usuários no banco (User model)
- Tarefas periódicas (health check a cada 1 hora):
  - Verifica trials expirando (últimas 24h) → envia oferta R$ 49,90
  - Verifica assinaturas expiradas → expulsa do canal

**Planos:**
| Plano | Preço | Duração | Observações |
|-------|-------|---------|-------------|
| Trial | Grátis | 3 dias | Uso único, 24h antes do fim recebe oferta |
| Mensal | R$ 29,87 | 30 dias | Renovação manual |
| Vitalício | R$ 197,87 | Eterno | Pagamento único |
| Oferta | R$ 49,90 | Eterno | Apenas para usuários em trial |

**Endpoints:**
- `/` - Landing page
- `/{BOT_TOKEN_ADMIN}` - Webhook Telegram
- `/stripe-webhook` - Webhook Stripe  
- `/health` - Health check + tarefas periódicas

### 3. ESTATÍSTICAS (estatisticas_time.py) - ATIVO ✅

**Funcionalidades:**
- Busca histórico de confrontos diretos via API Football
- Calcula gols no primeiro tempo (últimos 5 jogos)
- Salva/atualiza resultados no banco
- Cache de fixtures (7 dias configurable)
- Bônus/penalidade baseado em histórico:
  - >= 70% GREEN: +1 pt (HIST_BONUS_HIGH)
  - >= 55% GREEN: +0.5 pt (HIST_BONUS_MED)
  - Último RED: -0.5 pt (HIST_PENALTY_RED)
- Métricas de performance (fixture_found, odds_retry, etc.)

**Banco de Dados:**
- PostgreSQL (produção) ou SQLite (dev/fallback)
- Tabelas:
  - `historico_resumos` - Confrontos diretos
  - `fixtures_cache` - Cache de fixtures da API
  - `user` - Usuários e assinaturas (overbot_vip)

### 4. OPENAI (ia_openai.py) - INATIVO ❌

**Status:** Implementado mas nunca é chamado

**Potencial:**
- Gerar explicações em linguagem natural
- Contextualizar análises técnicas
- Melhorar engajamento dos usuários

**Função:**
```python
async def gerar_resposta_ia(pergunta)
# Usa GPT-3.5-turbo com prompt especializado em futebol
```

### 5. MÉTRICAS (keep_alive.py) - ATIVO ✅

**Endpoints:**
- `/` - Status do webhook
- `/metrics` - Métricas em JSON (timestamp + counters)

**Métricas rastreadas:**
- fixture_found, fixture_retry
- odds_retry, odds_pre_live_retry
- Outros eventos customizados via `metric(nome)`

---

## 🔑 VARIÁVEIS DE AMBIENTE

### ✅ OBRIGATÓRIAS (Bot Principal)

```bash
# Telegram
BOT_TOKEN=              # Token do bot (via @BotFather)
API_ID=                 # API ID (via my.telegram.org)
API_HASH=               # API Hash (via my.telegram.org)
CHAT_ID_SINAL=          # ID do canal fonte (número negativo)
CHAT_ID_DESTINO=        # ID do canal destino (número negativo)

# API Football
FOOTBALL_API_KEY=       # Chave da API (api-sports.io)
```

### ✅ OBRIGATÓRIAS (Sistema de Assinaturas)

```bash
# Telegram Admin
BOT_TOKEN_ADMIN=        # Token do bot admin
CHANNEL_ID_ADMIN=       # ID do canal VIP

# Banco de Dados
DATABASE_URL=           # URL PostgreSQL completa

# Stripe
STRIPE_API_KEY=         # Secret key
STRIPE_WEBHOOK_SECRET=  # Webhook signing secret
STRIPE_LINK_MENSAL=     # URL checkout mensal
STRIPE_LINK_VITALICIO=  # URL checkout vitalício
STRIPE_LINK_OFERTA_VITALICIO= # URL checkout oferta
```

### 📦 OPCIONAIS (Com valores padrão)

```bash
# Configuração Admin
ADMIN_USER_ID=895248440      # ID do administrador
BOT_USERNAME_ADMIN=overbotvip_bot  # Username do bot

# Pontuação Histórico
HIST_BONUS_HIGH=0.65         # Bônus alto
HIST_BONUS_MED=0.50          # Bônus médio
HIST_PENALTY_RED=0.50        # Penalidade RED

# Banco Local
ESTATISTICAS_DB_PATH=estatisticas.db
ESTATISTICAS_CACHE_DIAS=7

# Servidor
PORT=8080

# OpenAI (Inativa)
OPENAI_API_KEY=              # Chave API OpenAI
```

---

## 📝 COMO OBTER AS CHAVES

### 1. Telegram Bot Token (BOT_TOKEN)
1. Abra o Telegram → **@BotFather**
2. Envie `/newbot`
3. Siga instruções e copie o token

### 2. Telegram API (API_ID, API_HASH)
1. Acesse https://my.telegram.org
2. Login com seu número
3. "API Development Tools"
4. Crie app → copie API_ID e API_HASH

### 3. Chat IDs (CHAT_ID_SINAL, CHAT_ID_DESTINO)

**Método 1 - Via Bot:**
1. Adicione bot ao canal
2. Envie mensagem
3. Acesse: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Procure `"chat":{"id":-100...}`

**Método 2 - Via @userinfobot:**
1. Encaminhe mensagem do canal para @userinfobot
2. Copie o ID (negativo para canais)

### 4. Football API (FOOTBALL_API_KEY)
1. https://www.api-football.com/
2. Crie conta (gratuita ou paga)
3. Dashboard → copie API key

### 5. Stripe (Pagamentos)

**STRIPE_API_KEY:**
- Dashboard → Developers → API Keys → Secret Key

**STRIPE_WEBHOOK_SECRET:**
- Dashboard → Developers → Webhooks
- Add endpoint: `https://seu-dominio.com/stripe-webhook`
- Select event: `checkout.session.completed`
- Copie Signing Secret

**STRIPE_LINK_* (3 links):**
- Dashboard → Products → Create product
- Pricing: R$ 29.87 (mensal), R$ 197.87 (vitalício), R$ 49.90 (oferta)
- Create payment link
- Copie cada URL

### 6. PostgreSQL (DATABASE_URL)

**Railway.app (Recomendado):**
1. https://railway.app
2. New Project → Add PostgreSQL
3. Copie DATABASE_URL

**Heroku:**
1. App → Add-ons → Heroku Postgres
2. Settings → Config Vars → DATABASE_URL

**Local:**
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/botbet
```

### 7. OpenAI (OPENAI_API_KEY) - OPCIONAL
1. https://platform.openai.com
2. API Keys → Create new secret key

---

## 🚀 DEPLOY

### Railway.app (Recomendado)

1. Conecte repositório GitHub
2. Add PostgreSQL service
3. Configure variáveis em "Variables"
4. Deploy automático

### Heroku

```bash
heroku create nome-do-app
heroku addons:create heroku-postgresql:mini
heroku config:set BOT_TOKEN=...
# (repetir para cada variável)
git push heroku main
```

### VPS (Manual)

```bash
# Clone
git clone https://github.com/seu-user/botbet
cd botbet

# Ambiente
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar .env
nano .env  # adicione todas as variáveis

# Executar
# Bot principal:
python main.py

# Web (assinaturas):
gunicorn overbot_vip:app --bind 0.0.0.0:8080 --workers 2
```

---

## 💡 MELHORIAS RECOMENDADAS

### 🔥 Prioridade ALTA (Semana 1-2)

1. **Ativar OpenAI** ⭐
   - Integrar `gerar_resposta_ia()` em `analisar()`
   - Adicionar toggle via variável de ambiente
   - Enviar explicação contextual com cada sinal

2. **Validar Stripe Signature** 🔒
   - Adicionar verificação de signature no webhook
   - Prevenir webhooks falsos
   ```python
   import stripe
   sig = request.headers.get('Stripe-Signature')
   event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
   ```

3. **Rate Limiting** 🚦
   - Proteger rotas Flask
   - Usar `flask-limiter`
   - Prevenir abuse

4. **Documentação Inline** 📄
   - Adicionar docstrings às funções
   - Comentar lógica complexa
   - Explicar números mágicos

### 📈 Prioridade MÉDIA (Mês 1-2)

1. **Dashboard Admin** 📊
   - Painel web para visualizar métricas
   - Gerenciar usuários
   - Análise de conversão
   - Ver histórico de sinais GREEN/RED

2. **Notificações Push** 🔔
   - Avisar usuários sobre resultados
   - Estatísticas diárias/semanais
   - Alertas de performance

3. **Relatórios Automáticos** 📈
   - Performance diária/semanal/mensal
   - ROI tracking
   - Análise de assertividade

4. **Testes A/B** 🧪
   - Otimizar conversão de trials
   - Testar diferentes mensagens
   - Melhorar landing page

### 🔮 Prioridade BAIXA (Mês 3-6)

1. **Machine Learning** 🤖
   - Prever probabilidades com ML
   - Treinar modelo com histórico
   - Scoring automático

2. **Multi-idiomas** 🌍
   - Inglês/Espanhol
   - Configuração por usuário
   - i18n completo

3. **Mobile App** 📱
   - App nativo iOS/Android
   - Notificações push nativas
   - Interface otimizada

4. **Múltiplos Mercados** ⚽
   - Over 1.5, 2.5
   - BTTS (ambos marcam)
   - Corners, cards
   - Asian handicaps

---

## ⚠️ SEGURANÇA

### ✅ BOAS PRÁTICAS:
- Variáveis de ambiente para secrets
- Logging detalhado
- Testes automatizados
- HTTPS em webhooks

### ⚠️ A IMPLEMENTAR:
- Validação de signature Stripe
- Rate limiting
- Connection pooling DB
- Retry automático em falhas
- Sanitização de inputs

### ❌ NUNCA:
- Commitar .env no Git
- Compartilhar chaves em público
- Usar modo test Stripe em produção
- Expor DATABASE_URL em logs

---

## 📊 MÉTRICAS

### Código:
- **2.014 linhas** de Python
- **5 arquivos** principais
- **3 arquivos** de testes
- **69 testes** unitários/E2E
- **13 dependências**

### Performance:
- Cache de 7 dias para fixtures
- Timeout de 12-15s nas APIs
- Retry automático (2 tentativas)
- Métricas em tempo real

### Cobertura de Testes:
- ✅ Funções utilitárias (100%)
- ✅ Análise de clima (100%)
- ✅ Análise de sinais (mocked)
- ✅ API integration (mocked)
- ✅ Botadmin (100%)

---

## 📞 SUPORTE

- **Repositório:** https://github.com/bcaffe88/botbet
- **Issues:** Use GitHub Issues para bugs
- **Discussões:** GitHub Discussions para perguntas

---

**Última atualização:** 21/12/2025
**Versão:** 3.3 (Produção)
