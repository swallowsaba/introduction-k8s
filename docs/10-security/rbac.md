---
title: RBAC
parent: 10. セキュリティ
nav_order: 1
---

# RBAC
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**Role-Based Access Control (RBAC)** は Kubernetes の認可機構。
誰が(Subject)、何に対して(Resource)、何ができるか(Verb)を定義します。

## 4つのリソース

| リソース | スコープ | 内容 |
|----------|----------|------|
| Role | Namespace | NamespaceスコープのResource操作権限 |
| ClusterRole | Cluster | クラスタ全体のResource操作権限 |
| RoleBinding | Namespace | RoleをUser/Group/SAに付与 |
| ClusterRoleBinding | Cluster | ClusterRoleを付与 |

## Role の例

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: prod
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log"]
  verbs: ["get", "list", "watch"]
```

## RoleBinding の例

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: prod
subjects:
- kind: User
  name: alice@example.com
  apiGroup: rbac.authorization.k8s.io
- kind: ServiceAccount
  name: monitoring
  namespace: monitoring
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

## ClusterRole + RoleBinding の組合せ

「同じ権限を複数 Namespace で使い回したい」とき、ClusterRole を作って各 Namespace で RoleBinding するのが定石。

## 検証

```bash
kubectl auth can-i list pods --as alice@example.com -n prod
kubectl auth can-i delete deployments --as alice@example.com -n prod

# ServiceAccount の場合
kubectl auth can-i list secrets --as=system:serviceaccount:prod:default -n prod
```

## ベストプラクティス

### 1. 最小権限の原則

`*` (全Verb / 全Resource) は緊急時の human admin 用に温存し、SA や個別ロールには必要最小限のみ。

### 2. ServiceAccount を Pod ごとに分ける

`default` SA を使い回さず、Pod の用途別に SA を作って権限を絞る。

```yaml
# api 用の SA
apiVersion: v1
kind: ServiceAccount
metadata:
  name: todo-api
  namespace: prod
automountServiceAccountToken: false   # 不要なら off
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
spec:
  template:
    spec:
      serviceAccountName: todo-api
      automountServiceAccountToken: false
```

API トークンが Pod に注入されると、漏洩リスクと攻撃範囲が広がります。**必要ない Pod では automount を切る**。

### 3. 既存 ClusterRole の活用

`view` / `edit` / `admin` / `cluster-admin` という標準 ClusterRole がある。

```bash
kubectl get clusterrole view -o yaml
```

組織の運用ロールはこれらを土台に作るのが楽。

### 4. グループとの連携

外部 IDP(OIDC)で発行されるグループに RoleBinding することで、人の出入りを RBAC YAML に直接書かなくて済む。

## チェックポイント

- [ ] Role と ClusterRole の使い分け
- [ ] Pod ごとに SA を分ける利点
- [ ] `kubectl auth can-i` が必要になる場面
