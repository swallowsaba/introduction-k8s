---
title: メトリクス (Prometheus + Grafana)
parent: 09. 可観測性
nav_order: 1
---

# メトリクス (Prometheus + Grafana)
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

Kubernetes 環境でのメトリクス収集の事実上の標準は **Prometheus**。
それに Grafana(可視化)、Alertmanager(通知)を組み合わせた **kube-prometheus-stack** を使います。

## kube-prometheus-stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitor prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --version 60.x.x \
  -f values-monitor.yaml
```

`values-monitor.yaml`:

```yaml
prometheus:
  prometheusSpec:
    retention: 7d
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: nfs
          accessModes: [ReadWriteOnce]
          resources:
            requests:
              storage: 20Gi
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false

grafana:
  adminPassword: changeme
  service:
    type: NodePort
    nodePort: 30030
  persistence:
    enabled: true
    storageClassName: nfs
    size: 5Gi

alertmanager:
  alertmanagerSpec:
    storage:
      volumeClaimTemplate:
        spec:
          storageClassName: nfs
          resources:
            requests:
              storage: 5Gi
```

これだけで、

- Prometheus
- Grafana(`kube-prometheus-stack` 標準ダッシュボードプリインストール)
- Alertmanager
- kube-state-metrics
- node-exporter (DaemonSet)
- prometheus-operator
- Custom Resource: `ServiceMonitor`, `PodMonitor`, `PrometheusRule`

がすべて入ります。

## アプリのメトリクス公開

サンプルアプリの API に `prometheus_client` を入れます。

```python
# api/app/main.py
from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time

app = FastAPI()

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "code"]
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency",
    ["method", "path"]
)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    path = request.url.path
    REQUESTS.labels(request.method, path, response.status_code).inc()
    LATENCY.labels(request.method, path).observe(elapsed)
    return response

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

## ServiceMonitor で Prometheus に拾わせる

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: todo-api
  labels:
    release: monitor       # kube-prometheus-stack のリリース名と合わせる
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: todo-api
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
```

`Service` の port 名(`http`)を一致させる点に注意。

## RED メソッド / USE メソッド

メトリクス設計の指針:

| | 観点 | 例 |
|---|---|---|
| **RED** (Rate, Errors, Duration) | サービス向け | リクエスト数、5xx 割合、p95 レイテンシ |
| **USE** (Utilization, Saturation, Errors) | リソース向け | CPU使用率、スレッドキュー、ENOMEM 件数 |

API は RED、ノードや DB は USE で見るのが基本。

## PromQL の頻出パターン

```promql
# RPS
sum(rate(http_requests_total[1m]))

# 5xx エラー率
sum(rate(http_requests_total{code=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))

# p95 レイテンシ
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket[5m]))
)

# Pod の CPU使用率(Requests比)
sum(rate(container_cpu_usage_seconds_total{namespace="prod"}[5m])) by (pod)
/
sum(kube_pod_container_resource_requests{namespace="prod",resource="cpu"}) by (pod)
```

## アラート (PrometheusRule)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: todo-api
  labels:
    release: monitor
spec:
  groups:
  - name: todo-api.rules
    rules:
    - alert: TodoApiHighErrorRate
      expr: |
        sum(rate(http_requests_total{code=~"5..",job="todo-api"}[5m]))
        /
        sum(rate(http_requests_total{job="todo-api"}[5m]))
        > 0.01
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "todo-api error rate > 1% for 5m"
        runbook_url: "https://wiki/runbooks/todo-api-5xx"
```

`runbook_url` を必ず付けると、夜中の onCall に優しい。

## チェックポイント

- [ ] kube-prometheus-stack でインストールされる主要コンポーネントを 4 つ
- [ ] RED と USE の使い分けを言える
- [ ] アラートの最低限の必須項目を答えられる(severity / runbook 等)
