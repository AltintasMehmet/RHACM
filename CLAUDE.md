# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TelePortal Fleet Demo — a minimal static web application for demonstrating Red Hat Advanced Cluster Management (RHACM) with FluxCD to Telenet (Belgian telecom).

The app exists solely to provide a visible, version-stamped deployment that can be changed during a live GitOps rollout demo. It is not a functional telecom portal.

## Architecture

Single static HTML page served by `registry.access.redhat.com/ubi9/httpd-24:latest`. No backend, database, or custom container image.

- Namespace: `teleportal-app`
- Deployment: `teleportal-demo` (2 replicas)
- HTML delivered via a Kustomize `configMapGenerator` (hash-suffixed)
- ClusterIP Service on port 8080
- Edge-terminated OpenShift Route

## Validating

```bash
kubectl kustomize k8s/overlays/dev
```

The rendered output should contain exactly: Namespace, ConfigMap, Deployment, Service, Route. No other resource types.

## Key Directories

- `k8s/overlays/dev/` — all Kustomize manifests and the source `index.html`

## Demo Flow (GitOps rollout)

1. Change `index.html` (e.g. bump the version from `v1.0` to `v2.0`)
2. Commit and push — FluxCD reconciles the new ConfigMap hash, triggering a Deployment rollout
3. RHACM observes the running workload and enforces governance policies separately

## Governance Design

RHACM policies, Placement, ResourceQuota, LimitRange, NetworkPolicy and Gatekeeper resources are intentionally absent from this repo. They are applied by RHACM on the hub cluster during the live demo to show separation of concerns between app delivery (Flux) and fleet governance (RHACM).

## Labels

All resources carry:
- `app.kubernetes.io/name: teleportal-demo`
- `app.kubernetes.io/instance: teleportal-demo`
- `app.kubernetes.io/part-of: telenet-rhacm-demo`
- `app.kubernetes.io/managed-by: fluxcd`
- `environment: demo`
