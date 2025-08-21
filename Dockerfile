# Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_ENV=production \
    TZ=America/Sao_Paulo

# deps do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates supervisor gnupg \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 LTS (para o servidor Baileys)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (usa ARQUIVO NOVO para quebrar cache e evitar reqs antigos)
COPY requirements.app.txt /app/requirements.app.txt
RUN pip install -r /app/requirements.app.txt

# Node deps
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev

# Código
COPY bot_complete.py db.py /app/
COPY wa_server.js /app/
COPY supervisord.conf /app/supervisord.conf

# Sessão do Baileys
RUN mkdir -p /app/wa_auth

# Healthcheck (usa porta dinâmica do Railway: $PORT)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-3000}/health" || exit 1'

CMD ["supervisord", "-c", "/app/supervisord.conf"]
