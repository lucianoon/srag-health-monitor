FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    PYTHONPATH=/app/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

# curl fica para o healthcheck do compose. As dependências Python têm wheels
# para 3.11, então build-essential deixou de ser necessário.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Camada de dependências: só invalida quando o lockfile muda. As versões são
# exatamente as que o CI testou (`uv sync --locked`).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .

RUN mkdir -p /app/data /app/outputs/reports /app/outputs/logs

EXPOSE 8000

# Para `docker run` avulso; o compose declara o mesmo probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
