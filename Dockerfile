FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LINKBOARD_HOST=0.0.0.0 \
    LINKBOARD_PORT=8080 \
    LINKBOARD_DB_PATH=/data/linkdashboard.db

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend

RUN mkdir -p /data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, sys, urllib.request; port=os.getenv('LINKBOARD_PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3).read()" || exit 1

CMD ["python", "/app/backend/main.py"]
