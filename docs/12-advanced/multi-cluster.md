---
title: マルチクラスタ
parent: 12. 発展トピック
nav_order: 3
---

# マルチクラスタ
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

クラスタを分割する動機:

- 障害分離(1 クラスタの障害が他に波及しない)
- 地理分散(エッジ、リージョン)
- ステージング分離(本番と非本番)
- マルチテナント(顧客ごとにクラスタ)
- バージョン違いの混在

## 構築パターン

| パターン | ツール |
|----------|--------|
| 同一マニフェストを各クラスタに配信 | Argo CD ApplicationSet |
| クラスタを跨ぐ Service ディスカバリ | Submariner、Istio multi-cluster、Cilium ClusterMesh |
| KubeFed (Kubernetes Federation) | KubeFed v2 (停滞気味) |
| API Server を 1 つに見せる | Kamaji、vCluster |

## ローカル演習: kubeadm を 2 クラスタ立てる

VMware Workstation 上で **クラスタ A**(192.168.56.0/24)と **クラスタ B**(192.168.57.0/24)を立てる構成。
ホスト 128GB あれば余裕です。

```
ClusterA: cp/w 各3台 = 6台 × 4GB = 24GB
ClusterB: cp/w 各2台 = 4台 × 4GB = 16GB
合計 40GB
```

各クラスタに Argo CD を入れ、**1つのリポジトリ** から両方にデプロイする ApplicationSet 例:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: todo-multi
spec:
  generators:
  - clusters:
      selector:
        matchLabels:
          purpose: app
  template:
    metadata:
      name: 'todo-{{name}}'
    spec:
      project: default
      source:
        repoURL: https://github.com/<USER>/todo-manifests
        targetRevision: main
        path: 'overlays/{{metadata.labels.env}}'
      destination:
        server: '{{server}}'
        namespace: prod
      syncPolicy:
        automated: {prune: true, selfHeal: true}
```

クラスタ登録は `argocd cluster add <CONTEXT>`。
ラベルを付ければ ApplicationSet で柔軟に対象を制御できます。

## サービスディスカバリの跨り

「クラスタAの Pod から クラスタBの Service を呼ぶ」ためには:

- **Submariner** : Service を「エクスポート」してメッシュ経由で他クラスタに見せる
- **Cilium ClusterMesh** : eBPF ベースで透過的
- **Istio multi-cluster** : メッシュ全体で 1 つの名前空間として見える

オンプレ・ローカル環境でも Submariner / Cilium ClusterMesh は組み込み可能。

## クラスタの管理面

複数クラスタを kubectl で行き来するなら **kubectx** + **fzf**:

```bash
kubectx       # コンテキスト切替
kubens        # Namespace切替
```

クラスタを束ねる管理画面:

- Rancher
- Argo CD UI(複数クラスタを 1 画面で)
- Headlamp、Lens(IDE)

## チェックポイント

- [ ] マルチクラスタの動機を 3 つ
- [ ] ApplicationSet で複数クラスタを束ねる利点
- [ ] サービスディスカバリの選択肢を 1 つ
