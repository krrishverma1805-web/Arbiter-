# arbiter (Helm chart)

Deploys the three Arbiter workloads to Kubernetes:

| Workload | Kind | Notes |
|---|---|---|
| `api` | Deployment + Service (+ HPA, PDB) | FastAPI `/v1/*`; `/healthz` liveness, `/readyz` readiness |
| `worker` | Deployment (+ HPA) | `arbiter-api worker` — drains the DB job queue; `terminationGracePeriodSeconds: 120` so an in-flight run finishes or is re-claimed |
| `web` | Deployment + Service (+ optional HPA) | Next.js standalone cockpit |

Schema migrations run as a **`pre-install,pre-upgrade` hook Job** (`arbiter-api db upgrade`) so the database is at `head` before any pod that reads it rolls.

## Prerequisites

- A Postgres reachable at `secret.data.ARBITER_DB_URL` (this chart does **not** run Postgres — use a managed instance or the `bitnami/postgresql` chart, ideally behind pgbouncer).
- Images pushed to `{{ image.registry }}/{{ image.repository }}-api` and `-web`.

## Install

```bash
helm install arbiter deploy/helm/arbiter \
  --set image.apiTag=$GIT_SHA --set image.webTag=$GIT_SHA \
  --set-string secret.data.ARBITER_DB_URL='postgresql+psycopg://…' \
  --set-string secret.data.ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  --set ingress.enabled=true --set ingress.host=arbiter.example.com
```

For production, manage secrets out-of-band and point at them:

```bash
--set secret.existingSecret=arbiter-prod-secrets
```

## Key values

See [`values.yaml`](values.yaml). Most-changed: `image.*Tag`, `secret.*`,
`ingress.*`, `api.autoscaling.*`, `worker.autoscaling.*`, `persistence.*`
(disable and swap `storage.py` for S3/R2 in real clusters without RWX).

CI renders this chart with [`ci/lint-values.yaml`](ci/lint-values.yaml) and
validates every manifest against the Kubernetes 1.28 schema with `kubeconform`.
