# Dockerfile (corrige npm ci sem lockfile e falta do git)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_ENV=production \
    TZ=America/Sao_Paulo

# deps do sistema (inclui git para deps do npm via git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates supervisor gnupg git \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.app.txt /app/requirements.app.txt
RUN pip install -r /app/requirements.app.txt

# Node deps (usa lockfile se existir; senão, faz npm install)
COPY package*.json /app/
RUN sh -c 'if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi'

# Código
COPY bot_complete.py db.py /app/
COPY wa_server.js /app/
COPY supervisord.conf /app/supervisord.conf

# Sessão do Baileys
RUN mkdir -p /app/wa_auth

# Healthcheck (porta dinâmica do Railway: $PORT)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-3000}/health" || exit 1'

CMD ["supervisord", "-c", "/app/supervisord.conf"]
