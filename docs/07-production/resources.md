---
title: リソース管理 (Requests/Limits)
parent: 07. 本番運用
nav_order: 3
---

# リソース管理 (Requests/Limits)
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

Pod ごとに **CPU / Memory の Requests と Limits** を設定するのは、本番運用で **必須** です。
設定しないと「特定 Pod がノードを食い尽くしてクラスタ全体が不安定化」が容易に起こります。

## Requests と Limits

| | Requests | Limits |
|---|---|---|
| 意味 | スケジューリングに使う「予約」 | 実行時の上限 |
| CPU 超過 | 関係なし | スロットリング (kill されない) |
| Memory 超過 | 関係なし | OOMKill |

```yaml
spec:
  containers:
  - name: api
    image: todo-api:0.1.0
    resources:
      requests:
        cpu: 100m       # 0.1 vCPU
        memory: 128Mi
      limits:
        cpu: 500m       # 0.5 vCPU
        memory: 256Mi
```

## 単位

- **CPU**: `1` = 1 vCPU、`100m` = 0.1 vCPU (`m` = millicore)
- **Memory**: `Ki`, `Mi`, `Gi` (2 進数) または `K`, `M`, `G` (10 進数)

## QoS Class

Pod の Requests/Limits の組み合わせから自動的に決まる優先度。
ノードリソース逼迫時の Eviction 対象決定に使われます。

| Class | 条件 | Eviction優先順位 |
|-------|------|------------------|
| Guaranteed | Requests = Limits (両方とも設定) | 最後 |
| Burstable | Requests のみ、または Requests < Limits | 中間 |
| BestEffort | Requests/Limits 未設定 | 最初に殺される |

```bash
kubectl get pod <name> -o jsonpath='{.status.qosClass}'
```

**本番ではクリティカルな Pod は Guaranteed**、一般は Burstable、Best Effort は使わない、が基本。

## CPU Limits の罠

CPU Limits を設定すると、超えた瞬間にスロットリングがかかります。
これが意外と問題で、**Limitsを「やや厳しめ」に設定すると本番でレイテンシが悪化** することがあります。
最近のベストプラクティスとしては:

- **Requests は必ず設定**(スケジューリング正確性、QoS的に)
- **Memory Limits は設定**(OOMで暴走を止める)
- **CPU Limits は設定しない、もしくは緩めに**

という考え方が広まっています。Datadog、Buoyant、Robusta 等も同様の推奨をしています。

## ノードのリソース配分

```bash
kubectl describe node k8s-w1
```

`Allocatable` がそのノードに使える総量。`Allocated resources` で各 Pod の Requests 合計が見えます。

```
Capacity:
  cpu:                2
  memory:             4001852Ki
Allocatable:
  cpu:                1900m       # システム予約後
  memory:             3399676Ki
Allocated resources:
  Resource           Requests      Limits
  --------           --------      ------
  cpu                850m (44%)    1500m (78%)
  memory             1024Mi (30%)  2Gi (60%)
```

## オーバーコミット

Requests の合計はノードキャパを超えられませんが、**Limits の合計は超えられます**。
これが「コンテナの密度を上げる」一因。
ただし全 Pod が一斉に Limits まで使ったらノード崩壊するので、Limits 設計は実測ベースで控えめに。

## 適切な値の決め方

1. **dev で動かして観測**(`kubectl top pod`)
2. **負荷試験で観測**(p99 値を見る)
3. **prod で観測しながら微調整**

`kubectl top` のためには Metrics Server が必要:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# ローカル環境では --kubelet-insecure-tls を args に追加が必要
```

## ResourceQuota との連携

Namespace 単位の制限は 2 章 [Namespace]({{ '/02-resources/namespace/' | relative_url }}) で扱った通り。
ResourceQuota が設定された Namespace では、**Resources 未設定の Pod は admission で拒否されます** ─ これが Resources 設定を強制するベストプラクティス。

## チェックポイント

- [ ] CPU Limit と Memory Limit の超過時の挙動の違いを説明できる
- [ ] QoS Class が Guaranteed になる条件
- [ ] CPU Limits を入れない/緩める根拠
