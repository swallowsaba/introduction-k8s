---
title: Secret
parent: 06. 設定とSecret
nav_order: 2
---

# Secret
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**Secret** は機密情報用のリソース。基本構造は ConfigMap と同じだが、扱いが特別。

{: .warning }
Kubernetes の Secret は **Base64 エンコードされているだけ** で、暗号化はされていません。
etcd レベルの暗号化(`EncryptionConfiguration`)を有効化しないと、etcd を読まれた時点でアウトです。本番運用では etcd 暗号化、外部 Secret 管理(External Secrets / Sealed Secrets / SOPS)を検討します。10章で扱います。

## 作成

```bash
# 値から
kubectl create secret generic todo-secret \
  --from-literal=DB_PASSWORD='supersecret' \
  --from-literal=JWT_SECRET='abcdef123456'

# ファイルから
kubectl create secret generic tls-cert --from-file=tls.crt --from-file=tls.key
```

YAML:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: todo-secret
type: Opaque
data:
  DB_PASSWORD: c3VwZXJzZWNyZXQ=     # base64
  JWT_SECRET: YWJjZGVmMTIzNDU2
# stringData を使えばbase64しなくてよい
stringData:
  ANOTHER_KEY: plaintext
```

## Secret の種類 (type)

| type | 用途 |
|------|------|
| Opaque | 一般的なKey-Value (既定) |
| kubernetes.io/dockerconfigjson | プライベートレジストリ認証 |
| kubernetes.io/tls | TLS証明書 (`tls.crt` / `tls.key`) |
| kubernetes.io/service-account-token | ServiceAccountトークン |
| kubernetes.io/basic-auth | basic認証 |
| kubernetes.io/ssh-auth | SSH秘密鍵 |

## Pod への注入

ConfigMap と同じ。

```yaml
spec:
  containers:
  - name: app
    env:
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: todo-secret
          key: DB_PASSWORD
    envFrom:
    - secretRef:
        name: todo-secret
    volumeMounts:
    - name: secret-vol
      mountPath: /etc/secrets
      readOnly: true
  volumes:
  - name: secret-vol
    secret:
      secretName: todo-secret
      defaultMode: 0400      # 権限を絞る
```

## プライベートレジストリ認証

サンプルアプリのイメージを社内レジストリに置く場合の例。

```bash
kubectl create secret docker-registry regcred \
  --docker-server=192.168.56.10:5000 \
  --docker-username=admin \
  --docker-password=admin
```

```yaml
spec:
  imagePullSecrets:
  - name: regcred
  containers:
  - name: app
    image: 192.168.56.10:5000/todo-api:0.1.0
```

## etcd 暗号化

kubeadmで暗号化を有効化する設定例:

```yaml
# /etc/kubernetes/encryption-config.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources:
  - secrets
  providers:
  - aescbc:
      keys:
      - name: key1
        secret: <base64 32 bytes>
  - identity: {}
```

kube-apiserver の起動オプションに `--encryption-provider-config=/etc/kubernetes/encryption-config.yaml` を追加。
本番では必須の設定です。詳しくは 10 章 [Secret管理]({{ '/10-security/secret-management/' | relative_url }}) で。

## チェックポイント

- [ ] Secret は何で守られていて、何で守られていないか
- [ ] etcd 暗号化を入れるとどう変わるか
- [ ] イメージを private registry から pull するための YAML を書ける
