FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-reviewer.txt ./
RUN pip install --no-cache-dir -r requirements-reviewer.txt
COPY ocr_ingestion/ ./ocr_ingestion/
COPY reviewer/ ./reviewer/
COPY --from=frontend /build/frontend/dist ./frontend/dist
CMD ["python", "-m", "reviewer"]
