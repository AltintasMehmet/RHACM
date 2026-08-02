# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TelePortal — a telecom service portal demo for pitching Red Hat Advanced Cluster Management (RHACM). Built to show production-scale patterns to Telenet (Belgian telecom) who currently uses OpenShift Kubernetes Engine + FluxCD.

This `Telenet/` directory is the working scope; other directories in the parent `~/Desktop/Red Hat/` repo are unrelated.

## Architecture

7 Python/FastAPI microservices behind an API gateway, backed by per-service PostgreSQL databases, shared Redis, and RabbitMQ for async messaging. All services run on port 8000.

Services communicate via:
- HTTP (httpx) for synchronous calls (e.g., billing calls usage/plan/subscriber)
- RabbitMQ (aio-pika) for async events (e.g., subscriber.created → notification-service)
- Redis for real-time counters (usage-service) and network status (network-status-service)

## Running a Service Locally

```bash
cd services/<service-name>
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

All config is via environment variables with `TELEPORTAL_` prefix (see each service's `app/config.py`).

## Deploying to OpenShift

```bash
# Dev overlay (1 replica)
oc apply -k k8s/overlays/dev/

# Production overlay (3 replicas, higher limits)
oc apply -k k8s/overlays/production/

# RHACM resources (on hub cluster)
oc apply -f rhacm/cluster-sets/
oc apply -f rhacm/application/
oc apply -f rhacm/policies/
```

## Code Patterns

- Every service follows the same structure: `app/main.py` (FastAPI lifespan), `app/config.py` (pydantic-settings), `app/routes.py`, `app/models.py` + `app/schemas.py` (SQLAlchemy + Pydantic), `app/database.py`, `app/events.py` (RabbitMQ publisher)
- Health endpoints: `GET /health` (liveness), `GET /ready` (readiness with backing store checks)
- Prometheus metrics exposed at `GET /metrics` via prometheus-fastapi-instrumentator
- Tables are auto-created and seeded on startup via `app/seed.py`
- RabbitMQ and inter-service HTTP calls are resilient — errors are caught and logged, never crash the service
- Dockerfiles use multi-stage builds with non-root user compatible with OpenShift arbitrary UID

## Key Directories

- `services/` — Python microservices (api-gateway, subscriber, plan, usage, billing, notification, network-status)
- `k8s/base/` — Kustomize base manifests (namespaces, infrastructure, per-service K8s resources)
- `k8s/overlays/` — Environment-specific overlays (dev, staging, production)
- `rhacm/` — RHACM-specific CRs (application lifecycle, governance policies, cluster sets)
