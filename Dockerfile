# Orionmano backend — Docker runtime for Render.
#
# Why Docker instead of Render's native Python runtime: the native runtime
# mounts the filesystem read-only, so LibreOffice can't be installed there
# (see render-build.sh). LibreOffice headless is required for
#   1. xlsx formula recalc at export time — exact parity between the dashboard
#      (Python engine) and the workbook's cached cell values, and
#   2. the values-only export for external circulation (formulas → hard values).
#
# Switching the Render service to this Dockerfile removes the
# "Skipped Excel formula recalc" warning permanently.

FROM python:3.12-slim

# System deps:
#  - libreoffice-calc: headless xlsx recalc (values-only export + parity)
#  - libpango* / fonts: WeasyPrint PDF export
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-calc \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        fonts-liberation \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# Render injects $PORT; default for local runs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
