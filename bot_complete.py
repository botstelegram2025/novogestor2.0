const { makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');
const QRCode = require('qrcode');

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN || 'SEU_TOKEN_DO_TELEGRAM';

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

let whatsappSock;
let lastQrCode = null;
let startedWA = false;

// Teclado persistente com botão para QR Code
const teclado = {
  reply_markup: {
    keyboard: [
      [{ text: 'Gerar QR WhatsApp' }]
    ],
    resize_keyboard: true,
    one_time_keyboard: false
  }
};

// Comando /start exibe teclado persistente
bot.onText(/\/start/, (msg) => {
  bot.sendMessage(msg.chat.id, 'Bem-vindo! Use o botão abaixo para gerar o QR Code do WhatsApp.', teclado);
});

// Botão "Gerar QR WhatsApp"
bot.on('message', async (msg) => {
  if (msg.text === 'Gerar QR WhatsApp') {
    // Só inicia a conexão com WhatsApp se ainda não iniciou
    if (!startedWA) {
      startedWA = true;
      bot.sendMessage(msg.chat.id, 'Gerando QR Code, aguarde...');
      iniciarWhatsApp(msg.chat.id);
    } else if (lastQrCode) {
      // QR já gerado, envie novamente
      try {
        const qrBuffer = await QRCode.toBuffer(lastQrCode);
        bot.sendPhoto(msg.chat.id, qrBuffer, { caption: 'Escaneie este QR Code com seu WhatsApp!' });
      } catch (e) {
        bot.sendMessage(msg.chat.id, 'Erro ao gerar imagem do QR Code.');
      }
    } else {
      bot.sendMessage(msg.chat.id, 'Nenhum QR Code disponível no momento. O WhatsApp já pode estar conectado ou em processo de conexão.');
    }
  }
});

// Função para iniciar WhatsApp
async function iniciarWhatsApp(telegramChatId) {
  try {
    // Apaga credenciais antigas antes de iniciar
    if (fs.existsSync('auth_info_baileys')) {
      fs.rmSync('auth_info_baileys', { recursive: true, force: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    const sock = makeWASocket({ 
      auth: state,
      printQRInTerminal: true
    });

    whatsappSock = sock;

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      if (update.qr) {
        lastQrCode = update.qr;
        try {
          const qrBuffer = await QRCode.toBuffer(update.qr);
          await bot.sendPhoto(telegramChatId, qrBuffer, { caption: 'Escaneie este QR Code com seu WhatsApp!' });
        } catch (e) {
          bot.sendMessage(telegramChatId, 'Erro ao gerar imagem do QR Code.');
        }
      }
      if (update.connection === 'close') {
        console.log('WhatsApp desconectado. Apagando credenciais e aguardando novo login...');
        try {
          fs.rmSync('auth_info_baileys', { recursive: true, force: true });
          console.log('auth_info_baileys removido. Reinicie o bot para novo login.');
        } catch(err) {
          console.error('Erro ao apagar pasta de autenticação:', err);
        }
        // Permite nova tentativa
        startedWA = false;
        lastQrCode = null;
      }
      if (update.connection === 'open') {
        bot.sendMessage(telegramChatId, 'WhatsApp conectado com sucesso!');
      }
    });
  } catch (err) {
    console.error('Erro ao conectar ao WhatsApp:', err);
    try {
      fs.rmSync('auth_info_baileys', { recursive: true, force: true });
      console.log('Pasta auth_info_baileys removida. Reinicie o bot para novo login WhatsApp.');
    } catch (e) {
      console.error('Erro ao tentar limpar autenticação Baileys:', e);
    }
    startedWA = false;
    lastQrCode = null;
    bot.sendMessage(telegramChatId, 'Erro ao conectar ao WhatsApp. Tente novamente.');
  }
}

// Tratamento para erro de polling do Telegram
bot.on('polling_error', (err) => {
  if (err.code === 'ETELEGRAM' && err.message.includes('409 Conflict')) {
    console.error('Erro de polling do Telegram: Só pode rodar UMA instância do bot. Pare qualquer outro serviço/container/bot usando esse token!');
    if (process.env.TELEGRAM_ADMIN_ID) {
      bot.sendMessage(
        process.env.TELEGRAM_ADMIN_ID,
        'Erro: Só pode rodar UMA instância do bot Telegram com esse token! Pare outros bots que estejam rodando.'
      );
    }
    process.exit(1);
  } else {
    console.error('Polling error:', err);
  }
});
