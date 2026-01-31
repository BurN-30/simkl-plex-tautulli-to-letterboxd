FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p output logs data

EXPOSE 19876

# Default to web server, can be overridden for CLI
ENTRYPOINT ["python", "src/server.py"]
