# RAGOps

RAG pipeline over a corpus of SEC 10-K filings, built as an MLOps-flavored
project: ingestion, retrieval, cloud pipeline orchestration, and model
serving with live metrics. See `project-plan/` for the full week-by-week
plan.

## What's built so far (Week 1, Days 1–3)

**Ingestion** (`ingestion/`) — `loader.py` → `chunker.py` → `embedder.py` →
`vectorstore.py`, orchestrated by `pipeline.py`. Wrapped as a 3-task Airflow
DAG (`airflow/dags/ingest_docs_dag.py`, via `docker-compose.yaml`) with
incremental logic: doc_ids already embedded in Chroma are skipped unless the
source changed.

**RAG query path** (`rag/`) — `retriever.py` pulls top-k chunks from Chroma,
`prompt.py` builds the prompt, `generator.py` calls the LLM, `answer.py`
returns a response cited by ticker / fiscal year / item using metadata
stored per chunk at ingestion time. `query.py` is the entry point. The
retriever and the answer orchestrator can call out to in-cluster model
services instead of running locally (`EMBEDDING_ENDPOINT`,
`RERANKER_ENDPOINT` — see the Week 3 section below), falling back to the
local model when unset.

## Infrastructure (`terraform/`)

A **GKE Standard, zonal** cluster (`us-west1-a`), its VPC-native
network/subnet (with pods/services secondary ranges), the project APIs it
depends on, and a Terraform-managed GCP budget alert ($20/$50 thresholds via
`billingbudgets.googleapis.com`). The corpus GCS bucket lives in its own
Terraform root with separate state (`terraform/storage/`), so the daily
cluster teardown never touches it.

**Standard, not Autopilot.** The cluster started on GKE Autopilot and was
migrated to Standard mid-Week 3. Autopilot runs a non-preemptible
`gke-system-balloon-pod` in `kube-system` that reserves a large and
dynamically growing share of node capacity (observed growing from roughly
2 CPU/15GiB to 4 CPU/20GiB over the course of a day) — after that reservation
there wasn't enough schedulable room left for cert-manager, KServe, two
model services, and a canary split. A third Autopilot node couldn't be added
either way, since the `SSD_TOTAL_GB` regional quota (250GB on the free
trial) was already consumed by node boot disks plus KFP's PersistentVolumes.
Standard mode has no balloon pod, and its `pd-standard` boot disks don't
draw on that same SSD quota at all. The node pool is two `e2-standard-4`
nodes (8 vCPU / 32GB total, using the full E2_CPUS quota on the free trial),
with Workload Identity enabled on the cluster.

Variables (`variables.tf`): `project_id` and `billing_account_id` have no
defaults and must be supplied via `terraform.tfvars` (gitignored — never
commit real IDs); `region`, `zone` (`us-west1-a`), `vpc_name`,
`k8s_cluster_name`, and `budget_amount` all have sensible defaults.

Bring the cluster up — day-to-day this is `make cluster-up` / `make
cluster-down` (see `DEV_START.md` for the full daily checklist, including
KFP, Chroma, MLflow, KServe, and the Anthropic secret):

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

**Daily habit:** `make cluster-down` when stepping away, `make cluster-up`
when starting back up. `cluster-down` deletes every namespace that owns a
PersistentVolumeClaim (`kubeflow`, `ragops`) *before* destroying the cluster
— deleting the cluster directly doesn't go through the Kubernetes API, so
the CSI driver never gets a chance to clean up its disks, and they orphan
silently against the SSD quota otherwise.

## Week 3 — Kubeflow Pipelines, KServe model serving, and observability

Week 3 moved ingestion from Airflow to Kubeflow Pipelines (KFP) on GKE and
added KServe model serving with a live canary and Grafana dashboards. This
is what actually got built, including a few places where the real outcome
differs from the original plan.

**KFP.** Standalone (dev flavor), not the full production distribution —
lighter weight, no more than this single-user project needs. Pinned to
release `2.17.0` via a local kustomize overlay (`k8s/kfp/`), which patches
out three objects GKE Autopilot's Warden admission controller rejected (a
wildcard RBAC binding, the `proxy-agent` Deployment using `hostNetwork`, and
the cache-deployer/cache-server, which self-signs a TLS cert via a CSR
Autopilot hard-blocks) and pins every KFP image to `2.17.0` explicitly,
since the upstream overlay otherwise floats several images on `:master`
against manifests pinned to a release — a real version-skew bug that showed
up as a 404 on the API server's startup probe after a routine image re-pull.
A separate `k8s/kfp-cluster-scoped/` overlay installs the `kubeflow`
namespace and CRDs the main overlay assumes already exist.

