# 🚀 Deploy Railway - Bot Telegram + WhatsApp Baileys

Este guia mostra como fazer deploy **100% funcional** no Railway com comunicação perfeita entre o Bot Telegram e servidor WhatsApp.

## 📋 Pré-requisitos

1. **Conta Railway** - [railway.app](https://railway.app)
2. **Token do Bot Telegram** - [@BotFather](https://t.me/BotFather)
3. **Token Mercado Pago** - [developers.mercadopago.com](https://developers.mercadopago.com)

## 🎯 Passos para Deploy

### 1. Preparar o Projeto
```bash
# Extrair o ZIP e navegar para a pasta
cd telegram-bot-railway-deploy
```

### 2. Configurar no Railway

1. **Novo Projeto**: Criar projeto no Railway
2. **Deploy from GitHub**: Conectar seu repositório
3. **Configurar Variáveis**:

```env
# Obrigatórias
BOT_TOKEN=seu_token_telegram_aqui
MERCADO_PAGO_ACCESS_TOKEN=seu_token_mp_aqui

# Railway configura automaticamente
DATABASE_URL=postgresql://...
RAILWAY_ENVIRONMENT_NAME=production
PORT=8080
```

### 3. Configurar Domínio

1. **Railway Dashboard** > **Settings** > **Public Networking**
2. **Generate Domain** - Será algo como: `app-name.up.railway.app`
3. **Copiar URL** - Usar para configurar webhook se necessário

### 4. Verificar Deploy

#### Logs do Telegram Bot:
```
🤖 Starting Telegram bot...
📊 Database configured: ✅
🌐 WhatsApp URL: http://localhost:3001
✅ Bot started successfully
```

#### Logs do WhatsApp:
```
🚀 Servidor Baileys Multi-User rodando na porta 3001
✅ Sistema de recuperação automática ativo
💾 Sessões persistentes em ./sessions/
```

## 🔗 Como Gerar QR Code

### Via Bot Telegram:
1. `/start` no bot
2. **"📱 WhatsApp"**
3. **"🔗 Conectar WhatsApp"**
4. **Escanear QR Code** com WhatsApp

### Via URL Direta:
```
https://seu-app.up.railway.app/qr/SEU_USER_ID
```

## 🛠️ Arquivos Principais

- **`main.py`**: Bot Telegram principal
- **`whatsapp_baileys_multi.js`**: Servidor WhatsApp Baileys
- **`railway.toml`**: Configuração Railway
- **`Procfile`**: Comandos de inicialização
- **`package.json`**: Dependências Node.js
- **`railway_requirements.txt`**: Dependências Python

## 🔧 Configurações Importantes

### Railway.toml
```toml
[build]
builder = "nixpacks"

[deploy]
numReplicas = 1
restartPolicyType = "ON_FAILURE"

[[services]]
name = "telegram-bot"
startCommand = "python main.py"

[[services]]
name = "whatsapp-baileys"
startCommand = "node whatsapp_baileys_multi.js"
```

### Procfile
```
web: python main.py
whatsapp: node whatsapp_baileys_multi.js
```

## 🚨 Troubleshooting

### ❌ Bot não conecta WhatsApp
```bash
# Verificar logs
railway logs

# Verificar variáveis
railway variables
```

### ❌ QR Code não gera
1. **Verificar porta**: WhatsApp deve rodar na porta 3001
2. **Verificar URL**: `http://localhost:3001` interno
3. **Forçar nova conexão**: Limpar sessões antigas

### ❌ Database não conecta
```env
# Railway fornece automaticamente
DATABASE_URL=postgresql://user:pass@host:port/db
```

## ✅ Verificações Finais

1. **Bot responde** `/start` ✅
2. **QR Code gera** via bot ✅
3. **WhatsApp conecta** após scan ✅
4. **Mensagens funcionam** ✅
5. **Database ativo** ✅

## 📞 Suporte

- **Logs Railway**: `railway logs --follow`
- **Status Services**: Railway Dashboard
- **Health Check**: `https://seu-app.up.railway.app/health`

---

**🎉 Seu bot está pronto para produção no Railway!**