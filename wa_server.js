// wa_server.js
// Servidor Baileys + API HTTP + worker de agendamento no Postgres
// Foco em facilitar a geração do QR (rotas /qr, /qr.png, /qr.txt) e recuperação.

const express = require('express');
const cors = require('cors');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const pino = require('pino');
const QRCode = require('qrcode');
const { Pool } = require('pg');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason
} = require('@whiskeysockets/baileys');

const PORT = process.env.PORT || 3000;
const AUTH_DIR = path.join(__dirname, 'wa_auth');
const DATABASE_URL = process.env.DATABASE_URL;
const LOG_LEVEL = process.env.WA_LOG_LEVEL || 'info'; // info|warn|error|fatal
const PRINT_QR_IN_TERM = process.env.WA_PRINT_QR_IN_TERMINAL === '1';
const FORCE_VERSION = process.env.WA_FORCE_VERSION || ''; // ex: "2.3000.0" (major.minor.patch)

if (!DATABASE_URL) {
  console.error('DATABASE_URL não definido');
  process.exit(1);
}

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

// ---- Estado do Baileys ----
let sock = null;
let lastQR = null;          // dataURL
let lastQRpng = null;       // Buffer PNG
let isConnected = false;
let meJid = null;
let waVersion = null;
let starting = false;

// ---- Utils ----
function normalizeToJid(to) {
  if (!to) return null;
  let p = String(to).replace(/\D/g, '');
  if (p.startsWith('0')) p = p.replace(/^0+/, '');
  if (!p.startsWith('55')) p = '55' + p; // ajuste simples para BR
  return `${p}@s.whatsapp.net`;
}

function parseVersionString(v) {
  try {
    const [maj, min, pat] = v.split('.').map((x) => parseInt(x, 10));
    if ([maj, min, pat].some((n) => Number.isNaN(n))) return null;
    return [maj, min, pat];
  } catch { return null; }
}

