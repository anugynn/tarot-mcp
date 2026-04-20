FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY tarot.pdf .

ENV TAROT_PDF_PATH="tarot.pdf"

EXPOSE 8000

CMD ["python", "server.py"]
