FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# TELEGRAM_BOT_TOKEN, BAILEYS_URL, LOG_LEVEL, AUTO_SEND_HOUR, DEFAULT_COUNTRY_CODE via ambiente

CMD ["python", "bot_complete.py"]
