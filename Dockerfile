FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd --create-home agent && chown -R agent:agent /app
USER agent

CMD exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}