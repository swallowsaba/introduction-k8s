---
title: キャパシティ計画
parent: 11. SRE運用
nav_order: 3
---

# キャパシティ計画
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**今のリソースで何ヶ月もつか?** **次の四半期に何台買い足すか?** を予測する活動。
本番運用を始めると避けて通れません。

## 観測すべき指標

| レイヤー | 指標 | 警戒水準 |
|----------|------|----------|
| ノード CPU | Allocated / Allocatable | 70% 超で増設検討 |
| ノード Memory | Allocated / Allocatable | 70% 超で増設検討 |
| Pod 数 | Pods used / Pods Capacity | 80% 超 |
| etcd | DB size | 8GB 接近で警戒 |
| API Server | request latency p99 | 1s 超で警戒 |

## PromQL での収集例

```promql
# クラスタ全体の CPU Requests 充填率
sum(kube_pod_container_resource_requests{resource="cpu"})
/
sum(kube_node_status_allocatable{resource="cpu"})

# Memory も同様
sum(kube_pod_container_resource_requests{resource="memory"})
/
sum(kube_node_status_allocatable{resource="memory"})

# Pod数の使用率
sum(kube_pod_info)
/
sum(kube_node_status_allocatable{resource="pods"})
```

これらを Grafana で **時系列で** 見るのが重要。
「7 日前比 / 30 日前比」を出して傾向把握。

## ローカル環境での疑似演習

VM 1 台あたり 4GB RAM の構成なら、ノード追加スクリプトで擬似 Cluster Autoscaler を体験。

```bash
#!/bin/bash
# scripts/cluster-grow.sh
# Pod 充填率が80%を超えたら 1台追加
RATE=$(promql 'sum(kube_pod_container_resource_requests{resource="memory"})/sum(kube_node_status_allocatable{resource="memory"})')
if (( $(echo "$RATE > 0.8" | bc -l) )); then
  ./add-worker.sh k8s-w$NEW_NUM
fi
```

## etcd のサイジング

- 1コア / 2GB RAM / SSD が最小
- DB サイズの 80% でアラート、100% で書き込み停止
- 定期的なコンパクション・デフラグが必要

```bash
# 状態確認
ETCDCTL_API=3 etcdctl endpoint status -w table
ETCDCTL_API=3 etcdctl endpoint health

# コンパクション + デフラグ
ETCDCTL_API=3 etcdctl compact $(etcdctl endpoint status -w json | jq -r '.[0].Status.header.revision')
ETCDCTL_API=3 etcdctl defrag --cluster
```

## チェックポイント

- [ ] CPU / Memory / Pod 数のキャパシティ指標を答えられる
- [ ] etcd の容量超過時のリスク
- [ ] 「7日比トレンド」を観るために必要なツール