async function ensureJobsTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS wa_jobs (
      id BIGSERIAL PRIMARY KEY,
      to_jid TEXT NOT NULL,
      message TEXT NOT NULL,
      send_at TIMESTAMPTZ NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued',
      error TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      sent_at TIMESTAMPTZ
    );
  `);
}

// ---- Baileys ----
async function getBaileysVersion() {
  if (FORCE_VERSION) {
    const parsed = parseVersionString(FORCE_VERSION);
    if (parsed) {
      console.log(`[WA] Usando versão forçada: ${FORCE_VERSION}`);
      return parsed;
    }
    console.warn(`[WA] WA_FORCE_VERSION inválida (${FORCE_VERSION}). Ignorando.`);
  }
  try {
    const { version } = await fetchLatestBaileysVersion();
    return version;
  } catch (e) {
    console.warn('[WA] Falha ao buscar versão. Usando fallback 2.3000.0', e?.message || e);
    return [2, 3000, 0];
  }
}

async function startBaileys() {
  if (starting) return;
  starting = true;

  try {
    if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true });
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    waVersion = await getBaileysVersion();

    const logger = pino({ level: LOG_LEVEL });

    sock = makeWASocket({
      version: waVersion,
      auth: state,
      printQRInTerminal: PRINT_QR_IN_TERM,
      logger
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        // Gera DataURL e PNG
        try {
          lastQR = await QRCode.toDataURL(qr);
          lastQRpng = await QRCode.toBuffer(qr, { type: 'png', scale: 6, margin: 2 });
          console.log('[WA] QR gerado.');
        } catch (e) {
          console.error('[WA] Falha ao gerar QR:', e);
          lastQR = null;
          lastQRpng = null;
        }
        isConnected = false;
      }

      if (connection === 'open') {
        isConnected = true;
        lastQR = null;
        lastQRpng = null;
        meJid = sock.user?.id || null;
        console.log('[WA] Conectado como', meJid);
      } else if (connection === 'close') {
        isConnected = false;
        const status = lastDisconnect?.error?.output?.statusCode;
        const reason = lastDisconnect?.error?.message || status;
        console.warn('[WA] Conexão fechada:', reason);

        // Reconecta automaticamente, exceto logout explícito
        if (status !== DisconnectReason.loggedOut) {
          setTimeout(startBaileys, 3000);
        }
      }
    });
  } catch (e) {
    console.error('[WA] Erro ao iniciar Baileys:', e);
    setTimeout(startBaileys, 5000);
  } finally {
    starting = false;
  }
}

// ---- Rotas HTTP ----
app.get('/', (_req, res) => res.redirect('/health'));

app.get('/version', (_req, res) => {
  res.json({ version: waVersion, forced: !!FORCE_VERSION });
});

app.get('/health', async (_req, res) => {
  try {
    const { rows } = await pool.query(`SELECT COUNT(*)::int AS count FROM wa_jobs WHERE status='queued';`);
    return res.json({
      connected: isConnected,
      me: meJid,
      queued: rows?.[0]?.count || 0
    });
  } catch (e) {
    return res.status(500).json({ error: String(e) });
  }
});

// DataURL (útil para Telegram bot transformar em foto)
app.get('/qr', (_req, res) => {
  if (isConnected) return res.json({ connected: true, qr: null });
  if (!lastQR) return res.status(503).json({ connected: false, qr: null, error: 'QR indisponível no momento' });
  return res.json({ connected: false, qr: lastQR });
});

// PNG (útil para abrir direto no navegador)
app.get('/qr.png', (_req, res) => {
  if (isConnected) return res.status(204).end();
  if (!lastQRpng) return res.status(503).send('QR indisponível no momento');
  res.setHeader('Content-Type', 'image/png');
  res.send(lastQRpng);
});

// ASCII (debug em terminal)
app.get('/qr.txt', async (_req, res) => {
  if (isConnected) return res.status(204).end();
  if (!lastQR) return res.status(503).send('QR indisponível no momento');
  try {
    // Regenera como string ASCII (melhor para ver em logs)
    const ascii = await QRCode.toString(lastQR, { type: 'terminal' });
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    return res.send(ascii);
  } catch (e) {
    return res.status(500).send('Falha ao gerar ASCII');
  }
});

app.post('/send', async (req, res) => {
  try {
    if (!isConnected) return res.status(503).json({ ok: false, error: 'WhatsApp não conectado' });
    const { to, text } = req.body || {};
    if (!to || !text) return res.status(400).json({ ok: false, error: 'Campos to e text são obrigatórios' });

    const jid = normalizeToJid(to);
    await sock.sendMessage(jid, { text });
    return res.json({ ok: true, to: jid });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

app.post('/schedule', async (req, res) => {
  try {
    const { to, text, send_at } = req.body || {};
    if (!to || !text || !send_at) return res.status(400).json({ ok: false, error: 'Campos to, text, send_at são obrigatórios' });

    const when = new Date(send_at);
    if (isNaN(when.getTime())) return res.status(400).json({ ok: false, error: 'send_at inválido (ISO esperado)' });

    const jid = normalizeToJid(to);
    const { rows } = await pool.query(
      `INSERT INTO wa_jobs (to_jid, message, send_at, status)
       VALUES ($1, $2, $3, 'queued') RETURNING id, send_at`,
      [jid, text, when.toISOString()]
    );
    return res.json({ ok: true, job_id: rows[0].id, send_at: rows[0].send_at });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

// Apaga credenciais e reinicia (força novo QR)
app.post('/cleanup', async (_req, res) => {
  try {
    try { await sock?.logout?.(); } catch {}
    try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch {}
    isConnected = false;
    lastQR = null;
    lastQRpng = null;
    setTimeout(startBaileys, 1000);
    return res.json({ ok: true, message: 'Sessões limpas. Reconectando…' });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

// Reinicia a conexão sem apagar credenciais (útil se ficar “travado”)
app.post('/reconnect', async (_req, res) => {
  try {
    lastQR = null;
    lastQRpng = null;
    isConnected = false;
    try { await sock?.end?.(); } catch {}
    setTimeout(startBaileys, 500);
    return res.json({ ok: true, message: 'Reconectando…' });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

// ---- Worker de jobs (envio agendado) ----
async function runSchedulerTick() {
  try {
    const { rows: jobs } = await pool.query(
      `SELECT id, to_jid, message
         FROM wa_jobs
        WHERE status = 'queued'
          AND send_at <= NOW()
        ORDER BY send_at ASC
        LIMIT 10`
    );

    for (const job of jobs) {
      const upd = await pool.query(
        `UPDATE wa_jobs SET status='processing' WHERE id=$1 AND status='queued'`,
        [job.id]
      );
      if (upd.rowCount === 0) continue;

      let ok = false, err = null;
      try {
        if (!isConnected) throw new Error('WhatsApp desconectado');
        await sock.sendMessage(job.to_jid, { text: job.message });
        ok = true;
      } catch (e) {
        err = String(e);
      }

      if (ok) {
        await pool.query(`UPDATE wa_jobs SET status='sent', sent_at=NOW(), error=NULL WHERE id=$1`, [job.id]);
      } else {
        await pool.query(`UPDATE wa_jobs SET status='failed', error=$2 WHERE id=$1`, [job.id, err]);
      }
    }
  } catch (e) {
    console.error('[SCHED] erro:', e);
  }
}

async function boot() {
  await ensureJobsTable();
  await startBaileys();
  app.listen(PORT, () => console.log(`WA server ouvindo em :${PORT}`));
  setInterval(runSchedulerTick, 2000);
}

boot().catch((e) => {
  console.error('Falha ao iniciar:', e);
  process.exit(1);
});
