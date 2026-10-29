# Bizon Platform Helm Chart

A Helm chart for deploying Bizon Platform on Kubernetes.

## Quick Start

```bash
# Install with defaults (includes bundled PostgreSQL)
helm install bizon oci://ghcr.io/bizon-data/charts/bizon-platform

# Access the UI
kubectl port-forward svc/bizon-bizon-platform-ui 3000:8080
open http://localhost:3000
```

## Installation

### From GHCR (Recommended)

```bash
# Install with default settings (includes bundled PostgreSQL)
helm install bizon oci://ghcr.io/bizon-data/charts/bizon-platform

# Install with custom values
helm install bizon oci://ghcr.io/bizon-data/charts/bizon-platform \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=bizon.example.com

# Upgrade
helm upgrade bizon oci://ghcr.io/bizon-data/charts/bizon-platform

# Pull chart locally
helm pull oci://ghcr.io/bizon-data/charts/bizon-platform --version 0.1.0 --untar
```

### From Source

```bash
helm install bizon ./helm/bizon-platform
```

## Architecture

Startup sequence (dependencies handled automatically by Kubernetes):

```
PostgreSQL (StatefulSet)
    └─► API migrate init container (alembic upgrade head)
            └─► API (FastAPI)
    └─► Worker (polls DB with built-in retry)

UI (nginx, no dependencies)
```

## Local Testing with Minikube

```bash
# Start minikube
minikube start

# Build images locally
docker build --target backend -t bizon-platform:local .
docker build --target ui -t bizon-platform-ui:local .

# Load images into minikube
docker save bizon-platform:local | minikube image load --daemon=false -
docker save bizon-platform-ui:local | minikube image load --daemon=false -

# Install with local images
helm install bizon ./helm/bizon-platform \
  --set api.image.repository=bizon-platform \
  --set api.image.tag=local \
  --set api.image.pullPolicy=Never \
  --set worker.image.repository=bizon-platform \
  --set worker.image.tag=local \
  --set worker.image.pullPolicy=Never \
  --set ui.image.repository=bizon-platform-ui \
  --set ui.image.tag=local \
  --set ui.image.pullPolicy=Never

# Wait for pods
kubectl get pods -l "app.kubernetes.io/instance=bizon" -w

# Port forward UI
kubectl port-forward svc/bizon-bizon-platform-ui 3000:8080
```

## Configuration

### Quick Start Values

```yaml
# values-quickstart.yaml
ingress:
  enabled: true
  hosts:
    - host: bizon.example.com
      paths:
        - path: /
          pathType: Prefix

security:
  encryptionKey: "your-fernet-key-here"  # Generate with: make key
```

### External Database

```yaml
# values-external-db.yaml
postgresql:
  enabled: false

externalDatabase:
  host: "postgres.example.com"
  port: 5432
  database: "bizon"
  username: "bizon"
  password: "secret"
  sslMode: require
```

### Production Values

See `values-production.yaml` for production-ready settings including:
- Resource limits
- Horizontal Pod Autoscaler
- Ingress with TLS
- External database

## Parameters

### Global

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.imagePullSecrets` | Image pull secrets for private registries | `[]` |

### PostgreSQL (Bundled)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgresql.enabled` | Deploy bundled PostgreSQL | `true` |
| `postgresql.image.repository` | PostgreSQL image | `cgr.dev/chainguard/postgres` |
| `postgresql.auth.database` | Database name | `bizon_platform` |
| `postgresql.auth.username` | Database username | `bizon` |
| `postgresql.auth.password` | Database password (auto-generated if empty) | `""` |
| `postgresql.storage.size` | PVC size | `10Gi` |

### External Database

| Parameter | Description | Default |
|-----------|-------------|---------|
| `externalDatabase.host` | External database host | `""` |
| `externalDatabase.port` | External database port | `5432` |
| `externalDatabase.database` | Database name | `bizon_platform` |
| `externalDatabase.username` | Database username | `bizon` |
| `externalDatabase.password` | Database password | `""` |
| `externalDatabase.sslMode` | SSL mode | `prefer` |

### API Server

| Parameter | Description | Default |
|-----------|-------------|---------|
| `api.image.repository` | API image | `ghcr.io/bizon-data/bizon-platform` |
| `api.image.tag` | API image tag | `latest` |
| `api.replicaCount` | Number of replicas | `1` |
| `api.resources.requests.memory` | Memory request | `256Mi` |
| `api.resources.limits.memory` | Memory limit | `1Gi` |
| `api.service.port` | Service port | `8000` |

### Worker

| Parameter | Description | Default |
|-----------|-------------|---------|
| `worker.image.repository` | Worker image | `ghcr.io/bizon-data/bizon-platform` |
| `worker.image.tag` | Worker image tag | `latest` |
| `worker.replicaCount` | Number of replicas | `1` |
| `worker.resources.requests.memory` | Memory request | `512Mi` |
| `worker.resources.limits.memory` | Memory limit | `2Gi` |
| `worker.autoscaling.enabled` | Enable HPA | `false` |

### UI

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ui.image.repository` | UI image | `ghcr.io/bizon-data/bizon-platform-ui` |
| `ui.image.tag` | UI image tag | `latest` |
| `ui.replicaCount` | Number of replicas | `1` |
| `ui.service.port` | Service port | `8080` |

### Security

| Parameter | Description | Default |
|-----------|-------------|---------|
| `security.encryptionKey` | Fernet encryption key | `""` |
| `security.existingEncryptionKeySecret` | Use existing secret | `""` |
| `security.adminPassword` | Admin password (optional) | `""` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class | `""` |
| `ingress.hosts[0].host` | Hostname | `bizon.local` |
| `ingress.tls` | TLS configuration | `[]` |

### Storage

| Parameter | Description | Default |
|-----------|-------------|---------|
| `storage.outputs.size` | Outputs PVC size | `10Gi` |
| `storage.customSources.size` | Custom sources PVC size | `1Gi` |

## Images

The chart uses these images published to GHCR:

| Image | Description |
|-------|-------------|
| `ghcr.io/bizon-data/bizon-platform` | API + Worker (Python backend) |
| `ghcr.io/bizon-data/bizon-platform-ui` | UI (nginx serving React) |

Images are tagged with:
- `latest` - Latest build from main branch
- `sha-<commit>` - Specific commit (immutable)

## CI/CD

Images and chart are automatically published on merge to `main` via GitHub Actions.

See `.github/workflows/release.yml` for details.
