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
gcloud container clusters get-credentials <cluster_name> --zone <zone> --project <project_id>
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

## Week 3 design decisions

Week 3 moves ingestion from Airflow to Kubeflow Pipelines (KFP) on the GKE
Autopilot cluster and adds KServe model serving. These are the placement
decisions the rest of the week builds on.

**Trigger path.** Week 2: Aiven Kafka -> consumer -> Airflow `ingest_docs` DAG.
Week 3: Aiven Kafka -> consumer -> KFP run. Only the trigger step changes.
The consumer keeps its per-message commit + seek-retry behaviour: the offset
is committed only after the KFP run is successfully *submitted*. The two
consumers must never run at the same time (same group would split messages,
different groups would both fire).

**Consumer location.** Starts on the laptop, reading Aiven as today and
submitting runs to the KFP API through
`kubectl port-forward svc/ml-pipeline -n kubeflow 8888`. Stretch goal:
containerize it (amd64 image on GHCR, Aiven credentials in a Kubernetes
Secret) and run it as a Deployment in GKE against the in-cluster KFP service.

**ChromaDB.** Moves into GKE as a StatefulSet with a PersistentVolumeClaim.
The KFP `index` step writes to it and the RAG API reads from it. The volume is
lost on `terraform destroy`; that is acceptable because the pipeline rebuilds
the index, and it doubles as a demo of the pipeline working end to end.

**Source documents.** `corpus/` is gitignored and lives on the laptop, so KFP
pods cannot read it. The `ingest` step pulls filings from a Google Cloud
Storage (GCS) bucket in `us-west1` (same region as the cluster, to avoid
egress charges). The bucket must survive the daily `terraform destroy`, so it
lives in its own Terraform root with separate state (for example
`terraform/storage/`) rather than alongside the cluster. Pod access to the
bucket goes through Workload Identity (details to be worked out on Day 1).

**Airflow.** Retired from the Kafka path but kept in the repo as the Week 2
baseline (`airflow/`). The Compose containers (`scheduler`, `webserver`,
`postgres`) can be stopped to free Docker memory.

**Not decided yet.** Kubernetes version compatibility with KFP and KServe
(cluster runs GKE 1.35.x), how KServe canary traffic is split in RawDeployment
mode (Gateway API is already enabled on the cluster), and regional quota
increases (E2_CPUS 8, IN_USE_ADDRESSES 4 at time of writing).

**Autopilot note.** A fresh Autopilot cluster has no nodes until a workload is
deployed, so kube-system pods sit Pending after `terraform apply`. Deploy any
small workload to trigger node provisioning.

## Reproducibility check

The KFP pipeline (`ingest` then `ragas_eval`) was run on a freshly created
cluster with an empty Chroma index: the corpus came from GCS, was chunked,
embedded and upserted in-cluster, and the eval set was then run against it
with the Week 2 champion config (`wide+capped`: `top_k=12`, `per_doc_cap=3`).

`mean_recall` was **0.8819583333333334**, identical to the original local
champion run. Recall is computed from retrieved-source metadata only, with no
LLM judge, so an exact match means the cluster retrieved the same chunks for
every eval question. The corpus, chunking, embeddings, index and retrieval
config all reproduce end to end.

The LLM-judged metrics do not match exactly, as expected. Across the runs
compared, faithfulness ranged 0.78–0.82, answer_relevancy 0.55–0.61 and
context_precision 0.09–0.17, all with identical recall. That spread is judge
and generation noise on a small eval set, not a pipeline difference, and
context_precision is the noisiest. Context precision stays low while recall
is high (0.88): retrieval finds the right filings but returns many irrelevant
chunks, which is what the Week 3 reranker is meant to address. Because of the
noise, the reranker comparison should use the mean of several baseline runs
(and several reranker runs), not a single pair.

## Repo layout

```
ingestion/      load -> chunk -> embed -> upsert (Chroma)
airflow/        Airflow DAG + docker-compose wrapping ingestion
rag/            retrieval -> prompt -> generation -> cited answer
terraform/      GKE Autopilot (regional) + VPC + API enablement + budget alert
corpus/         pulled 10-K filings (gitignored)
Evaluation.md   eval question set and methodology
```
