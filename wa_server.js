const express = require("express");
const { default: makeWASocket, useMultiFileAuthState } = require("@whiskeysockets/baileys");
const QRCode = require("qrcode");

const app = express();
app.use(express.json());
const PORT = process.env.WA_PORT || 3000;

let sock = null;
let qrDataUrl = "";
let logs = [];

function logPush(msg) {
  const ts = new Date().toISOString();
  logs.push(`[${ts}] ${msg}`);
  if (logs.length > 500) logs = logs.slice(-300);
  console.log(msg);
}

async function connectWA() {
  const { state, saveCreds } = await useMultiFileAuthState("./wa_auth");
  sock = makeWASocket({ auth: state, printQRInTerminal: true });

  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (update) => {
    const { connection, qr, lastDisconnect } = update;
    if (qr) {
      try {
        qrDataUrl = await QRCode.toDataURL(qr);
        logPush("QR code atualizado.");
      } catch (e) { logPush("Falha ao gerar QR: " + e.message); }
    }
    if (connection === "open") {
      logPush("✅ WhatsApp conectado.");
    }
    if (connection === "close") {
      logPush("❌ Conexão encerrada, tentando reconectar...");
      setTimeout(connectWA, 2000);
    }
  });
}

// ---- Endpoints ----
app.get("/status", (req, res) => {
  res.json({ status: sock?.user ? "connected" : "disconnected", user: sock?.user || null });
});
app.get("/health", (req, res) => {
  res.json({ connected: !!sock?.user });
});

app.get("/qr", (req, res) => {
  if (!qrDataUrl) return res.send("QR ainda não gerado. Aguarde...");
  res.send(`<html><body><img src="${qrDataUrl}" style="max-width:320px"/></body></html>`);
});

app.get("/logs", (req, res) => res.json(logs));

app.get("/logout", async (req, res) => {
  try {
    if (sock) await sock.logout();
    logPush("Sessão encerrada por API.");
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

app.post("/send", async (req, res) => {
  try {
    const { to, text } = req.body || {};
    if (!sock?.user) return res.status(400).json({ ok: false, error: "not_connected" });
    if (!to || !text) return res.status(400).json({ ok: false, error: "missing_fields" });
    const jid = to.startsWith("+") || to.match(/^\d+$/) ? to.replace(/\D/g, "") + "@s.whatsapp.net" : to;
    await sock.sendMessage(jid, { text });
    logPush(`Mensagem enviada para ${jid}: ${text}`);
    res.json({ ok: true });
  } catch (e) {
    logPush("Erro /send: " + e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

const timers = new Map();
app.post("/schedule", async (req, res) => {
  try {
    const { to, text, send_at } = req.body || {};
    if (!to || !text || !send_at) return res.status(400).json({ ok: false, error: "missing_fields" });
    const when = new Date(send_at);
    const delay = when.getTime() - Date.now();
    if (delay < 0) return res.status(400).json({ ok: false, error: "past_time" });

    const id = Date.now().toString(36);
    const t = setTimeout(async () => {
      try {
        if (!sock?.user) { logPush("Agendado falhou: não conectado."); return; }
        const jid = to.replace(/\D/g, "") + "@s.whatsapp.net";
        await sock.sendMessage(jid, { text });
        logPush(`Agendado enviado para ${jid}: ${text}`);
      } catch (e) {
        logPush("Erro ao enviar agendado: " + e.message);
      } finally {
        timers.delete(id);
      }
    }, delay);
    timers.set(id, t);
    logPush(`Agendamento criado ${id} para ${send_at} -> ${to}`);
    res.json({ ok: true, id, send_at });
  } catch (e) {
    logPush("Erro /schedule: " + e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

app.listen(PORT, () => {
  console.log("Baileys API em http://localhost:" + PORT);
  connectWA();
});
