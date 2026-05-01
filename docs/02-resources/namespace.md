---
title: Namespace
parent: 02. リソースの基礎
nav_order: 6
---

# Namespace
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**Namespace** はクラスタ内を **論理的に分割** する仕組み。
1クラスタ上に複数の環境(dev/stg)、チーム、アプリを共存させるときに使います。

## 既定のNamespace

```bash
kubectl get namespaces
```

| Namespace | 用途 |
|-----------|------|
| default | 何も指定しないとここに作られる |
| kube-system | クラスタコンポーネント (CoreDNS, kube-proxy) |
| kube-public | 全ユーザーが読める情報置き場 |
| kube-node-lease | ノードハートビート管理 |

ユーザーアプリは **default に置かない** のが鉄則。

## 作成

```bash
kubectl create namespace dev
```

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: dev
  labels:
    env: dev
    team: platform
```

## NamespaceスコープとClusterスコープ

| Namespaceスコープ | Clusterスコープ |
|---|---|
| Pod, Deployment, Service, ConfigMap, Secret, PVC, Role, RoleBinding | Node, PV, StorageClass, ClusterRole, ClusterRoleBinding, Namespace 自身 |

```bash
kubectl api-resources --namespaced=true
kubectl api-resources --namespaced=false
```

## Namespaceをまたぐ通信

Service の DNS は `<service>.<namespace>.svc.cluster.local`。

- 同じ Namespace : `web` だけで引ける
- 別 Namespace : `web.prod` または `web.prod.svc.cluster.local`

## 設計指針

「環境ごと」「チームごと」「アプリごと」など複数の軸があり、組織により正解は異なります。

```
パターンA (環境×コンポーネント)
  dev-frontend / dev-backend / stg-frontend / ...

パターンB (チーム単位)
  team-a / team-b / shared-infra
```

クラスタを分けるか Namespace で分けるか:

| 軸 | クラスタ分割 | Namespace分割 |
|---|---|---|
| 障害の隔離 | 強い | 弱い (CNI/etcd障害は共通) |
| RBAC で十分か | — | OK |
| バージョン違いを許容 | OK | NG |
| コスト | 高い | 安い |
| マルチテナント (外部組織) | 推奨 | 非推奨 |

**本番と本番候補(stg)はクラスタ分け、開発系はNamespace分け** が堅実なパターン。

## ResourceQuota と LimitRange

Namespace 単位で利用量を制限。マルチテナント運用では必須。

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: dev-quota
  namespace: dev
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "50"
    persistentvolumeclaims: "10"
```

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: dev-limits
  namespace: dev
spec:
  limits:
  - type: Container
    default:        {cpu: 200m, memory: 256Mi}
    defaultRequest: {cpu: 100m, memory: 128Mi}
    max:            {cpu: 2,    memory: 2Gi}
```

LimitRangeがあると Resources を書き忘れた Pod に既定値が当たる。
ResourceQuotaがある Namespace では Resources 未設定の Pod は **作成自体が拒否** されます。

## チェックポイント

- [ ] Namespace の解決する課題を 2 つ以上挙げられる
- [ ] 「Namespace で分ければ十分」「クラスタを分けるべき」を判断できる
- [ ] ResourceQuota と LimitRange の役割の違いを説明できる
