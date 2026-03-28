FROM python:3.11-slim

# Instalar dependencias en una sola capa optimizada
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-draw \
    qpdf \
    fonts-liberation \
    fonts-dejavu-core \
    fontconfig \
    curl \
    && fc-cache -f \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar solo lo necesario (no todo el repo)
COPY server.py .
COPY static/ ./static/

# Directorio de trabajo para conversiones
RUN mkdir -p /tmp/docflow && chmod 777 /tmp/docflow

# Pre-calentar LibreOffice (genera perfil en /tmp, evita lentitud en primer uso)
RUN HOME=/tmp soffice --headless --version || true

# Variables de entorno
ENV SAL_USE_VCLPLUGIN=svp
ENV HOME=/tmp
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# 1 worker + 4 threads: ideal para plan free (512MB RAM)
# gthread soporta concurrencia sin múltiples procesos pesados
CMD gunicorn \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 4 \
    --timeout 200 \
    --keep-alive 5 \
    --worker-class gthread \
    --log-level info \
    server:app
