.PHONY: cluster-up creds kfp port-forward cluster-down

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

port-forward:
	kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80

cluster-down:
	kubectl delete ns kubeflow --wait=true --ignore-not-found=true
	cd terraform && terraform destroy
