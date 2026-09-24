# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[ui]"

# Application code (Streamlit entry point + package already installed above).
COPY app ./app

EXPOSE 8501

# Default: launch the Streamlit UI. Override the command to use the CLI, e.g.
#   docker run --rm competitor-intel competitor-intel run --url https://example.com
CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
