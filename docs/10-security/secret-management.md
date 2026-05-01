---
title: Secret管理
parent: 10. セキュリティ
nav_order: 5
---

# Secret管理
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

6章で見たとおり、素の Kubernetes Secret は **base64 にすぎず、etcd に平文同然** で保存されます。
本番運用では以下のいずれかを必ず採用します。

## 選択肢

| 方法 | 学習しやすさ | 推奨度 |
|------|--------------|--------|
| etcd 暗号化 | ◎ | 必須 |
| Sealed Secrets | ◎ | ◯ |
| SOPS + Helm Secrets / Kustomize plugin | ◯ | ◯ |
| External Secrets Operator + Vault/AWS Secrets Manager | △ | ◎ |

ローカル環境では学習に最適なのは **Sealed Secrets** と、**Vault + External Secrets**。本教材では両方触ります。

## etcd 暗号化 (まず最初に)

7 章のkubeadm 構築時に EncryptionConfiguration を有効化する設定を入れる。
これだけで etcd ダンプが奪取されても直接読まれない状態にできる。

## Sealed Secrets

公開鍵で暗号化された YAML(SealedSecret)を **Git に commit してOK** にする仕組み。
クラスタ内のコントローラが秘密鍵で復号して Secret に変換します。

```bash
# インストール
helm install sealed-secrets sealed-secrets/sealed-secrets -n kube-system

# kubeseal CLI
brew install kubeseal

# 通常の Secret を作って sealed に変換
kubectl create secret generic todo-secret \
  --from-literal=DB_PASSWORD=supersecret \
  --dry-run=client -o yaml > secret.yaml
kubeseal -f secret.yaml -w sealed-secret.yaml

git add sealed-secret.yaml      # OK!
```

`sealed-secret.yaml`:

```yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: todo-secret
  namespace: prod
spec:
  encryptedData:
    DB_PASSWORD: AgB...暗号化済...==
```

メリット:

- GitOpsとの相性が抜群
- SOPSのようなローカル鍵管理が不要

注意点:

- クラスタの秘密鍵を喪失すると **二度と復号できない**(必ずバックアップ)
- secret rotation の手順が必要

## External Secrets Operator (ESO)

Vault / AWS Secrets Manager / 1Password などから動的に取得して Secret に変換するオペレーター。
**真実の源泉を K8s 外** に置けるのが最大の利点。

```bash
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
```

### Vault を立てる (ローカル)

```bash
helm install vault hashicorp/vault \
  --set "server.dev.enabled=true" \
  -n vault --create-namespace
```

```bash
# Vault に Secret を入れる
kubectl exec -n vault vault-0 -- vault kv put secret/todo \
  DB_PASSWORD=supersecret JWT_SECRET=jwt-key
```

### SecretStore + ExternalSecret

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault
  namespace: prod
spec:
  provider:
    vault:
      server: "http://vault.vault.svc:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "todo-api"
          serviceAccountRef:
            name: "todo-api"
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: todo-secret
  namespace: prod
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault
    kind: SecretStore
  target:
    name: todo-secret
    creationPolicy: Owner
  data:
  - secretKey: DB_PASSWORD
    remoteRef:
      key: todo
      property: DB_PASSWORD
  - secretKey: JWT_SECRET
    remoteRef:
      key: todo
      property: JWT_SECRET
```

これだけで、

- Vault の値が更新されると、1 時間後に Secret も更新される
- Git にはシークレットの「**参照**」だけ残し、値は Vault が一元管理
- 監査ログで「誰がいつ取り出したか」が追える

本番運用ではこの形を推奨します。

## SOPS + age

ファイル単位で暗号化して Git に置けるツール。Helm Secrets や Kustomize 経由で使える。
GitOpsで「ファイルベースで完結したい」場合の選択肢。

```bash
sops --age=age1...  -e -i values-prod.yaml
helm secrets install todo ./todo -f values-prod.yaml
```

## 比較表

| 軸 | Sealed Secrets | SOPS | ESO + Vault |
|---|----|----|----|
| Git に置けるか | ✓ | ✓ | 参照のみ |
| 真実の源泉 | クラスタ秘密鍵 | ファイル | Vault |
| 値の rotate | 再暗号 + commit | 再暗号 + commit | Vault側で更新するだけ |
| 監査 | △ | △ | ◎ |
| 学習コスト | 低 | 中 | 高 |

## チェックポイント

- [ ] etcd暗号化を入れずに本番運用するとどうなるか
- [ ] Sealed Secrets と ESO の使い分け
- [ ] Vault + ESO を採用する利点を 3 つ
