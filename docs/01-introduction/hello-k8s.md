---
title: Hello Kubernetes!
parent: 01. はじめに
nav_order: 5
---

# Hello Kubernetes!
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

最初の一歩として、Kubernetes 上に nginx を動かしてブラウザからアクセスするところまでを体験します。
ここでは「とりあえず動かす」ことを優先し、出てきた概念は次章以降で詳しく扱います。

## 1. クラスタの確認

```bash
minikube status
kubectl get nodes
```

## 2. Pod を1つ立てる

```bash
kubectl run hello-nginx --image=nginx:1.27 --port=80
kubectl get pods
```

```
NAME          READY   STATUS    RESTARTS   AGE
hello-nginx   1/1     Running   0          15s
```

## 3. Pod の中を見る

```bash
kubectl logs hello-nginx
kubectl exec -it hello-nginx -- bash
# 中で
curl localhost
exit

kubectl describe pod hello-nginx
```

`describe` の `Events:` セクションは、トラブル時に最初に見る情報源です。

## 4. Service で外部から見えるようにする

Pod の IP は再起動で変わります。安定したアクセス先を提供するのが **Service** です。

```bash
kubectl expose pod hello-nginx --type=NodePort --port=80
kubectl get svc
```

Minikubeのショートカット:

```bash
minikube service hello-nginx
```

ブラウザで "Welcome to nginx!" が出ればOK。

## 5. YAMLで同じことを書く

実運用では `kubectl apply` 中心です。

```yaml
# hello.yaml
apiVersion: v1
kind: Pod
metadata:
  name: hello-nginx
  labels:
    app: hello
spec:
  containers:
  - name: nginx
    image: nginx:1.27
    ports:
    - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: hello-nginx
spec:
  type: NodePort
  selector:
    app: hello
  ports:
  - port: 80
    targetPort: 80
```

```bash
kubectl delete pod hello-nginx
kubectl delete svc hello-nginx
kubectl apply -f hello.yaml
kubectl get pod,svc
```

## 6. Deployment で本格的に

Pod を直接作るのは学習用以外では使いません。実運用では **Deployment** を使います。

```yaml
# hello-deploy.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hello
  template:
    metadata:
      labels:
        app: hello
    spec:
      containers:
      - name: nginx
        image: nginx:1.27
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: hello
spec:
  type: NodePort
  selector:
    app: hello
  ports:
  - port: 80
    targetPort: 80
```

```bash
kubectl delete -f hello.yaml --ignore-not-found
kubectl apply -f hello-deploy.yaml
kubectl get pods -l app=hello
```

3 つの Pod が動いています。**1つ消してみてください**。

```bash
POD=$(kubectl get pods -l app=hello -o jsonpath='{.items[0].metadata.name}')
kubectl delete pod $POD
kubectl get pods -l app=hello
```

すぐに新しい Pod が起動して、常に 3 つに収束するはずです。これが **「宣言した状態に収束させる」** の実例です。

## 7. ローリングアップデート

```bash
kubectl set image deployment/hello nginx=nginx:1.28
kubectl rollout status deployment/hello
kubectl rollout undo deployment/hello
```

新旧の Pod が順次入れ替わる様子は `kubectl get pods -w` で見ると分かりやすいです。
Docker だけで本番運用する場合、これらすべてを自前のシェルスクリプトで作る必要がありました。**Kubernetesの価値の片鱗** がここにあります。

## 8. お片付け

```bash
kubectl delete -f hello-deploy.yaml
```

## チェックポイント

- [ ] Pod・Service・Deployment の関係をざっくり説明できる
- [ ] 「Pod を直接作るのではなく Deployment を使う」のはなぜか説明できる
- [ ] `kubectl describe` と `kubectl logs` の使い分けが分かる

ここまでで「動かす」体験は終わりです。次章からは、登場したリソースを **きちんと理解する** フェーズに入ります。