**Ingestion as a KFP pipeline** (`pipelines/`). One container component
(`ingest`) runs the full load → chunk → embed → upsert flow inside the
cluster: `ingestion/gcs_fetch.py` pulls `corpus/clean/` from a GCS bucket
(the corpus lives on the laptop otherwise, which KFP pods can't read), then
calls the existing ingestion code unchanged. Pod access to the bucket goes
through Workload Identity: the `pipeline-runner` KSA in the `kubeflow`
namespace is granted `roles/storage.objectViewer` directly on the bucket, no
separate Google service account needed. A second component (`ragas_eval`)
runs the offline eval (`evaluation/generate.py` then `evaluation/ragas_eval.py`)
and logs to an in-cluster MLflow (`k8s/mlflow/`, sqlite-backed, StatefulSet).
Both run as one pipeline, chained with `.after()`.

**ChromaDB and MLflow.** Both run as StatefulSets in the `ragops` namespace,
both on the `standard` (HDD) storage class rather than the SSD-backed
cluster default, specifically to stay off the `SSD_TOTAL_GB` quota — a
real, measured constraint this project ran into, not a theoretical one.
Neither survives `make cluster-down`; Chroma is rebuilt by re-running the
ingest pipeline (confirmed to reproduce the exact same retrieval results —
see Reproducibility check below), and MLflow's run history is backed up
separately before any teardown that needs to keep it.

**KServe.** Installed via Helm (cert-manager `v1.21.2`, KServe `v0.20.0`) in
`Standard` deployment mode — the plan originally called this
"RawDeployment," but in this KServe release the equivalent, non-Knative mode
is actually named `Standard`; `RawDeployment` isn't a value this version
accepts. Ingress/gateway creation is disabled, since nothing here needs a
public endpoint or the Google Cloud load balancer that would otherwise get
provisioned.

**Embedding model** (`serving/embedder/`) — a custom KServe predictor
wrapping `ingestion.embedder.embed_texts`, so serving uses the exact same
model ingestion used to build the index. The RAG retriever calls it for
query-time embeddings when `EMBEDDING_ENDPOINT` is set, falling back to the
local model otherwise; ingestion itself always embeds documents in-process.

**Reranker canary** (`serving/reranker/`) — a custom KServe predictor
wrapping `sentence_transformers.CrossEncoder`, deployed twice
(`reranker` on `cross-encoder/ms-marco-MiniLM-L-6-v2`, `reranker-b` on the
larger `cross-encoder/ms-marco-MiniLM-L-12-v2`) behind a KServe
`InferenceGraph` splitting traffic 70/30. Both checkpoints are baked into
one shared image; which one a given pod loads is picked at runtime via a
`MODEL_CHECKPOINT` env var. Verified with real, differing scores for
identical input, not just two copies of the same model answering a
plumbing test. `rag/reranker.py` wires this into the query path via
`RERANKER_ENDPOINT`, inserted between retrieval and the per-doc diversity
cap, so the cap works from the reranker's more accurate ordering rather than
raw embedding distance.

**Observability.** Grafana and GKE's Managed Prometheus (GMP), not a local
Grafana instance as originally planned — Grafana runs in-cluster (Google's
own example manifest), using its native Google Cloud Monitoring data source
authenticated via Workload Identity (`roles/monitoring.viewer`), which turned
out to be simpler and have fewer moving parts than the officially documented
`datasource-syncer` CronJob path. GMP doesn't auto-discover scrape targets
the way self-hosted Prometheus can; a `PodMonitoring` resource
(`k8s/kserve/podmonitoring.yaml`) tells it to scrape all four KServe
predictors' `/metrics` endpoints. Two dashboards (Embedder, Reranker) show
request rate and p95 latency; the reranker dashboard is the more interesting
one, since it plots both checkpoints side by side and visibly shows their
different latency profiles under the live canary split. An error-rate panel
was planned but dropped — KServe's default instrumentation here only
exposes latency histograms, no HTTP-status-labeled counter, and adding one
would have meant custom instrumentation and a rebuild this late in the week.

**Not done this week.** The Kafka → KFP trigger swap (consumer submitting
runs to the KFP API instead of the Week 2 Airflow DAG) was tabled, to be
picked up after KServe and the Week 4 items, a deliberate scope cut rather
than something that didn't work out.

## Reproducibility check

The KFP pipeline (`ingest` then `ragas_eval`) was run on a freshly created
cluster with an empty Chroma index: the corpus came from GCS, was chunked,
embedded and upserted in-cluster, and the eval set was then run against it
with the Week 2 champion config (`wide+capped`: `top_k=12`, `per_doc_cap=3`).

`mean_recall` was **0.8819583333333334**, identical to the original local
champion run — and reproduced again, exactly, on a second from-scratch
cluster build after the Autopilot→Standard migration. Recall is computed
from retrieved-source metadata only, with no LLM judge, so an exact match
means the cluster retrieved the same chunks for every eval question across
two completely separate cluster builds. The corpus, chunking, embeddings,
index and retrieval config all reproduce end to end.

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
airflow/        Airflow DAG + docker-compose wrapping ingestion (Week 2 baseline)
rag/            retrieval -> rerank -> prompt -> generation -> cited answer
evaluation/     offline eval (generate + RAGAS judge), runs as a KFP component
serving/        custom KServe predictors (embedder, reranker)
pipelines/      KFP v2 SDK pipeline + component definitions
k8s/            kustomize overlays and manifests (KFP, Chroma, MLflow, KServe, Grafana)
terraform/      GKE Standard cluster + VPC + API enablement + budget alert
terraform/storage/  corpus GCS bucket + Workload Identity grants (separate state, survives teardown)
corpus/         pulled 10-K filings (gitignored)
Evaluation.md   eval question set and methodology
```
