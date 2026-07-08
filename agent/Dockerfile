FROM python:3.12-slim

# MPLBACKEND=Agg: matplotlib renders charts headless (no display needed).
# util-linux (for `unshare -n`, the sandbox network jail) ships in the base image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-build matplotlib's font cache in the sandbox's config dir (/tmp) so the
# first chart render at runtime is fast and never trips the sandbox CPU cap.
RUN MPLCONFIGDIR=/tmp MPLBACKEND=Agg python -c "import matplotlib.pyplot"

COPY . .

EXPOSE 8000
# Respect $PORT when the host injects it (Render sets it); default 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
