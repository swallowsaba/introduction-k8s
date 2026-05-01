---
title: コスト最適化
parent: 12. 発展トピック
nav_order: 4
---

# コスト最適化
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

ローカル環境ではクラウド費用は発生しませんが、本教材で学んだ知識は **クラウドへ持っていったときに大きく効きます**。
コスト最適化はクラウドネイティブ運用の重要テーマです。

## 主な観点

### 1. Right-sizing

Resources Requests を実測ベースで適切な値にする。
過大設定はノード数を増やす元凶。

ツール:

- VPA (Recommendation only モード)
- Goldilocks (VPA をラップしてレポート化)
- Robusta KRR

### 2. Bin-packing 最適化

スケジューラに詰め込みやすい構成にする。

- 大きい Pod を作らない(分割する)
- Node の規格を揃える
- 不要な Affinity を入れない

### 3. オートスケーリング

- HPA で「ピーク時だけスケールアウト」
- Cluster Autoscaler / Karpenter で「Pod 不足時だけノード追加」

### 4. アイドルワークロードの停止

dev/stg は夜間・週末は止める。`kube-downscaler` 等。

```yaml
metadata:
  annotations:
    downscaler/uptime: "Mon-Fri 09:00-19:00 Asia/Tokyo"
```

### 5. Spot / Preemptible の活用 (クラウド)

Spot インスタンスを Worker に使うと 70% 程度の割引。ただし即停止リスクがあるので、

- ステートレスな Pod のみ
- PDB と Replicaを設定
- Cluster Autoscaler が混在を扱える設定

が必要。Karpenter は Spot に強い。

### 6. 観測

何にお金が掛かっているかを可視化:

- **OpenCost** : K8s ネイティブのコスト可視化 (Pod / Namespace 単位の課金)
- **Kubecost** : OpenCost をベースにした製品

```bash
helm install opencost opencost-charts/opencost -n opencost --create-namespace
```

OpenCost は Prometheus メトリクスを使って計算するので、ローカル環境でも「**もしクラウドに上げたら月いくらか?**」を見積もれます。
学習用途として面白い。

## ローカル環境での演習

サンプルアプリの requests/limits を実測ベースで見直し、Goldilocks のレコメンドに従って調整するのが良い練習になります。

```bash
helm install goldilocks fairwinds-stable/goldilocks -n goldilocks --create-namespace
kubectl label namespace prod goldilocks.fairwinds.com/enabled=true
```

UI で「現在 cpu:500m memory:512Mi 設定だが、推奨は cpu:120m memory:160Mi」のように出ます。

## チェックポイント

- [ ] Right-sizing にツールを 2 つ挙げられる
- [ ] Spot 活用時の前提条件を 2 つ
- [ ] OpenCost が解決する課題
