FROM python:3.11-slim

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

COPY server.py /app/server.py
COPY static/ /app/static/

RUN mkdir -p /tmp/docflow && chmod 777 /tmp/docflow

RUN HOME=/tmp soffice --headless --version || true

ENV SAL_USE_VCLPLUGIN=svp
ENV HOME=/tmp
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD gunicorn \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 4 \
    --timeout 200 \
    --keep-alive 5 \
    --worker-class gthread \
    --log-level info \
    server:app
    server:app
