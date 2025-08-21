import makeWASocket, { useMultiFileAuthState } from "@whiskeysockets/baileys";
import express from "express";
import qrcode from "qrcode";

const app = express();
const PORT = 3000;

let sock;
let logs = [];

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState("wa_auth");
  sock = makeWASocket({ auth: state });

  sock.ev.on("connection.update", ({ connection, qr }) => {
    if (qr) {
      qrcode.toDataURL(qr, (err, url) => {
        logs.push("Novo QR gerado");
        app.set("qr", url);
      });
    }
    if (connection === "open") {
      logs.push("✅ Conectado ao WhatsApp");
    }
    if (connection === "close") {
      logs.push("❌ Desconectado, tentando reconectar...");
      connectToWhatsApp();
    }
  });

  sock.ev.on("creds.update", saveCreds);
}

app.get("/status", (req, res) => {
  res.json({ status: sock?.user ? "connected" : "disconnected", user: sock?.user });
});

app.get("/qr", (req, res) => {
  res.send(`<img src="${app.get("qr") || ""}" />`);
});

app.get("/logs", (req, res) => {
  res.json(logs.slice(-20));
});

app.get("/logout", async (req, res) => {
  await sock?.logout();
  logs.push("Sessão encerrada manualmente");
  res.json({ ok: true });
});

app.use(express.json());
app.post("/schedule", async (req, res) => {
  const { number, message } = req.body;
  try {
    await sock.sendMessage(number + "@s.whatsapp.net", { text: message });
    logs.push(`Mensagem enviada para ${number}: ${message}`);
    res.json({ ok: true });
  } catch (e) {
    logs.push("Erro ao enviar mensagem: " + e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

connectToWhatsApp();
app.listen(PORT, () => console.log("Baileys API rodando em http://localhost:" + PORT));
