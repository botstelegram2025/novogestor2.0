import express from "express";
import cors from "cors";
import qrcode from "qrcode";
import { Boom } from "@hapi/boom";
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState
} from "@whiskeysockets/baileys";

const PORT = process.env.PORT || 3000;
const AUTH_DIR = process.env.AUTH_DIR || "./baileys_auth";

let sock;
let latestQR = null;

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  sock = makeWASocket({
    printQRInTerminal: true,
    auth: state,
    logger: undefined // silencioso; logs ficam no Python
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      latestQR = qr;
      console.log("[Baileys] QR atualizado");
    }

    if (connection === "close") {
      const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;
      console.log("[Baileys] conexão encerrada", reason);
      if (reason !== DisconnectReason.loggedOut) {
        start().catch((e) => console.error("[Baileys] restart error", e));
      } else {
        console.log("[Baileys] logout detectado, será necessário reescanear QR");
      }
    } else if (connection === "open") {
      latestQR = null;
      console.log("[Baileys] conectado");
    }
  });
}

const app = express();
app.use(cors());
app.use(express.json());

// Retorna QR em PNG base64 para pareamento
app.get("/qr", async (_req, res) => {
  if (!latestQR) return res.json({ status: "connected_or_wait", qr_png: null });
  const png = await qrcode.toDataURL(latestQR, { margin: 2, scale: 6 });
  res.json({ status: "scan_me", qr_png: png });
});

// Envia mensagem de texto
// body: { to: "+5585999999999", text: "mensagem" }
app.post("/send", async (req, res) => {
  try {
    if (!sock) return res.status(500).json({ ok: false, error: "sock_not_ready" });
    const { to, text } = req.body || {};
    if (!to || !text) return res.status(400).json({ ok: false, error: "missing to/text" });

    // Formato JID do WhatsApp
    const jid = to.replace(/[^\d]/g, "") + "@s.whatsapp.net";

    await sock.sendMessage(jid, { text });
    return res.json({ ok: true });
  } catch (e) {
    console.error("[Baileys] /send error", e);
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

app.listen(PORT, () => {
  console.log(`[Baileys] HTTP na porta ${PORT}`);
  start().catch((e) => console.error("[Baileys] start error", e));
});
