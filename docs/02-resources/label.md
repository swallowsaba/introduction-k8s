---
title: Label と Selector
parent: 02. リソースの基礎
nav_order: 7
---

# Label と Selector
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**Label** は Kubernetes リソースに付ける Key-Value のメタデータで、Kubernetes の **多くの機能の土台** です。

- Service が Pod を見つけるとき
- Deployment が自分の管理する Pod を見つけるとき
- NetworkPolicy が対象を選ぶとき
- ノードへのアフィニティ

すべてラベルを使います。

## 付与

```yaml
metadata:
  name: web
  labels:
    app: web
    env: prod
    version: v1.2.3
    tier: frontend
```

```bash
kubectl label pod nginx env=dev
kubectl label pod nginx env=stg --overwrite
kubectl label pod nginx env-          # 削除
kubectl get pods --show-labels
```

## Selector

### 等価ベース

```bash
kubectl get pods -l app=web
kubectl get pods -l 'app=web,env=prod'
kubectl get pods -l 'app!=web'
```

### 集合ベース

```bash
kubectl get pods -l 'env in (dev,stg)'
kubectl get pods -l 'env notin (prod)'
kubectl get pods -l 'tier'      # 存在チェック
kubectl get pods -l '!tier'     # 不在チェック
```

### YAML内のセレクタ

```yaml
spec:
  selector:
    matchLabels:
      app: web
    matchExpressions:
    - {key: env, operator: In, values: [prod, stg]}
    - {key: version, operator: Exists}
```

## 推奨ラベル (Kubernetes公式)

`app.kubernetes.io/*` プレフィックスで標準ラベルが定義されています。
Helm や Kustomize、運用ツールの多くがこれを前提に動くので、新規で書くなら付けるのが望ましい。

| ラベル | 意味 | 例 |
|--------|------|-----|
| `app.kubernetes.io/name` | アプリ名 | `wordpress` |
| `app.kubernetes.io/instance` | インスタンス識別 | `wordpress-blog-a` |
| `app.kubernetes.io/version` | バージョン | `5.7.1` |
| `app.kubernetes.io/component` | 役割 | `database` |
| `app.kubernetes.io/part-of` | 上位アプリ | `wordpress` |
| `app.kubernetes.io/managed-by` | 管理ツール | `helm` / `argocd` |

## Annotationとの違い

| | Label | Annotation |
|---|---|---|
| 用途 | フィルタ・選択 | 補足情報・ツール連携 |
| 値の長さ | 63文字以下 | 制限緩い |
| Selector で使える | ◯ | ✗ |
| 例 | `env=prod` | `kubernetes.io/change-cause=deploy by alice` |

## 落とし穴: Deployment の selector は immutable

`spec.selector` は **作成後に変更できません**。
ラベル設計を後から変えたいときは、Deployment ごと作り直しになります。
**最初から組織で統一されたラベル規約** を決めるのが重要。

## チェックポイント

- [ ] Label と Annotation の使い分けを説明できる
- [ ] Service の selector が Pod の labels と一致しないと何が起きるか
- [ ] 推奨ラベルを 3 つ以上挙げられる
