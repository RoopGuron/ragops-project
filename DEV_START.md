# Dev environment — start of day

Quick checklist to bring the cluster + KFP back up. Everything here is
destroyed at end of day (see bottom), so this runs every session. Steps below
are backed by `Makefile` targets — run `make <target>` for each.

## 1. Create the cluster

```bash
make cluster-up
```

Review the plan — cluster, VPC/subnet, budget alert, enabled APIs — before
approving.

## 2. Point kubectl at it

```bash
make creds
kubectl config current-context   # sanity check
```

## 3. Install KFP

```bash
make kfp
kubectl get pods -n kubeflow -w
```

`make kfp` runs two kustomize overlays in order:

1. `k8s/kfp-cluster-scoped` — creates the `kubeflow` namespace and the CRDs
   (the `Application` CRD, KFP's own scheduled-workflow/viewer CRDs, Argo
   Workflows' CRDs) that step 2 assumes already exist, then waits for the
   `Application` CRD to become `Established` before continuing. This is a
   fresh cluster every day, so it must run first every time — see
   `k8s/kfp-cluster-scoped/kustomization.yaml` for the two errors you get if
   you skip it (or run it before the wait completes).
2. `k8s/kfp` — KFP 2.17.0's `env/dev` base with three Autopilot-incompatible
   objects patched out (a wildcard RBAC binding, the `proxy-agent`
   Deployment, and the cache-deployer/cache-server and their supporting RBAC
   + Service). See `k8s/kfp/kustomization.yaml` for why each was removed.
   Expect ~14 pods; nothing cache-related should appear.

If pods sit `Pending` for more than a few minutes with no nodes showing up
(`kubectl get nodes`), Autopilot needs a real workload to trigger
provisioning — see the fallback in `terraform/scribble.md`. If `mysql-pv-claim`
or `seaweedfs-pvc` stay `Pending`, check for a `QUOTA_EXCEEDED` on
`SSD_TOTAL_GB` in `kubectl get events -n kubeflow` — the free-trial region
quota is 250GB and disks from a cluster torn down without `make cluster-down`
can orphan and eat into it (`gcloud compute disks list` to check for
unattached `pvc-*` disks).

## 4. Deploy Chroma

```bash
make chroma
```

Applies `k8s/chroma` (StatefulSet + PVC + Service in the `ragops` namespace)
and prints the pod and PVC status. The pod should reach `Running` and the PVC
`Bound`. The store starts empty every day — repopulate it by re-running the
ingest pipeline.

## 5. Deploy MLflow

```bash
make mlflow
```

Applies `k8s/mlflow` (StatefulSet + headless Service + PVC in the `ragops`
namespace). **Run this after `make chroma`:** the `ragops` namespace is
created by `k8s/chroma`, and `k8s/mlflow` does not create it, so on a fresh
cluster running MLflow first fails with `namespaces "ragops" not found`.

In-cluster pipeline steps reach it at
`http://mlflow.ragops.svc.cluster.local:5000`. To open its UI from your
laptop, see step 7.

## 6. Create the Anthropic Secret

```bash
make secrets
```

Creates the `anthropic-credentials` Secret in the `kubeflow` namespace from
`local/anthropic.env`, which the eval pipeline step reads through
`use_secret_as_env`. Run it after `make kfp` (it needs the `kubeflow`
namespace) and before starting a pipeline run — without it the eval step pod
never starts. It is safe to re-run. The Secret is destroyed with the cluster,
so this is a daily step.

One-time setup: `local/anthropic.env` (gitignored, `chmod 600`) holds exactly
two lines, `ANTHROPIC_API_KEY=...` and `ANTHROPIC_WORKSPACE_ID=...`. Never put
these in `k8s/` or in the image — the ghcr package is public.

## 7. Port-forward the UIs

Each port-forward holds its terminal open, so run them in separate
terminals. They also drop if the laptop sleeps — just re-run them.

| UI | Command | URL |
|---|---|---|
| Kubeflow Pipelines | `make port-forward` | `http://localhost:8080` |
| MLflow | `kubectl port-forward -n ragops svc/mlflow 5001:5000` | `http://localhost:5001` |

MLflow uses local port 5001 because macOS reserves 5000 for AirPlay.

## End of day

```bash
make cluster-down
```

This deletes **every namespace that owns a PVC** (`kubeflow` and `ragops`),
waiting for each to finish, and only then runs `terraform destroy`. The order
matters: deleting the cluster doesn't go through the Kubernetes API, so the
CSI driver never gets a chance to delete the dynamically-provisioned PDs
behind `mysql-pv-claim`/`seaweedfs-pvc` (KFP) and Chroma's PVC. Orphaned
disks silently eat into the `SSD_TOTAL_GB` quota (250GB on the free trial)
until a later `kubectl apply` fails to schedule. Any new namespace that gets
a PVC (e.g. KServe model storage later) must be added to this list.

Chroma's data does not survive this — every storage class on the cluster has
`reclaimPolicy: Delete`, so the PVC and disk are destroyed with the
namespace. That's intended: the corpus lives in the GCS bucket, and Chroma is
repopulated by re-running the ingest pipeline each morning.

After it finishes, confirm nothing leaked:

```bash
gcloud compute disks list --format="table(name,sizeGb,type,users)"
```

The list should be empty. Any `pvc-*` disk with no `users` is an orphan —
delete it with `gcloud compute disks delete <name> --zone=<zone>`.

**Do NOT** run `terraform destroy` inside `terraform/storage/` — that's a
separate state holding the corpus bucket, and it must survive the daily
cluster teardown. See `terraform/storage/scribble.md`.
