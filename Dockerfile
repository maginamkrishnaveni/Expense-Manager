# ─────────────────────────────────────────────────────────────
#  Expense Manager — Docker image for Koyeb (and any Docker host)
# ─────────────────────────────────────────────────────────────
# Koyeb auto-detects this Dockerfile and builds it. The service must
# listen on the port named by the PORT env var (default 8000); Koyeb
# sets PORT and routes HTTP traffic to it.
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# build-essential -> in case any dependency needs to compile
# libgomp1        -> onnxruntime (used by ChromaDB) needs OpenMP at runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project. (.dockerignore keeps .env, db.sqlite3, __pycache__,
# chroma_db and the projects/ planning docs OUT of the image.)
COPY . .

# Gather static files into STATIC_ROOT so WhiteNoise can serve them
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# On every container start: apply migrations, then serve via gunicorn.
# NOTE: SQLite lives on the container's ephemeral filesystem, so data
# resets on each redeploy. To persist data across redeploys, provision a
# PostgreSQL database and set DATABASE_URL (see settings.py).
CMD python manage.py migrate --noinput \
 && gunicorn expense_manager.wsgi:application \
       --bind 0.0.0.0:${PORT} \
       --workers 2 \
       --timeout 120 \
       --access-logfile - \
       --log-file -
