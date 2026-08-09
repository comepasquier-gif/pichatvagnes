FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PICHAT_DATA_ROOT=/tmp/pichat-data \
    PICHAT_COOKIE_SECURE=1 \
    PICHAT_INTERNET_MODE=1 \
    PICHAT_TRUST_PROXY=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
RUN mkdir -p /tmp/pichat-data/database /tmp/pichat-data/uploads /tmp/pichat-data/backups /tmp/pichat-data/logs /tmp/pichat-data/runtime /tmp/pichat-data/deployment
EXPOSE 10000
CMD ["sh","-c","uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
