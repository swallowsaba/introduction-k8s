---
title: kubectlの基本
parent: 02. リソースの基礎
nav_order: 2
---

# kubectlの基本
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

`kubectl` は Kubernetes API への CLI クライアント。本章では実運用で頻繁に使うコマンドと効率化テクをまとめます。

## kubeconfig

`kubectl` は **kubeconfig** ファイルを読んで API Server と認証情報を知ります。デフォルトは `~/.kube/config`。

```bash
kubectl config current-context              # 現在のコンテキスト
kubectl config view                         # 設定一覧
kubectl config use-context <name>           # コンテキスト切替
kubectl config set-context --current --namespace=dev  # Namespaceを既定に

# 複数の kubeconfig をマージ
export KUBECONFIG=~/.kube/config:~/.kube/staging.yaml
```

## コマンドのパターン

```
kubectl <verb> <resource> [name] [flags]
```

| verb | 用途 |
|------|------|
| `get` | 一覧 |
| `describe` | 詳細(イベント含む) |
| `create` | 作成(命令型) |
| `apply` | 作成 or 更新(宣言型) |
| `delete` | 削除 |
| `edit` | エディタで編集 |
| `logs` | ログ表示 |
| `exec` | Pod 内コマンド実行 |
| `port-forward` | ローカルへ転送 |
| `explain` | スキーマ説明 |

## get の頻出パターン

```bash
kubectl get pods
kubectl get pods -A                    # 全Namespace
kubectl get pods -n kube-system
kubectl get pods -o wide               # ノード名/IP表示
kubectl get pods -o yaml               # YAMLフル出力
kubectl get pods --watch               # 変化を見続ける
kubectl get pods -l app=web            # ラベルセレクタ
kubectl get pods --field-selector=status.phase=Running
```

## describe — 困ったらこれ

「Pod が起動しない」ときの第一手は describe。
末尾の `Events:` セクションに、スケジュール失敗・イメージ pull 失敗・OOM など、原因の手がかりがほぼ載っています。

```bash
kubectl describe pod <name>
```

## apply と create の違い

```bash
kubectl create -f deploy.yaml   # 命令型: 既にあるとエラー
kubectl apply -f deploy.yaml    # 宣言型: なければ作る、あれば差分適用
```

`apply` は内部で `last-applied-configuration` annotation を使った 3-way merge を行います。
**運用で書くコマンドはほぼ `apply`** と覚えてOK。

## explain — ドキュメントを引かずにスキーマ確認

```bash
kubectl explain pod.spec.containers
kubectl explain deployment.spec.strategy --recursive
```

YAMLを書きながら詰まったときに便利です。

## デバッグ

```bash
# ログ
kubectl logs <pod>
kubectl logs <pod> -c <container>
kubectl logs <pod> --previous       # 1つ前の起動のログ
kubectl logs -l app=web --tail=100  # 複数Pod横断

# 中に入る
kubectl exec -it <pod> -- bash
kubectl exec -it <pod> -c <container> -- sh

# ローカルにポート転送
kubectl port-forward svc/web 8080:80

# ファイル転送
kubectl cp <pod>:/etc/nginx/nginx.conf ./nginx.conf

# 一時的なデバッグ用 Pod
kubectl run debug --rm -it --image=nicolaka/netshoot -- bash
```

`netshoot` には `dig`, `curl`, `tcpdump`, `traceroute` 等が入っており、ネットワーク調査で重宝します。

## Dry-run と差分

```bash
# YAMLを生成 (実際には作らない)
kubectl create deployment web --image=nginx --replicas=3 --dry-run=client -o yaml > web.yaml

# 適用前の差分確認 (重要!)
kubectl diff -f web.yaml

# サーバーサイド検証
kubectl apply -f web.yaml --dry-run=server
```

特に `kubectl diff` は本番作業前に必ず使うクセを付けてください。

## 効率化

### エイリアス

```bash
alias k=kubectl
alias kgp='kubectl get pods'
alias kgs='kubectl get svc'
alias kgd='kubectl get deploy'
alias kdp='kubectl describe pod'
alias kex='kubectl exec -it'
source <(kubectl completion bash)
complete -F __start_kubectl k
```

### kubectx / kubens

複数クラスタを行き来する人は必須。

```bash
brew install kubectx
```

### k9s

ターミナルのインタラクティブUI。

```bash
brew install k9s
k9s
```

{: .warning }
`k9s` は便利ですが、本番作業ログが残らないため、**変更系の操作は kubectl を直叩き** で履歴に残すのが運用上の基本です。

## チェックポイント

- [ ] `apply` と `create` の違いと、運用でどちらを使うか答えられる
- [ ] Pod の不調時に最初に打つコマンドを2つ言える
- [ ] `kubectl diff` を本番作業フローに組み込める
