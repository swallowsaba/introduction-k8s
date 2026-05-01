# ミニ TODO サンプルアプリ

教材を通じて使うサンプルアプリのソースコードと Kubernetes マニフェスト一式です。

## アーキテクチャ

```
[Browser] -> [Ingress] -> [Frontend: Nginx] -> [API: FastAPI] -> [PostgreSQL]
                                                       |
                                                       v
                                                   [Redis]
                                                       ^
                                                       |
                                              [Worker: CronJob (notify)]
```

## ディレクトリ

| ディレクトリ | 内容 |
|---|---|
| `frontend/` | Nginx + 静的HTML(SPA) |
| `api/` | FastAPI(Python 3.12) |
| `worker/` | 通知バッチ(Python) |
| `k8s/02-basic/` | 第2章: Deployment/Service だけで動かす最小構成 |
| `k8s/03-stateful/` | 第3章: StatefulSet/CronJob/Init 導入 |
| `k8s/06-configmap-secret/` | 第6章: ConfigMap/Secret に分離 |
| `k8s/07-helm/todo-chart/` | 第7章: Helm Chart |
| `k8s/07-kustomize/` | 第7章: Kustomize (base + overlays/dev,prod) |
| `k8s/08-argocd/` | 第8章: Argo CD Application、Rollout(カナリア) |

## ローカルビルド

```bash
docker build -t todo-frontend:dev frontend/
docker build -t todo-api:dev api/
docker build -t todo-worker:dev worker/
```

## Minikube でビルド + 実行

Minikube 内 Docker で push 不要で動かせます。

```bash
eval $(minikube docker-env)
docker build -t todo-frontend:dev frontend/
docker build -t todo-api:dev api/

# ImagePolicy を Never に変える必要があるので、k8s YAML を一部書き換え or
# kubectl apply -f k8s/02-basic/all.yaml した後に kubectl set image でローカル imageを指定
```

## kubeadm クラスタ + ローカルレジストリ

```bash
# 192.168.56.10:5000 がローカル registry の場合
docker build -t 192.168.56.10:5000/todo-frontend:0.1.0 frontend/
docker push 192.168.56.10:5000/todo-frontend:0.1.0

docker build -t 192.168.56.10:5000/todo-api:0.1.0 api/
docker push 192.168.56.10:5000/todo-api:0.1.0

docker build -t 192.168.56.10:5000/todo-worker:0.1.0 worker/
docker push 192.168.56.10:5000/todo-worker:0.1.0
```

各ノードの containerd で insecure registries 設定が必要です。教材本編 1-3 を参照。

## 章ごとのデプロイ例

### 第2章

```bash
kubectl apply -f k8s/02-basic/all.yaml
kubectl get pods -n todo
kubectl port-forward -n todo svc/todo-frontend 8080:80
# ブラウザで http://localhost:8080
```

### 第7章 (Helm)

```bash
helm install todo k8s/07-helm/todo-chart \
  -n todo --create-namespace \
  --set image.tag=0.1.0
```

### 第7章 (Kustomize)

```bash
kubectl apply -k k8s/07-kustomize/overlays/dev
kubectl apply -k k8s/07-kustomize/overlays/prod
```

### 第8章 (Argo CD GitOps)

```bash
# 1. このリポジトリ(or 別リポジトリ)を Manifest Repo として用意
# 2. Argo CD インストール後、root Application を apply
kubectl apply -f k8s/08-argocd/root.yaml
```

## API 仕様

| Method | Path | 説明 |
|--------|------|------|
| GET | `/healthz` | Liveness 用ヘルスチェック |
| GET | `/readyz` | Readiness 用(DB/Redis到達確認) |
| GET | `/metrics` | Prometheus メトリクス |
| GET | `/todos` | TODO 一覧 |
| POST | `/todos` | TODO 作成 |
| PATCH | `/todos/{id}` | TODO 更新 |
| DELETE | `/todos/{id}` | TODO 削除 |

## 必要な環境変数

| 変数 | 例 | 出所 |
|------|-----|------|
| DB_HOST | postgres | ConfigMap |
| DB_PORT | 5432 | ConfigMap |
| DB_NAME | todo | ConfigMap |
| DB_USER | todo | ConfigMap |
| DB_PASSWORD | (機密) | Secret |
| REDIS_HOST | redis | ConfigMap |
| REDIS_PORT | 6379 | ConfigMap |
| LOG_LEVEL | info | ConfigMap |
