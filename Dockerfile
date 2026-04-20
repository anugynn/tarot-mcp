FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY "The Ultimate Guide to Tarot - A Beginner.pdf" .

ENV TAROT_PDF_PATH="The Ultimate Guide to Tarot - A Beginner.pdf"

EXPOSE 8000

CMD ["python", "server.py"]
