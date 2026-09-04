FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p output/pending output/done logs data

ENV PYTHONIOENCODING=utf-8

EXPOSE 19876

# Dashboard by default. Override the command for the CLI, e.g.
#   docker compose run --rm letterboxd-sync sync
#   docker compose run --rm letterboxd-sync export --incremental
ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["serve", "--host", "0.0.0.0"]
