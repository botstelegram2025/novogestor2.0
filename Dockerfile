FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy all files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    python-telegram-bot \
    psycopg2-binary \
    apscheduler \
    pytz \
    qrcode \
    pillow \
    requests \
    python-dotenv \
    flask \
    gunicorn

# Expose port
EXPOSE 5000

# Make start.sh executable
RUN chmod +x start.sh

# Run the application using the smart start script
CMD ["./start.sh"]
