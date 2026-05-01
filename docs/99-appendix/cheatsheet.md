---
title: kubectl チートシート
parent: 99. 付録
nav_order: 1
---

# kubectl チートシート
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## コンテキスト・Namespace

```bash
kubectl config current-context
kubectl config use-context <ctx>
kubectl config set-context --current --namespace=prod
kubectl config get-contexts
```

## get / list

```bash
kubectl get pods
kubectl get pods -A                          # 全Namespace
kubectl get pods -o wide                     # IPやノード表示
kubectl get pods -l app=web                  # ラベル
kubectl get pods --field-selector=status.phase=Running
kubectl get pods --watch
kubectl get pods --sort-by=.status.startTime
kubectl get pods -o jsonpath='{.items[*].metadata.name}'
kubectl get pods -o custom-columns=NAME:.metadata.name,IP:.status.podIP
```

## describe / logs / exec

```bash
kubectl describe pod <pod>
kubectl describe node <node>
kubectl logs <pod>
kubectl logs <pod> -c <container>
kubectl logs <pod> --previous
kubectl logs -l app=web --tail=100 -f
kubectl logs -l app=web --max-log-requests=10 --tail=10
kubectl exec -it <pod> -- bash
kubectl exec -it <pod> -c <container> -- sh
kubectl cp <pod>:/etc/conf ./conf -c <container>
```

## apply / edit / delete

```bash
kubectl apply -f .
kubectl apply -k overlays/prod
kubectl diff -f .
kubectl delete -f deploy.yaml
kubectl delete pod <pod> --grace-period=0 --force
kubectl edit deploy/web
kubectl scale deploy/web --replicas=5
kubectl rollout status deploy/web
kubectl rollout undo deploy/web
kubectl rollout restart deploy/web
kubectl rollout history deploy/web
```

## ラベル・アノテーション

```bash
kubectl label pod <pod> env=dev
kubectl label pod <pod> env-                 # 削除
kubectl annotate pod <pod> note='handle with care'
```

## ポート転送・プロキシ

```bash
kubectl port-forward svc/web 8080:80
kubectl port-forward pod/web-xxx 8080:80
kubectl proxy --port=8001
```

## デバッグ

```bash
# 一時 Pod (netshoot)
kubectl run debug --rm -it --image=nicolaka/netshoot --restart=Never -- bash

# 既存Podにエフェメラルコンテナ
kubectl debug -it <pod> --image=nicolaka/netshoot --target=<container>

# ノード上で実行
kubectl debug node/<node> -it --image=ubuntu
```

## トラブル時の高速確認

```bash
kubectl get events -A --sort-by=.metadata.creationTimestamp | tail -30
kubectl get pods -A --field-selector=status.phase!=Running
kubectl top pod -A --sort-by=cpu
kubectl top node
kubectl get pdb -A
kubectl get pvc -A
```

## YAML 生成

```bash
kubectl create deploy web --image=nginx:1.27 --replicas=3 --dry-run=client -o yaml
kubectl create svc clusterip web --tcp=80:8080 --dry-run=client -o yaml
kubectl create configmap app-config --from-literal=K=V --dry-run=client -o yaml
kubectl create secret generic app-secret --from-literal=PW=x --dry-run=client -o yaml
```

## 認可確認

```bash
kubectl auth can-i list pods --as alice@example.com -n prod
kubectl auth can-i '*' '*' --as system:serviceaccount:prod:todo-api
```

## よく使う JSONPath / 加工

```bash
# Pod 名一覧
kubectl get pods -o jsonpath='{.items[*].metadata.name}'

# 各 Pod のノード
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}'

# 起動時刻
kubectl get pods -o custom-columns=NAME:.metadata.name,STARTED:.status.startTime
```

## エイリアス候補

```bash
alias k=kubectl
alias kg='kubectl get'
alias kd='kubectl describe'
alias kl='kubectl logs -f'
alias kex='kubectl exec -it'
alias kctx=kubectx
alias kns=kubens
source <(kubectl completion bash); complete -F __start_kubectl k
```
