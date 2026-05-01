---
title: Scheduling (Affinity/PDB/Taint)
parent: 07. 本番運用
nav_order: 5
---

# Scheduling (Affinity/PDB/Taint)
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

Pod の配置先を細かく制御する仕組みを学びます。

## nodeSelector

最もシンプル。ラベルが完全一致するノードに配置。

```yaml
spec:
  nodeSelector:
    disktype: ssd
```

ノード側のラベル設定:

```bash
kubectl label node k8s-w1 disktype=ssd
```

## Node Affinity

より柔軟な配置制御。

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: disktype
            operator: In
            values: [ssd, nvme]
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: zone
            operator: In
            values: [zone-a]
```

| 種類 | 必須/推奨 |
|------|----------|
| `requiredDuringSchedulingIgnoredDuringExecution` | 必須 |
| `preferredDuringSchedulingIgnoredDuringExecution` | 可能なら |

## Pod Affinity / Anti-Affinity

「他の Pod の近くに置く / 離して置く」。

```yaml
# 同じappの Pod を別ノードに分散 (HA基本)
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app.kubernetes.io/name: todo-api
        topologyKey: kubernetes.io/hostname
```

`topologyKey` でどのレベルで「離す」かを決める:

- `kubernetes.io/hostname` : ノード単位
- `topology.kubernetes.io/zone` : AZ単位 (オンプレでもラベル付けして使える)

## Taint と Toleration

ノードに Taint を打つと、対応する Toleration を持たない Pod は配置されません。

```bash
kubectl taint nodes k8s-w3 dedicated=db:NoSchedule
```

```yaml
spec:
  tolerations:
  - key: dedicated
    operator: Equal
    value: db
    effect: NoSchedule
```

Effect の種類:

| effect | 動作 |
|--------|------|
| `NoSchedule` | 新規 Pod を配置しない |
| `PreferNoSchedule` | 可能な限り避ける |
| `NoExecute` | 既存 Pod も追い出す |

マスターノードには既定で `node-role.kubernetes.io/control-plane:NoSchedule` の Taint が付いています。

## Topology Spread Constraints

複数ゾーン/ノードに均等にばらすための仕組み。
podAntiAffinity より柔軟。

```yaml
spec:
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app.kubernetes.io/name: todo-api
```

ノードごとに同名 Pod の数の差が `maxSkew` を超えないよう配置。

## PodDisruptionBudget (PDB)

ノードのドレイン(`kubectl drain`)や Cluster Autoscaler によるノード削減で、**同時に何個まで Pod が落ちてよいか** を宣言します。

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: todo-api
spec:
  minAvailable: 2          # 最低2つは生かす
  selector:
    matchLabels:
      app.kubernetes.io/name: todo-api
```

または:

```yaml
spec:
  maxUnavailable: 1
```

PDB がないと、ドレインで全 Pod が同時に落ちる可能性があります。**HA 構成のサービスには必ず設定**。

## ハンズオン: ドレイン

```bash
# PDB 設定 + replicas=3 でデプロイ
# ノードを drain
kubectl drain k8s-w1 --ignore-daemonsets --delete-emptydir-data

# 別ノードに Pod が移ったか確認
kubectl get pods -l app.kubernetes.io/name=todo-api -o wide

# 復帰
kubectl uncordon k8s-w1
```

PDB に違反する drain は中断されます。

## チェックポイント

- [ ] 同名 Pod を別ノードに分散させる YAML を書ける
- [ ] Taint と Toleration の組み合わせの効果
- [ ] PDB を入れずにドレインすると何が起きるか
