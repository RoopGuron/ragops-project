# Dev environment — start of day

Quick checklist to bring the cluster + KFP back up. Everything here is
destroyed at end of day (see bottom), so this runs every session.

## 1. Create the cluster

```bash
cd terraform
terraform apply
```

Confirm the plan matches expectations (cluster, VPC/subnet, budget alert,
enabled APIs) before approving.

## 2. Point kubectl at it

```bash
gcloud container clusters get-credentials ragops-cluster --region us-west1
kubectl config current-context   # sanity check
```

## 3. Install KFP

```bash
kubectl apply -k k8s/kfp
kubectl get pods -n kubeflow -w
```

`k8s/kfp` is a local overlay pinned to KFP 2.17.0's `env/dev` base with three
Autopilot-incompatible objects patched out (a wildcard RBAC binding, the
`proxy-agent` Deployment, and the cache-deployer/cache-server and their
supporting RBAC + Service). See `k8s/kfp/kustomization.yaml` for why each was
removed. Expect ~14 pods; nothing cache-related should appear.

If pods sit `Pending` for more than a few minutes with no nodes showing up
(`kubectl get nodes`), Autopilot needs a real workload to trigger
provisioning — see the fallback in `terraform/scribble.md`.

## 4. Port-forward the KFP UI

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80
```

Open `http://localhost:8080`.

## End of day

```bash
cd terraform
terraform destroy
```

**Do NOT** run `terraform destroy` inside `terraform/storage/` — that's a
separate state holding the corpus bucket, and it must survive the daily
cluster teardown. See `terraform/storage/scribble.md`.
