# TelePortal — Telecom Service Portal Demo

A production-scale microservices application for demoing **Red Hat Advanced Cluster Management (RHACM)** capabilities to telecom customers. Built to highlight governance, multi-cluster placement, and compliance features that go beyond what FluxCD can provide.

## Architecture

```
                         ┌──────────────┐
            Internet ──▶ │  API Gateway │ :8000
                         └──────┬───────┘
           ┌────────┬───────┬───┴───┬──────────┬────────────────┐
           ▼        ▼       ▼       ▼          ▼                ▼
     ┌──────────┐┌──────┐┌──────┐┌───────┐┌──────────────┐┌──────────────┐
     │Subscriber││ Plan ││Usage ││Billing││ Notification ││Network Status│
     │ Service  ││ Svc  ││ Svc  ││  Svc  ││   Service    ││   Service    │
     └────┬─────┘└──┬───┘└──┬───┘└───┬───┘└──────┬───────┘└──────┬───────┘
          │         │       │        │            │               │
     ┌────▼───┐┌────▼──┐┌───▼──┐┌───▼───┐   ┌───▼────┐     ┌───▼───┐
     │ PG DB  ││ PG DB ││PG DB ││ PG DB │   │RabbitMQ│     │ Redis │
     └────────┘└───────┘└──┬───┘└───────┘   └────────┘     └───────┘
                           │
                        ┌──▼──┐
                        │Redis│
                        └─────┘
```

## Services

| Service | Stack | Database | Purpose |
|---------|-------|----------|---------|
| **api-gateway** | FastAPI | — | Routes traffic, circuit breaker, request-ID tracing |
| **subscriber-service** | FastAPI + SQLAlchemy | PostgreSQL | Customer account CRUD, event publishing |
| **plan-service** | FastAPI + SQLAlchemy | PostgreSQL | Telecom plans (data/voice/bundles) |
| **usage-service** | FastAPI + SQLAlchemy | PostgreSQL + Redis | Data/voice/SMS usage tracking, real-time counters |
| **billing-service** | FastAPI + SQLAlchemy | PostgreSQL | Invoice generation with Belgian VAT (21%) |
| **notification-service** | FastAPI + SQLAlchemy | PostgreSQL | RabbitMQ consumer, notification logging |
| **network-status-service** | FastAPI | Redis | Network health by Belgian region, outage simulation |

## Running Locally

Each service can run standalone with uvicorn:

```bash
cd services/plan-service
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Services need their backing stores (PostgreSQL, Redis, RabbitMQ) available. Set connection URLs via environment variables with the `TELEPORTAL_` prefix:

```bash
export TELEPORTAL_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/plans"
export TELEPORTAL_REDIS_URL="redis://localhost:6379/0"
export TELEPORTAL_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
```

## Deploying to OpenShift

### With Kustomize (direct)

```bash
# Dev environment (1 replica per service)
oc apply -k k8s/overlays/dev/

# Staging
oc apply -k k8s/overlays/staging/

# Production (3 replicas, higher resource limits)
oc apply -k k8s/overlays/production/
```

### With RHACM (multi-cluster)

Apply the RHACM resources on the hub cluster:

```bash
# 1. Create cluster sets for your data centers
oc apply -f rhacm/cluster-sets/

# 2. Create the application channel, placement, and subscription
oc apply -f rhacm/application/

# 3. Apply governance policies
oc apply -f rhacm/policies/

# 4. Deploy observability (ServiceMonitors)
oc apply -f rhacm/observability/
```

## RHACM Demo Walkthrough

### 1. Multi-Cluster Application Deployment
Show how `Placement` dynamically selects clusters by labels (`environment: production`, `region: belgium`) instead of FluxCD's static per-cluster configuration.

### 2. Governance Policies
Navigate to the RHACM Governance dashboard and show:
- **Resource Limits** — ensures LimitRanges exist across all clusters
- **Network Policies** — default-deny enforced in application namespaces
- **Trusted Registry** — only `quay.io/teleportal` and `registry.redhat.io` images allowed
- **Namespace Labels** — required labels enforced across clusters
- **Certificate Expiry** — 30-day warning on expiring certificates

### 3. Cluster Set Management
Demonstrate that adding a third data center is as simple as labeling the new cluster — Placements auto-select it, and all policies and applications extend automatically.

### 4. Application Topology
Use the RHACM Application view to show the full topology: API Gateway → backend services → databases, with health status across clusters.

## RHACM vs FluxCD Comparison

| Capability | FluxCD | RHACM |
|---|---|---|
| Multi-cluster targeting | Manual per-cluster Flux install | Placement with label selectors |
| Cluster grouping | None | ManagedClusterSets |
| Governance / Compliance | Not available | ConfigurationPolicy, CertificatePolicy |
| Adding a new DC | Reconfigure Flux on new cluster | Label the cluster → auto-selected |
| Compliance dashboard | Must build yourself | Built-in governance dashboard |
| Drift enforcement | HelmRelease only | Policy-driven on any K8s object |

## API Endpoints

All services expose:
- `GET /health` — liveness probe
- `GET /ready` — readiness probe (checks backing stores)
- `GET /metrics` — Prometheus metrics

Through the API Gateway (`/api/v1/{service}/...`):

| Path | Methods | Description |
|------|---------|-------------|
| `/api/v1/subscribers/subscribers` | GET, POST | List/create subscribers |
| `/api/v1/plans/plans` | GET, POST | List/create plans |
| `/api/v1/usage/usage` | GET, POST | Record/query usage |
| `/api/v1/billing/billing/invoices` | GET | List invoices |
| `/api/v1/billing/billing/generate/{id}` | POST | Generate invoice |
| `/api/v1/notifications/notifications/recent` | GET | Recent notifications |
| `/api/v1/network/network/status` | GET | Network health |
| `/api/v1/network/network/outages` | GET, POST | Manage outages |

## Production Patterns

- Multi-stage Dockerfiles with non-root user (OpenShift arbitrary UID)
- Liveness and readiness probes
- Resource requests/limits on all containers
- HPA (CPU-based autoscaling)
- PodDisruptionBudgets
- NetworkPolicies (default-deny + per-service allow rules)
- ConfigMaps + Secrets (externalized config)
- ServiceMonitors (Prometheus)
- SecurityContext (runAsNonRoot, drop ALL capabilities, readOnlyRootFilesystem)
- Per-service ServiceAccounts
- ResourceQuotas and LimitRanges per namespace
- Kustomize overlays for dev/staging/production

## Project Structure

```
Telenet/
├── services/           # 7 Python/FastAPI microservices
│   ├── api-gateway/
│   ├── subscriber-service/
│   ├── plan-service/
│   ├── usage-service/
│   ├── billing-service/
│   ├── notification-service/
│   └── network-status-service/
├── k8s/
│   ├── base/           # Kustomize base (namespaces, infra, per-service manifests)
│   └── overlays/       # dev, staging, production
├── rhacm/
│   ├── application/    # Channel, Subscription, Application, Placement
│   ├── policies/       # 5 governance policies
│   ├── cluster-sets/   # ManagedClusterSet definitions
│   └── observability/  # ServiceMonitor aggregation
└── README.md
```
