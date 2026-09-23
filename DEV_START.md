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

## 4. Port-forward the KFP UI

```bash
make port-forward
```

Open `http://localhost:8080`.

## End of day

```bash
make cluster-down
```

This runs `kubectl delete ns kubeflow --wait=true` before `terraform
destroy` — without it, the dynamically-provisioned PDs behind
`mysql-pv-claim`/`seaweedfs-pvc` orphan (deleting the cluster doesn't go
through the Kubernetes API, so the CSI driver never gets a chance to clean
them up) and silently eat into the `SSD_TOTAL_GB` quota until the next
`kubectl apply -k k8s/kfp` fails to schedule.

**Do NOT** run `terraform destroy` inside `terraform/storage/` — that's a
separate state holding the corpus bucket, and it must survive the daily
cluster teardown. See `terraform/storage/scribble.md`.
