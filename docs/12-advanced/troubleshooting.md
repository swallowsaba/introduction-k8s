---
title: トラブルシューティング集
parent: 12. 発展トピック
nav_order: 5
---

# トラブルシューティング集
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

ここまで学んだ知識を活かして、**実運用で頻繁に出会う症状とその診断手順** をまとめます。
リファレンスとして使ってください。

## 症状: ImagePullBackOff / ErrImagePull

```
Events:
  Failed to pull image "registry.example.com/api:1.0": ...
```

確認:

```bash
kubectl describe pod <name>     # Events を必ず読む
```

原因の典型:

- イメージ名が typo
- tag が存在しない
- private registry で `imagePullSecrets` が無い
- Registry に到達不可(DNS / firewall)
- `latest` を使っていてキャッシュにいないだけのケース

検証:

```bash
# ノードで
crictl pull registry.example.com/api:1.0
# あるいはdebug Podから
kubectl run net --rm -it --image=nicolaka/netshoot -- bash
curl -k https://registry.example.com/v2/
```

## 症状: CrashLoopBackOff

```
Restart Count: 7
```

```bash
kubectl logs <pod> --previous
kubectl describe pod <pod>
```

原因の典型:

- アプリの起動エラー (env / configmap 不足、DB 接続失敗)
- Liveness Probe が厳しすぎ
- Init Container の失敗
- イメージのコマンド/エントリーポイント間違い

## 症状: Pending のまま動かない

```bash
kubectl describe pod <name>
```

Events を読む。よくある:

- リソース不足: `0/3 nodes available: 3 Insufficient cpu`
- nodeSelector/Affinity が合わない: `0/3 nodes available: 3 didn't match Pod's node affinity`
- PVC が pending: `volume node affinity conflict`
- Taint: `0/3 nodes available: 3 had taints that the pod didn't tolerate`

PVC が pending なら:

```bash
kubectl get pvc
kubectl describe pvc <name>
kubectl get sc           # StorageClass が default に設定されている?
kubectl get pv
```

## 症状: Service につながらない

順番に確認:

```bash
# 1. Endpoints が空でないか
kubectl get endpoints <svc>
# → 空なら selector / Pod label / Pod の Ready 状態を確認

# 2. ClusterIP からアクセス
kubectl run net --rm -it --image=nicolaka/netshoot -- bash
nc -zv <svc-name> <port>

# 3. DNS は引けるか
nslookup <svc-name>

# 4. NetworkPolicy が遮断していないか
kubectl get networkpolicy -A

# 5. kube-proxy / iptables
ssh <node> 'iptables -t nat -L | grep <svc-cluster-ip>'
```

## 症状: ノードが NotReady

```bash
kubectl describe node <name>
ssh <node>
systemctl status kubelet
journalctl -u kubelet --since "30 min ago"
df -h                    # ディスク満杯?
free -h                  # メモリ?
```

頻出:

- containerd 停止/異常
- kubelet 設定不整合
- ディスク満杯 (`/var/lib/containerd` 系)
- 時刻ずれ
- 証明書期限切れ

```bash
# 証明書期限確認
kubeadm certs check-expiration
kubeadm certs renew all
```

## 症状: メモリリーク・OOMKill

```bash
kubectl describe pod <name>
# State の中に "Reason: OOMKilled" がある
```

- アプリのメモリリーク → `pprof` 等でプロファイリング
- Limits が低すぎる → 増やす(VPA Recommendation活用)
- Heap だけでなく page cache も込み → Memory Limits は overhead 含めて設定

## 症状: API Server が遅い

```bash
kubectl get --raw /metrics | grep apiserver_request_duration_seconds_bucket
```

- etcd が遅い? (ディスクIO 確認)
- 大量 Watch クライアント?
- 大きすぎるリスト要求? (`kubectl get pods -A` で30秒掛かる等)

対策:

- etcd を SSD 上へ
- API Server の `--max-requests-inflight` を上げる
- クライアント側で `kubectl get --field-selector` 等で絞る

## 症状: Argo CD が sync しない

```bash
argocd app get <app>
kubectl logs -n argocd deploy/argocd-application-controller
```

- リポジトリ認証エラー
- マニフェストが kustomize/helm でエラー
- destination namespace が無い (CreateNamespace=true)
- diff があるが prune が無い

## 即席チートシート

```bash
# よく落ちる Pod
kubectl get pods -A --field-selector=status.phase!=Running

# 最近の Events
kubectl get events -A --sort-by=.metadata.creationTimestamp | tail -30

# 各Pod のリソース使用
kubectl top pod -A --sort-by=cpu
kubectl top pod -A --sort-by=memory

# ノードのリソース余裕
kubectl describe nodes | grep -A 5 "Allocated resources"

# 全 Resource を YAML 出力 (調査用)
kubectl get all,configmap,secret,pvc,ingress -n prod -o yaml > prod-snapshot.yaml
```

## チェックポイント

- [ ] ImagePullBackOff の原因切り分けを 4 つ
- [ ] Pending の原因切り分けを 4 つ
- [ ] Service につながらない時の確認順序を述べられる
