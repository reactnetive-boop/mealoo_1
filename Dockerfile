# Orleeno API image
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY docker/entrypoint.sh /entrypoint.sh

# Unprivileged runtime user; uploads live on a mounted volume
RUN useradd --system --uid 10001 --home /app orleeno \
    && mkdir -p /data/uploads \
    && chown -R orleeno:orleeno /data \
    && chmod 0755 /entrypoint.sh

USER orleeno

ENV APP_ENV=production \
    UPLOAD_DIR=/data/uploads \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
