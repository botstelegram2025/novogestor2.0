// wa_server.js
const express = require('express');
const cors = require('cors');
const fs = require('fs');
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

if (!DATABASE_URL) {
  console.error('DATABASE_URL não definido');
  process.exit(1);
}

const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

let sock = null;
let lastQR = null;
let isConnected = false;
let meJid = null;

function normalizeToJid(to) {
  if (!to) return null;
  let p = String(to).replace(/\D/g, '');
  if (p.startsWith('0')) p = p.replace(/^0+/, '');
  if (!p.startsWith('55')) p = '55' + p;
  return `${p}@s.whatsapp.net`;
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

async function startBaileys() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();
  const logger = pino({ level: 'fatal' });

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      try {
        lastQR = await QRCode.toDataURL(qr);
      } catch (e) {
        console.error('Falha ao gerar QR:', e);
        lastQR = null;
      }
      isConnected = false;
    }

    if (connection === 'open') {
      isConnected = true;
      lastQR = null;
      meJid = sock.user?.id || null;
      console.log('[WA] Conectado como', meJid);
    } else if (connection === 'close') {
      isConnected = false;
      const reason = lastDisconnect?.error?.output?.statusCode || lastDisconnect?.error?.message;
      console.log('[WA] Conexão fechada:', reason);
      if (lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut) {
        setTimeout(startBaileys, 3000);
      }
    }
  });
}

/** API */
app.get('/', (_req, res) => res.redirect('/health'));

app.get('/health', async (_req, res) => {
  try {
    const { rows } = await pool.query(`SELECT COUNT(*)::int AS count FROM wa_jobs WHERE status='queued';`);
    return res.json({ connected: isConnected, me: meJid, queued: rows?.[0]?.count || 0 });
  } catch (e) {
    return res.status(500).json({ error: String(e) });
  }
});

app.get('/qr', (_req, res) => {
  if (isConnected) return res.json({ connected: true, qr: null });
  if (!lastQR) return res.status(503).json({ connected: false, qr: null, error: 'QR indisponível no momento' });
  return res.json({ connected: false, qr: lastQR });
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

app.post('/cleanup', async (_req, res) => {
  try {
    try { await sock?.logout?.(); } catch {}
    try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch {}
    isConnected = false;
    lastQR = null;
    setTimeout(startBaileys, 1000);
    return res.json({ ok: true, message: 'Sessões limpas. Reconectando…' });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

/** Worker de jobs */
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
