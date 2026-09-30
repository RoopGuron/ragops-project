cert-manager version: v1.21.2

helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager \
  --version v1.21.2 -n cert-manager --create-namespace -f k8s/cert-manager/values.yaml --dry-run=server
