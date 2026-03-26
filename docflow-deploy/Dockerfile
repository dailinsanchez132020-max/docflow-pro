FROM python:3.11-slim

# Instalar LibreOffice, qpdf y dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    libreoffice-draw \
    qpdf \
    fonts-liberation \
    fonts-dejavu \
    fontconfig \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear directorio temporal
RUN mkdir -p /tmp/docflow

# Variables de entorno para LibreOffice headless
ENV SAL_USE_VCLPLUGIN=svp
ENV HOME=/tmp

# Puerto
EXPOSE 8080

# Arrancar con gunicorn (producción)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 180 --worker-class sync server:app
