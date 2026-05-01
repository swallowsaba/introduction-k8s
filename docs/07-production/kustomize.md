---
title: Kustomize
parent: 07. 本番運用
nav_order: 7
---

# Kustomize
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**Kustomize** はテンプレート言語を使わずに、**プレーンな YAML を base + overlays でカスタマイズ** するツール。
`kubectl apply -k` で標準内蔵されています。

## 構成

```
sample-app/k8s/07-kustomize/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   └── secret.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── replicas-patch.yaml
    ├── stg/
    │   ├── kustomization.yaml
    │   └── ...
    └── prod/
        ├── kustomization.yaml
        ├── replicas-patch.yaml
        ├── resources-patch.yaml
        └── ingress-patch.yaml
```

## base/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- deployment.yaml
- service.yaml
- configmap.yaml
- secret.yaml
commonLabels:
  app.kubernetes.io/name: todo-api
  app.kubernetes.io/managed-by: kustomize
```

## overlays/prod/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: prod
namePrefix: prod-
commonLabels:
  env: prod

resources:
- ../../base

patches:
- path: replicas-patch.yaml
- path: resources-patch.yaml

images:
- name: 192.168.56.10:5000/todo-api
  newTag: 1.2.3

configMapGenerator:
- name: todo-config
  behavior: merge
  literals:
  - LOG_LEVEL=warn
```

`patches` は SMP(Strategic Merge Patch)または JSON6902 が使えます。

## replicas-patch.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
spec:
  replicas: 5
```

## ビルドと適用

```bash
kubectl kustomize overlays/prod   # 出力を確認
kubectl apply -k overlays/prod    # 適用
kubectl diff -k overlays/prod     # 差分
```

## ConfigMapGenerator / SecretGenerator

ConfigMap/Secret を kustomization から生成。

```yaml
configMapGenerator:
- name: todo-config
  literals:
  - LOG_LEVEL=info
  - DB_HOST=postgres
  files:
  - app.conf

secretGenerator:
- name: todo-secret
  literals:
  - DB_PASSWORD=secret
```

中身が変わると **生成名にハッシュサフィックスが付く** ため、Pod が自動再起動するメリット付き。

## Helm との比較・併用

両者は併用できます。
パターン1: **Helm Chart を Kustomize から呼ぶ**:

```yaml
helmCharts:
- name: postgresql
  repo: https://charts.bitnami.com/bitnami
  version: 15.5.0
  releaseName: my-pg
  namespace: db
  valuesFile: values-pg.yaml
```

`kubectl kustomize --enable-helm` で展開。

## 落とし穴

- `commonLabels` は **selector** にも入る
- 既存の Deployment の selector は immutable なので、後から `commonLabels` を変えると apply に失敗する
- `namespace:` を kustomization に書くと配下全リソースに当たるが、Namespace スコープでないリソース(ClusterRole等)も対象になるので注意
- `images:` でタグ書き換えしておくと、CI 連携で便利(`kustomize edit set image`)

## チェックポイント

- [ ] base/overlays の構成が書ける
- [ ] replicas をオーバーレイで上書きするパッチが書ける
- [ ] Kustomize が Helm と排他関係でないことを説明できる
