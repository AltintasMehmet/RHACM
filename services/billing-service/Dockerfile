# ---------- Builder ----------
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY app/ app/

# ---------- Runtime ----------
FROM python:3.12-slim

LABEL maintainer="TelePortal" \
      description="TelePortal Billing Service"

# Create non-root user compatible with OpenShift arbitrary UIDs.
# Members of group 0 (root) can read/write necessary paths.
RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid 0 --no-create-home appuser \
    && mkdir -p /app \
    && chown -R 1001:0 /app \
    && chmod -R g=u /app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/app ./app

# Ensure group 0 can write (OpenShift arbitrary UID support)
RUN chmod -R g=u /app

USER 1001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
