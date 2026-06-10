FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ scripts/
COPY worker/ worker/
COPY api/ api/
COPY db/ db/
COPY prompts/ prompts/

CMD ["rq", "worker", "render_queue", "upload_queue", "--url", "redis://redis:6379/0"]
