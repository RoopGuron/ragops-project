# RAGOps

RAG pipeline over a corpus of SEC 10-K filings, built as an MLOps-flavored
project: local ingestion + retrieval today, real cloud infra and pipeline
orchestration on the way. See `project-plan/` for the full week-by-week plan.

## What's built so far (Week 1, Days 1–3)

**Ingestion** (`ingestion/`) — `loader.py` → `chunker.py` → `embedder.py` →
`vectorstore.py`, orchestrated by `pipeline.py`. Wrapped as a 3-task Airflow
DAG (`airflow/dags/ingest_docs_dag.py`, via `docker-compose.yaml`) with
incremental logic: doc_ids already embedded in Chroma are skipped unless the
source changed.

**RAG query path** (`rag/`) — `retriever.py` pulls top-k chunks from Chroma,
`prompt.py` builds the prompt, `generator.py` calls the LLM, `answer.py`
returns a response cited by ticker / fiscal year / item using metadata
stored per chunk at ingestion time. `query.py` is the entry point.

**Infrastructure** (`terraform/`) — GKE Autopilot cluster, its VPC-native
network/subnet (with pods/services secondary ranges), the project APIs it
depends on, and a Terraform-managed GCP budget alert ($20/$50 thresholds via
`billingbudgets.googleapis.com`). Note: GCP now requires Autopilot clusters
to be **regional** — zonal Autopilot has been deprecated — but the $74.40/mo
management-fee credit still fully offsets the flat per-cluster fee either
way, so the cost story from the project plan holds.

Variables (`variables.tf`): `project_id` and `billing_account_id` have no
defaults and must be supplied via `terraform.tfvars` (gitignored — never
commit real IDs); `region` (`us-west1`), `zone`, `vpc_name`, `k8s_cluster_name`,
and `budget_amount` all have sensible defaults.

Bring the cluster up:

```bash
cd terraform
# terraform.tfvars (gitignored): project_id, billing_account_id
terraform init
terraform apply
gcloud container clusters get-credentials <cluster_name> --region <region> --project <project_id>
kubectl get nodes   # confirm kubectl is talking to the cluster
```

Two GCP-side gotchas hit during setup, in case they recur: (1) ADC user
credentials don't reliably pick up a quota project for billing-related APIs
— fixed via `user_project_override = true` + `billing_project` on the
`google` provider block rather than relying on `gcloud auth
application-default set-quota-project`; (2) a brand-new project needs
`cloudresourcemanager.googleapis.com` enabled before Terraform can manage
*any* other API via `google_project_service` — a one-time manual
`gcloud services enable`, since Terraform can't bootstrap its own way past
that chicken-and-egg dependency.

**Daily habit going forward:** `terraform destroy` when stepping away,
`terraform apply` when starting back up — Autopilot bills per-pod-second, so
this is what keeps a "always on" ~$150+/mo bill down to genuine active-use
compute. See `project-plan/` for the full cost reasoning.

## Repo layout

```
ingestion/      load -> chunk -> embed -> upsert (Chroma)
airflow/        Airflow DAG + docker-compose wrapping ingestion
rag/            retrieval -> prompt -> generation -> cited answer
terraform/      GKE Autopilot (regional) + VPC + API enablement + budget alert
corpus/         pulled 10-K filings (gitignored)
Evaluation.md   eval question set and methodology
```
