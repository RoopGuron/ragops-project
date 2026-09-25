.PHONY: cluster-up creds kfp chroma mlflow port-forward secrets cluster-down

# Mirrors DEV_START.md's daily checklist as runnable targets.

cluster-up:
	cd terraform && terraform apply

creds:
	gcloud container clusters get-credentials ragops-cluster --region us-west1

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

port-forward:
	kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80

secrets:
	kubectl create secret generic anthropic-credentials -n kubeflow \
	  --from-env-file=local/anthropic.env --dry-run=client -o yaml | kubectl apply -f -


cluster-down:
	kubectl delete ns kubeflow ragops --wait=true --ignore-not-found=true
	cd terraform && terraform destroy
