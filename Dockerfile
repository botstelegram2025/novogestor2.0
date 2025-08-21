# Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_ENV=production \
    WA_API_BASE=http://127.0.0.1:3000 \
    TZ=America/Sao_Paulo

# deps do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates supervisor gnupg \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Node deps
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev

# Código
COPY bot_complete.py db.py /app/
COPY wa_server.js /app/
COPY supervisord.conf /app/supervisord.conf

# diretório de sessão do Baileys
RUN mkdir -p /app/wa_auth

CMD ["supervisord", "-c", "/app/supervisord.conf"]
