---
title: ServiceAccount
parent: 10. セキュリティ
nav_order: 2
---

# ServiceAccount
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**ServiceAccount (SA)** は Pod が Kubernetes API や外部システムへ認証するためのアカウントです。

## 基本

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: todo-api
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
spec:
  template:
    spec:
      serviceAccountName: todo-api
```

Pod が起動すると、`/var/run/secrets/kubernetes.io/serviceaccount/token` に JWT トークンがマウントされ、これで API Server に認証できます。

## Token の進化: BoundServiceAccountToken

旧来は SA を作ると同時に Secret(永続トークン)が作られていましたが、v1.24 以降は **Bound Service Account Token (Projected Volume)** が標準です。

- 有効期限あり (既定1時間)
- Pod 削除時に無効化
- 監査可能 (audience 指定可)

```yaml
spec:
  containers:
  - volumeMounts:
    - name: api-token
      mountPath: /var/run/secrets/tokens
      readOnly: true
  volumes:
  - name: api-token
    projected:
      sources:
      - serviceAccountToken:
          path: token
          expirationSeconds: 3600
          audience: api.example.com
```

## 外部システムへの認証

SA トークンを外部 OIDC IdP として使えるので、**Kubernetes の SA を AWS や Vault の認証主体にできる** という応用があります。
- AWS IRSA (IAM Roles for Service Accounts)
- GCP Workload Identity
- HashiCorp Vault Kubernetes Auth Method

ローカル環境でも Vault Kubernetes Auth でこれを体験可能で、本教材 [Secret管理]({{ '/10-security/secret-management/' | relative_url }}) で扱います。

## 注意

`automountServiceAccountToken: false` を **本当に Kubernetes API を使わない Pod** には必ず付けるのが現代の推奨。

## チェックポイント

- [ ] Bound Service Account Token の利点
- [ ] 「Pod がクラスタAPIを叩く必要があるか」を判断基準にできる
