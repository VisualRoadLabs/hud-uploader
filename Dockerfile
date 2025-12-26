FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dependencias del sistema:
# - ffmpeg: para ffprobe (duración/codec)
# - libs típicas que OpenCV necesita en slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala deps Python primero para caché
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copia código y assets web
COPY app.py /app/app.py
COPY src /app/src
COPY templates /app/templates
COPY static /app/static

# Cloud Run usa PORT
ENV PORT=8080
EXPOSE 8080

# Ejecuta la web
CMD ["python", "-m", "app"]
