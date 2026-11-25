# Imagen de la web (Ahí la Llevas): motor + web + sitio. Sin data/, config.yaml, plan personal ni .env (ver .dockerignore).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt requirements.txt
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r web/requirements.txt
COPY dashboard/ dashboard/
COPY plan/gen_plan.py plan/plan.example.json plan/
COPY site/ site/
COPY web/ web/
COPY scripts/ scripts/
# Cloud Run pone $PORT. Las migraciones corren al arrancar (máximo 1 instancia).
CMD ["sh", "-c", "alembic -c web/alembic.ini upgrade head && exec uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
