Sorry—here it is directly in the chat.

# RHACM + FluxCD Technical Demo Runbook

Run each command block separately. When using `-w`, wait for `Compliant`, press `Ctrl+C`, and only then paste the next block.

## Prepare the environment

Return both policies to passive `inform` mode:

```bash
oc patch policy policy-teleportal-namespace \
  -n telenet-governance \
  --type=merge \
  -p '{"spec":{"remediationAction":"inform"}}'

oc patch policy policy-teleportal-capacity \
  -n telenet-governance \
  --type=merge \
  -p '{"spec":{"remediationAction":"inform"}}'

sleep 15
```

Remove the controls created during rehearsal:

```bash
oc label namespace teleportal-app \
  governance.telenet.be/managed- 2>/dev/null || true

oc delete resourcequota teleportal-capacity \
  -n teleportal-app \
  --ignore-not-found

oc delete limitrange teleportal-container-defaults \
  -n teleportal-app \
  --ignore-not-found

sleep 10
```

Verify the opening state:

```bash
oc get policy -n telenet-governance

oc get resourcequota,limitrange \
  -n teleportal-app

oc get namespace teleportal-app \
  -o jsonpath='Governance label: {.metadata.labels.governance\.telenet\.be/managed}{"\n"}'
```

Expected:

```text
policy-teleportal-capacity     inform   NonCompliant
policy-teleportal-namespace    inform   NonCompliant

No resources found in teleportal-app namespace.
Governance label:
```

## Prepare the console

Open these pages before presenting:

1. The TelePortal website.
2. OpenShift console in the **All Clusters** perspective.
3. RHACM **Search**.
4. RHACM **Governance**.
5. **Infrastructure → Clusters → local-cluster**.
6. A bastion terminal authenticated as `admin`.

# Demo procedure

## Show the Flux and application baseline

```bash
oc get gitrepository,kustomization \
  -n flux-system

oc get deployment,pods,service,route \
  -n teleportal-app

curl -ksS -o /dev/null \
  -w 'Application HTTP status: %{http_code}\n' \
  "https://$(oc get route teleportal-demo -n teleportal-app -o jsonpath='{.spec.host}')"
```

Expected:

* GitRepository: `Ready=True`
* Kustomization: `Ready=True`
* Deployment: `2/2`
* Pods: `Running`
* Website: HTTP 200

Explain:

> The GitRepository fetches the Git revision. The Flux Kustomization builds and applies the manifests. Kubernetes runs the Deployment. RHACM observes and governs these resources without replacing Flux as the application delivery controller.

## Show RHACM resource discovery

Open **All Clusters → Search** and enter:

```text
namespace:teleportal-app
```

Show the:

* Namespace
* Deployment
* ReplicaSet
* Pods
* Service
* Route
* Generated ConfigMap

Then search:

```text
kind:Deployment namespace:teleportal-app
```

Open `teleportal-demo` and show its related resources.

Explain:

> RHACM indexes the resources and their relationships. Discovery does not transfer ownership. Flux remains responsible for application reconciliation.

## Show Placement and cluster selection

```bash
oc get managedcluster local-cluster \
  --show-labels

oc get managedclustersetbinding,placement,placementdecision \
  -n telenet-governance

oc get placementdecision \
  -n telenet-governance \
  -o jsonpath='{range .items[*].status.decisions[*]}Selected cluster: {.clusterName}{"\n"}{end}'

oc get placement teleportal-placement \
  -n telenet-governance \
  -o jsonpath='Required labels: {.spec.predicates[0].requiredClusterSelector.labelSelector.matchLabels}{"\n"}'
```

Expected:

```text
Selected cluster: local-cluster
Required labels: {"demo.telenet.be/gitops":"flux"}
```

Explain:

* `ManagedClusterSetBinding` makes the global cluster set available to the policy namespace.
* `Placement` filters eligible clusters using labels.
* `PlacementDecision` contains the selected clusters.
* `PlacementBinding` connects the policies to the Placement.
* Additional OKE clusters with the same label can receive the same policies.

## Show passive compliance detection

```bash
oc get policy -n telenet-governance

oc get namespace teleportal-app \
  -o jsonpath='Governance label: {.metadata.labels.governance\.telenet\.be/managed}{"\n"}'

oc get resourcequota,limitrange \
  -n teleportal-app
```

Expected:

* Namespace policy: `inform / NonCompliant`
* Capacity policy: `inform / NonCompliant`
* Governance label: absent
* ResourceQuota: absent
* LimitRange: absent

Open **Governance → Policies** and show the violation details for both policies.

Explain:

> `inform` continuously evaluates the desired state but performs no mutation. The application is operationally healthy while still violating the platform governance baseline.

## Perform controlled namespace remediation

```bash
oc patch policy policy-teleportal-namespace \
  -n telenet-governance \
  --type=merge \
  -p '{"spec":{"remediationAction":"enforce"}}'
```

Watch the transition:

```bash
oc get policy policy-teleportal-namespace \
  -n telenet-governance \
  -w
```

When it shows `Compliant`, press `Ctrl+C`.

Verify the result:

```bash
oc get namespace teleportal-app \
  -o jsonpath='Governance label: {.metadata.labels.governance\.telenet\.be/managed}{"\n"}'
```

Expected:

```text
Governance label: true
```

Explain:

> Enforcement was enabled only after reviewing the violation. RHACM added the required namespace label and changed the policy state to compliant.

## Enforce capacity guardrails

```bash
oc patch policy policy-teleportal-capacity \
  -n telenet-governance \
  --type=merge \
  -p '{"spec":{"remediationAction":"enforce"}}'
```

