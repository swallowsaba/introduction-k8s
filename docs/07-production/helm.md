---
title: Helm
parent: 07. 本番運用
nav_order: 6
---

# Helm
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**Helm** は Kubernetes のパッケージマネージャ。
1つのアプリに必要な複数の YAML をまとめてテンプレート化し、`values.yaml` でパラメタライズします。

## 基本概念

| | 意味 |
|---|---|
| Chart | パッケージ (テンプレート + デフォルト values) |
| Release | クラスタにインストールしたインスタンス |
| Repository | Chart の配布元 |

## Helm のインストール

```bash
brew install helm    # macOS
choco install kubernetes-helm    # Windows
```

## サードパーティ Chart の利用

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm install my-redis bitnami/redis -n cache --create-namespace \
  --set auth.password=secret123
helm list -A
helm uninstall my-redis -n cache
```

## サンプルアプリを Chart 化

```bash
helm create todo
```

生成される構造:

```
todo/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── _helpers.tpl
│   └── tests/
└── charts/
```

### values.yaml

```yaml
image:
  repository: 192.168.56.10:5000/todo-api
  tag: "0.1.0"
  pullPolicy: IfNotPresent

replicaCount: 2

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: todo.local
      paths:
        - {path: /, pathType: Prefix}

resources:
  requests: {cpu: 100m, memory: 128Mi}
  limits:   {memory: 256Mi}

postgres:
  enabled: true
  password: changeme
  storageSize: 5Gi

redis:
  enabled: true

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

### template例

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "todo.fullname" . }}
  labels: {{- include "todo.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels: {{- include "todo.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
      labels: {{- include "todo.selectorLabels" . | nindent 8 }}
    spec:
      containers:
      - name: api
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - containerPort: {{ .Values.service.targetPort }}
        resources: {{- toYaml .Values.resources | nindent 10 }}
        envFrom:
        - configMapRef:
            name: {{ include "todo.fullname" . }}
        - secretRef:
            name: {{ include "todo.fullname" . }}-secret
```

## 環境ごとの values

```bash
helm install todo ./todo -f values-prod.yaml -n prod --create-namespace
helm upgrade todo ./todo -f values-prod.yaml -n prod
helm rollback todo 1 -n prod
helm history todo -n prod
helm diff upgrade todo ./todo -f values-prod.yaml -n prod   # plugin
```

## デバッグ

```bash
helm template todo ./todo -f values-prod.yaml          # YAML 出力 (適用しない)
helm install todo ./todo --dry-run --debug -f values-prod.yaml
helm lint ./todo
```

## Subchart とDependency

サブモジュール的に他の Chart を取り込めます。

```yaml
# Chart.yaml
dependencies:
- name: postgresql
  version: 15.x.x
  repository: https://charts.bitnami.com/bitnami
  condition: postgres.enabled
- name: redis
  version: 19.x.x
  repository: https://charts.bitnami.com/bitnami
  condition: redis.enabled
```

```bash
helm dependency update
helm dependency build
```

これでサンプルアプリの Chart 1 つで「API + Frontend + Postgres + Redis」を一括デプロイできます。

## Helm vs Kustomize

両方使えますが、思想が違います。

| | Helm | Kustomize |
|---|---|---|
| アプローチ | テンプレート + values | base + overlay (パッチ) |
| 学習コスト | テンプレート言語が独特 | YAML のみ |
| 配布 | repository あり | なし |
| サードパーティ | 圧倒的 | 比較的少ない |
| 環境差 | values で | overlays で |

**サードパーティアプリは Helm、自社アプリは Kustomize、または両者の併用** がよくあるパターン。

## チェックポイント

- [ ] Chart 化のメリットを 3 つ以上挙げられる
- [ ] 既存 Helm Chart に依存を追加できる
- [ ] `helm diff` を使った安全なアップグレードフロー
