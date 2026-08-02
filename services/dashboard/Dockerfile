FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser -u 1001 -d /app appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
RUN chown -R 1001:0 /app && chmod -R g=u /app
USER 1001
EXPOSE 3000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