Watch the transition:

```bash
oc get policy policy-teleportal-capacity \
  -n telenet-governance \
  -w
```

When it shows `Compliant`, press `Ctrl+C`.

Inspect the created objects:

```bash
oc get resourcequota,limitrange \
  -n teleportal-app

oc describe resourcequota teleportal-capacity \
  -n teleportal-app

oc describe limitrange teleportal-container-defaults \
  -n teleportal-app
```

Expected usage:

```text
Pods:             2 / 10
CPU requests:     100m / 2
Memory requests:  128Mi / 2Gi
CPU limits:       400m / 4
Memory limits:    256Mi / 4Gi
```

Explain:

> ResourceQuota controls aggregate namespace consumption. LimitRange defines container defaults and maximums. These are namespace capacity guardrails, not cluster-capacity forecasting.

## Demonstrate drift remediation

Record the current quota UID:

```bash
QUOTA_UID_BEFORE=$(oc get resourcequota teleportal-capacity \
  -n teleportal-app \
  -o jsonpath='{.metadata.uid}')

echo "Quota UID before deletion: ${QUOTA_UID_BEFORE}"
```

Delete it:

```bash
oc delete resourcequota teleportal-capacity \
  -n teleportal-app
```

Wait for RHACM to recreate it:

```bash
QUOTA_UID_AFTER=""

for ATTEMPT in {1..30}; do
  QUOTA_UID_AFTER=$(oc get resourcequota teleportal-capacity \
    -n teleportal-app \
    -o jsonpath='{.metadata.uid}' 2>/dev/null) && break

  sleep 1
done

echo "Quota UID before: ${QUOTA_UID_BEFORE}"
echo "Quota UID after:  ${QUOTA_UID_AFTER}"
```

Show the restored object:

```bash
oc get resourcequota teleportal-capacity \
  -n teleportal-app
```

The UIDs should differ.

Explain:

> The changed UID proves RHACM created a new ResourceQuota. The configuration-policy controller detected drift and restored the declared governance state.

## Prove Flux and RHACM coexistence

```bash
oc get gitrepository,kustomization \
  -n flux-system

oc get deployment,pods \
  -n teleportal-app

curl -ksS -o /dev/null \
  -w 'Application HTTP status: %{http_code}\n' \
  "https://$(oc get route teleportal-demo -n teleportal-app -o jsonpath='{.spec.host}')"
```

Show the Kubernetes field managers:

```bash
oc get namespace teleportal-app \
  -o jsonpath='{range .metadata.managedFields[*]}{.manager}{"\t"}{.operation}{"\n"}{end}' |
  sort -u
```

Expected evidence includes:

```text
config-policy-controller
kustomize-controller
```

Explain:

> Flux remains ready and continues managing the application. RHACM manages only the governance configuration declared in its policies. Flux pruning acts on resources in its own inventory and does not delete arbitrary resources created by another controller.

## Show cluster lifecycle and health

```bash
oc get managedcluster local-cluster

oc get managedclusteraddons \
  -n local-cluster

oc get clusterversion

oc get nodes \
  -o custom-columns='NAME:.metadata.name,CPU:.status.capacity.cpu,MEMORY:.status.capacity.memory,ALLOCATABLE-CPU:.status.allocatable.cpu,ALLOCATABLE-MEMORY:.status.allocatable.memory'
```

In RHACM, open **Infrastructure → Clusters → local-cluster** and show:

* Cluster availability
* OpenShift version
* Nodes and allocatable capacity
* RHACM add-on health
* Cluster labels used by Placement

Explain:

> This environment uses the hub as `local-cluster`. An imported OKE cluster uses the same ManagedCluster model. RHACM provides fleet-level health, lifecycle, add-on, Placement and governance views, while Flux remains the application delivery engine.

# Emergency checks

## Website returns HTTP 503

```bash
oc rollout status deployment/teleportal-demo \
  -n teleportal-app \
  --timeout=120s

oc get pods -n teleportal-app

curl -ksS -o /dev/null \
  -w 'Application HTTP status: %{http_code}\n' \
  "https://$(oc get route teleportal-demo -n teleportal-app -o jsonpath='{.spec.host}')"
```

## Flux is not ready

```bash
oc describe kustomization demoapp-kustomization \
  -n flux-system
```

## A policy does not change state

```bash
oc get placementdecision \
  -n telenet-governance \
  -o yaml

oc get managedclusteraddons \
  -n local-cluster

oc describe policy policy-teleportal-namespace \
  -n telenet-governance

oc describe policy policy-teleportal-capacity \
  -n telenet-governance
```

# Reset after the demonstration

```bash
oc patch policy policy-teleportal-namespace \
  -n telenet-governance \
  --type=merge \
  -p '{"spec":{"remediationAction":"inform"}}'

oc patch policy policy-teleportal-capacity \
  -n telenet-governance \
  --type=merge \
  -p '{"spec":{"remediationAction":"inform"}}'

sleep 15

oc label namespace teleportal-app \
  governance.telenet.be/managed- 2>/dev/null || true

oc delete resourcequota teleportal-capacity \
  -n teleportal-app \
  --ignore-not-found

oc delete limitrange teleportal-container-defaults \
  -n teleportal-app \
  --ignore-not-found

sleep 10

oc get policy -n telenet-governance
```

Closing statement:

> Flux delivers and reconciles the application. RHACM discovers the resulting resources, selects clusters through Placement, continuously evaluates governance, performs explicitly authorized remediation, corrects configuration drift, and provides fleet lifecycle visibility.
