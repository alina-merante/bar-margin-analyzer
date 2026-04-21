FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-ita \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*