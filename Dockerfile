FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml alembic.ini ./
RUN pip install --no-cache-dir fints "sqlalchemy>=2" alembic fastapi uvicorn jinja2 python-dotenv keyring apscheduler

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/
COPY .env.example ./

ENV PYTHONUNBUFFERED=1
EXPOSE 4712

CMD ["sh", "-c", "python -m alembic upgrade head && python -m app.seed && python -m app.seed_rules && python -m uvicorn app.api:create_app --factory --host 0.0.0.0 --port 4712"]