---
title: ConfigMap
parent: 06. 設定とSecret
nav_order: 1
---

# ConfigMap
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**ConfigMap** は機密でない設定値を Pod に注入するためのリソース。

## 作成

```bash
# ファイルから
kubectl create configmap app-config --from-file=app.properties

# 値から
kubectl create configmap app-config --from-literal=LOG_LEVEL=info --from-literal=PORT=8080
```

YAML:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: todo-config
data:
  LOG_LEVEL: info
  PORT: "8000"
  app.conf: |
    [server]
    host = 0.0.0.0
    workers = 4
```

## Pod への注入方法

### 1. 環境変数 (個別)

```yaml
spec:
  containers:
  - name: app
    image: myapp:1.0
    env:
    - name: LOG_LEVEL
      valueFrom:
        configMapKeyRef:
          name: todo-config
          key: LOG_LEVEL
```

### 2. 環境変数 (一括)

```yaml
spec:
  containers:
  - name: app
    envFrom:
    - configMapRef:
        name: todo-config
```

ConfigMap のすべてのキーが環境変数として注入される。

### 3. ファイルとしてマウント

```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: config
      mountPath: /etc/app
      readOnly: true
  volumes:
  - name: config
    configMap:
      name: todo-config
      items:
      - key: app.conf
        path: app.conf
```

`/etc/app/app.conf` として参照可能。

## 注意点

### 1. 環境変数として注入したものはホットリロードされない

ConfigMap を更新しても、**環境変数は Pod 再起動まで反映されない**。
ホットリロード可能にしたいなら、ファイルマウントしてアプリ側で監視する。

### 2. 容量制限 1MiB

大きなファイルは Volume にすべき。

### 3. immutable ConfigMap

```yaml
immutable: true
```

変更できなくする代わりに、kube-apiserver の負荷を下げる。

## ハンズオン

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: todo-config
data:
  LOG_LEVEL: info
  DB_HOST: postgres
  DB_PORT: "5432"
  DB_NAME: todo
  REDIS_HOST: redis
  REDIS_PORT: "6379"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: todo-api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: todo-api
    spec:
      containers:
      - name: api
        image: 192.168.56.10:5000/todo-api:0.1.0
        envFrom:
        - configMapRef:
            name: todo-config
        - secretRef:           # 機密はSecretへ (次節)
            name: todo-secret
```

## チェックポイント

- [ ] envFrom と env の使い分け
- [ ] ConfigMap 更新時にホットリロードしたい場合の注入方法
- [ ] immutable ConfigMap の利点
