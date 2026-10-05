FROM python:3.12.15-slim-bookworm AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false POETRY_NO_INTERACTION=1
WORKDIR /app
RUN python -m venv /opt/venv && pip install --no-cache-dir poetry==2.2.1
ENV VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-ansi && rm -rf /root/.cache

FROM python:3.12.15-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" TULUN_MODE=msd \
    LITELLM_LOCAL_MODEL_COST_MAP=True
WORKDIR /app
RUN groupadd --gid 10001 tulun && useradd --uid 10001 --gid tulun --no-create-home tulun
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=tulun:tulun manage.py gunicorn.conf.py ./
COPY --chown=tulun:tulun tulun ./tulun
COPY --chown=tulun:tulun translations ./translations
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).close()"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "tulun.wsgi:application"]
