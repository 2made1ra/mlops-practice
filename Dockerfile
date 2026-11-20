FROM python:3.12.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
ENV PATH="/app/.venv/bin:${PATH}" PYTHONUNBUFFERED=1

COPY mlops_practice/ mlops_practice/
COPY configs/ configs/
ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
ENTRYPOINT ["python", "-m", "mlops_practice.train"]
