# === Base com Python 3.12 enxuto ===
FROM python:3.12-slim

# === Configs de runtime e fuso horário (útil p/ zoneinfo) ===
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

# tzdata para fuso horário; ping básico para diagnósticos opcionais
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# === Diretório da app ===
WORKDIR /app

# === Instala dependências primeiro (cache eficiente) ===
# Garanta que o arquivo se chama exatamente "requirements.txt"
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# === Copia o restante do código ===
COPY . /app

# === Usuário não-root por segurança ===
RUN useradd -m appuser
USER appuser

# === Entry configurável: por padrão, rodamos main.py ===
# Se seu entrypoint for outro arquivo (ex: bot_complete.py), 
# altere o APP_ENTRY no deploy ou mude para o nome correto aqui.
ENV APP_ENTRY=main.py
CMD ["sh", "-c", "python3 $APP_ENTRY"]
