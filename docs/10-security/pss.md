---
title: Pod Security Standards
parent: 10. セキュリティ
nav_order: 3
---

# Pod Security Standards
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

旧 PodSecurityPolicy(PSP)が v1.25 で削除され、代わりに **Pod Security Standards (PSS)** + **Pod Security Admission (PSA)** が導入されました。

## 3つのプロファイル

| Level | 内容 |
|-------|------|
| **privileged** | 制限なし |
| **baseline** | 既知の特権昇格を防ぐ最小限 |
| **restricted** | 強くハードニングされた状態 (推奨) |

## Namespace ラベルで適用

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: prod
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

| ラベル | 効果 |
|--------|------|
| enforce | 違反する Pod の作成を拒否 |
| audit | 監査ログに記録 |
| warn | クライアントに警告表示 |

新規 Namespace には `restricted` を当てるのが望ましく、既存は `audit`/`warn` で観察 → 段階的移行。

## restricted プロファイルが要求するもの

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: app
    image: myapp:1.0
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: ["ALL"]
```

主な制約:

- root で動かさない
- 特権昇格不可
- 全 Capabilities drop (NET_BIND_SERVICE 等は明示追加)
- root filesystem は read-only
- seccomp profile を設定

## アプリ側の対応

`readOnlyRootFilesystem: true` の場合、書き込みが必要なディレクトリは emptyDir でマウント:

```yaml
volumes:
- name: tmp
  emptyDir: {}
volumeMounts:
- name: tmp
  mountPath: /tmp
```

Dockerfile での **非 root ユーザー化** を忘れずに。

```dockerfile
FROM python:3.12-slim
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -m app
USER 1000
```

## より細かい制御

PSA は単純なので、より細かく制御するなら:

- **Kyverno** : YAMLで policy を書ける
- **OPA Gatekeeper** : Rego でポリシー記述
- **Kubewarden** : WASM ベース

```yaml
# Kyverno: latest タグ禁止
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: disallow-latest-tag
spec:
  validationFailureAction: Enforce
  rules:
  - name: require-image-tag
    match:
      any:
      - resources:
          kinds: [Pod]
    validate:
      message: "Using a mutable image tag like 'latest' is not allowed."
      pattern:
        spec:
          containers:
          - image: "!*:latest"
```

## チェックポイント

- [ ] privileged / baseline / restricted の違い
- [ ] restricted を満たすための Dockerfile/Manifest 修正点を 3 つ
- [ ] Kyverno で書く有用なポリシーを 1 つ提案できる
