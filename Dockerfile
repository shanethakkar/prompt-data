# syntax=docker/dockerfile:1
# Backend image for Render. Lean runtime: main deps only (no dev, no pandas — pandas is
# offline-only, see pyproject [dependency-groups]). The slim demo DB ships gzipped in the
# repo and is decompressed at build time. Keeps well under the 4 GB RAM ceiling at runtime.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer (cached until pyproject/uv.lock change): main group only.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# App source, then install the editable project (the `backend` package).
COPY backend ./backend
RUN uv sync --frozen --no-dev

# Trust-layer calibration map + the slim demo DB (decompressed from the committed gzip).
COPY eval/out/calibration.json ./eval/out/calibration.json
COPY data/demo.db.gz ./data/demo.db.gz
RUN python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/demo.db.gz','rb'), open('data/demo.db','wb'))" \
    && rm data/demo.db.gz

ENV DEMO_DB_PATH=data/demo.db \
    CALIBRATION_PATH=eval/out/calibration.json \
    PORT=8000
EXPOSE 8000

# Render injects $PORT. Single worker by design (in-memory rate guard; 4 GB budget).
CMD ["sh", "-c", "uv run uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
