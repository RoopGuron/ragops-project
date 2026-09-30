.PHONY: cluster-up creds kfp chroma mlflow cert-manager kserve port-forward secrets cluster-down

# Mirrors DEV_START.md's daily checklist as runnable targets.

cluster-up:
	cd terraform && terraform apply

creds:
	gcloud container clusters get-credentials ragops-cluster --zone us-west1-a

kfp:
	kubectl apply -k k8s/kfp-cluster-scoped
	kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
	kubectl apply -k k8s/kfp
	kubectl get pods -n kubeflow

chroma:
	kubectl apply -k k8s/chroma
	kubectl get pods -n ragops
	kubectl get pvc -n ragops

mlflow:
	kubectl apply -k k8s/mlflow
	kubectl get pods -n ragops
	kubectl get pvc -n ragops

cert-manager:
	helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager \
  --version v1.21.2 -n cert-manager --create-namespace -f k8s/cert-manager/values.yaml --wait
	kubectl get pods -n cert-manager

kserve:
	helm upgrade --install kserve-crd oci://ghcr.io/kserve/charts/kserve-crd \
	  --version v0.20.0 -n kserve --create-namespace --wait
	helm upgrade --install kserve oci://ghcr.io/kserve/charts/kserve-resources \
	  --version v0.20.0 -n kserve -f k8s/kserve/values.yaml --wait --timeout 5m
	kubectl get pods -n kserve

port-forward:
	kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80

secrets:
	kubectl create secret generic anthropic-credentials -n kubeflow \
	  --from-env-file=local/anthropic.env --dry-run=client -o yaml | kubectl apply -f -

cluster-down:
	kubectl delete ns kubeflow ragops --wait=true --ignore-not-found=true
	cd terraform && terraform destroy
