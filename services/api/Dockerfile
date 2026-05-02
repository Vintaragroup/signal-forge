FROM python:3.11-slim

WORKDIR /app

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api/main.py .
COPY services/api/transcript_provider.py .
COPY services/api/audio_extractor.py .
COPY services/api/media_intake.py .
COPY services/api/prompt_generator.py .
COPY services/api/video_assembler.py .
COPY agents ./agents
COPY tools ./tools
COPY modules ./modules
COPY core ./core
COPY scripts ./scripts
COPY tests ./tests
COPY docker-compose.yml ./docker-compose.yml

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
