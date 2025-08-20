// Servidor mínimo para compatibilizar com a BaileysAPI de teste
const express = require('express');
const bodyParser = require('body-parser');
const app = express();
app.use(bodyParser.json());

app.get('/status/:sessionId', (req, res) => {
  res.json({ sessionId: req.params.sessionId, qr_needed: false, connected: true });
});

app.get('/qr/:sessionId', (req, res) => {
  res.json({ success: true, qr_code: '' });
});

app.post('/send', (req, res) => {
  const { to, message } = req.body || {};
  if (!to || !message) return res.status(400).json({ success: false, error: 'Missing to/message' });
  res.json({ success: true });
});

const port = process.env.BAILEYS_PORT || 3000;
app.listen(port, () => console.log('[baileys-server] listening on', port));
