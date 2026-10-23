FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY sandbox ./sandbox
RUN pip install --no-cache-dir .

EXPOSE 8000 8100
