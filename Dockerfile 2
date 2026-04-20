FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY tarot_index.json .

ENV TAROT_INDEX_PATH="tarot_index.json"

EXPOSE 8000

CMD ["python", "server.py"]
