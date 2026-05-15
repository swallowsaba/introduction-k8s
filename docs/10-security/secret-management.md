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

## このページのゴール

このページを読み終えると、以下を **自分の言葉で説明できる** ようになります。

- Kubernetes の `Secret` リソースの仕組み(なぜ base64 で、なぜそれが「暗号化ではない」のか)
- etcd 保存時暗号化 (Encryption at Rest, KMS v1/v2) の構成方法
- Sealed Secrets / SOPS+age の暗号化 GitOps パターンの違い
- HashiCorp Vault と External Secrets Operator(ESO)の連携アーキテクチャ
- CSI Secret Store Driver による「Secret を経由しない」シークレット注入
- cert-manager と連携した TLS 自動化
- Secret rotation 戦略(時間ベース・イベントベース)
- TODO アプリで Vault + ESO の本番相当構成を組める

---

## Secret は「暗号化」ではない

まず徹底的に誤解を解きます。

```bash
kubectl create secret generic demo --from-literal=password='hunter2'
kubectl get secret demo -o yaml
```

期待される出力:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: demo
  namespace: default
type: Opaque
data:
  password: aHVudGVyMg==
```

`aHVudGVyMg==` を見て「暗号化されている」と思った人は、明日からインシデント担当です。

```bash
echo 'aHVudGVyMg==' | base64 -d
# hunter2
```

**Base64 は単なる「バイナリを ASCII テキストにする符号化方式」** であり、暗号ではありません。
なぜ base64 を使うかというと、Secret の `data` フィールドが JSON/YAML として **任意のバイト列を運ぶ** ためで、改行や NUL や非 UTF-8 バイトを含むデータをそのまま埋め込めないからです(参考: `stringData` を使うと自動で base64 エンコードしてくれます)。

### Secret に何が起きているのか

| 場所 | 状態 |
|------|------|
| YAML マニフェスト | base64 エンコード(平文同然) |
| kube-apiserver の RAM | 平文 |
| etcd ディスク | **デフォルトでは平文**(暗号化未設定なら) |
| Pod の中(env / file) | 平文 |
| Pod の Volume(tmpfs)| 平文だがディスクには書かれない |
| kubectl get -o yaml | base64(平文同然) |

```mermaid
flowchart LR
    Y[YAML]:::plain --> A[kube-apiserver]:::plain
    A -- 暗号化なし --> E[(etcd)]:::danger
    A -- KMS plugin --> E2[(etcd 暗号化)]:::ok
    A --> KL[kubelet]:::plain
    KL --> Pod[Pod tmpfs]:::plain
    Pod --> App[アプリ env / file]:::plain

    classDef plain fill:#fdd,color:#000
    classDef danger fill:#f88,color:#000
    classDef ok fill:#dfd,color:#000
```

つまり Secret は **「アクセス制御」と「暗号化保管」を別途設定して初めて安全になる** リソースです。

### なぜ Kubernetes は Secret を独立リソースにしたのか

ConfigMap と分ける必要があるのか? と疑問に思った人もいるはず。実際、データ構造はほぼ同じです。

歴史的理由:

- **RBAC で別の verb を持てる** (`secrets/get` を分けて制限できる)
- **etcd 暗号化対象に Secret だけ含める** ことができる
- **kubectl で表示する際にデフォルトでマスク** される(`kubectl describe secret` は値を見せない)
- ノードの **kubelet が必要な Secret しか pull しない**(NodeRestriction admission)
- **メトリクス・監査ログでの扱いを分けられる**

逆に、ConfigMap と同じ運用にしてしまうと得られる利点が消えます。
**「Secret には RBAC で `get`/`list`/`watch` を狭く絞る」** が最重要原則。

---

## 背景: K8s Secret の歴史

### 2014: Secret 誕生時の素朴な設計

Kubernetes 0.6 (2014年) で Secret が登場。当時のクラスタは「**シングルクラスタ、信頼できる管理者のみが etcd を触る**」前提だったため、etcd への平文保管が許容されていました。

### 2017: Encryption at Rest (alpha → beta)

EncryptionConfiguration による「etcd 内 Secret の暗号化」が導入(KEP-92)。クラスタ管理者が AES key を設定ファイルで持ち、apiserver が読み書き時に暗号化/復号する仕組み。

### 2019: KMS Provider v1

外部 KMS(AWS KMS、GCP KMS、Vault Transit、HSM 等)に依存できる KMS v1 プラグインが GA。ローカル鍵を持たずに KMS で暗号化できるようになる。
ただし KMS v1 はパフォーマンス問題があり、**全 Secret 操作が KMS への gRPC 呼び出しになる** ため大規模クラスタで詰まる事例が多発。

### 2023〜: KMS v2 (v1.27 beta, v1.29 GA)

KEP-3299。**DEK(データ暗号化鍵) を apiserver がキャッシュ、KEK(鍵暗号化鍵) を KMS が管理** する 2 段階方式に進化。KMS への問い合わせ回数が劇的に減り、HA・パフォーマンス双方が改善。

### 2018〜: GitOps と「Secret を Git に置きたい」問題

ArgoCD / Flux などの GitOps が普及すると、「Secret も Git で宣言的管理したい」のニーズが生まれる。
しかし生の Secret YAML を Git に push すると公開と同じ。これを解決する 3 つのアプローチが出現:

1. **Sealed Secrets** (Bitnami, 2018〜): クラスタ内の鍵で暗号化、Git に置いて apply 時に復号
2. **SOPS** (Mozilla, 2017〜): GPG/age/KMS で暗号化したファイルを Git に、運用時に復号
3. **External Secrets Operator** (2020〜): Git には参照だけ、実体は Vault/Cloud KMS

### 2020〜: Secret CSI Driver

Pod の Volume として **Kubernetes Secret を経由せず** 直接 Vault や Cloud KMS から取得する仕組み。Secret リソース自体を作らないので etcd 暴露リスクすらゼロ。

```mermaid
timeline
    title K8s Secret 管理の進化
    2014 : Secret 誕生 (平文 etcd 保管)
    2017 : Encryption at Rest (beta)
    2018 : Sealed Secrets / SOPS
    2019 : KMS v1 GA
    2020 : Secret CSI Driver / External Secrets Operator
    2023 : KMS v2 (beta)
    2024 : KMS v2 GA (v1.29)
```

---

## Secret の基本操作

### 種類

| Type | 用途 |
|------|------|
| `Opaque` | 汎用(デフォルト) |
| `kubernetes.io/service-account-token` | SA トークン |
| `kubernetes.io/dockerconfigjson` | レジストリ認証 |
| `kubernetes.io/basic-auth` | username/password |
| `kubernetes.io/ssh-auth` | SSH 秘密鍵 |
| `kubernetes.io/tls` | TLS 証明書 + 秘密鍵 |
| `bootstrap.kubernetes.io/token` | kubeadm join トークン |

タイプは **任意の名前空間で自分でも作れる** (`type: my.company.com/license`)。読み書きは Opaque と同じ。

### 作り方バリエーション

```bash
# リテラル
kubectl create secret generic db-cred \
  --from-literal=username=todo \
  --from-literal=password='S3cr3t!'

# ファイルから
kubectl create secret generic ssl-cert \
  --from-file=tls.crt=server.crt \
  --from-file=tls.key=server.key

# .env 形式から一括
kubectl create secret generic app-env --from-env-file=app.env

# TLS タイプ
kubectl create secret tls api-tls \
  --cert=api.crt --key=api.key

# Docker registry
kubectl create secret docker-registry harbor-cred \
  --docker-server=harbor.example.com \
  --docker-username=robot \
  --docker-password='xxx' \
  --docker-email=ci@example.com
```

### stringData フィールド

YAML を手書きするとき、base64 を毎回計算するのは面倒。`stringData` を使うと **apiserver が自動で base64 化** してくれる(`data` と排他ではないが、同名は `stringData` が優先)。

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-config
stringData:
  database_url: "postgres://todo:secret@postgres:5432/todo"
  redis_url: "redis://redis:6379/0"
data:
  legacy.bin: aGVsbG8=   # こっちは base64
```

### immutable Secret(v1.21+)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: locked-cert
type: kubernetes.io/tls
data:
  tls.crt: ...
  tls.key: ...
immutable: true
```

- 編集不可になり、変更時は **削除 + 再作成** が必要
- apiserver が watch しなくてよくなり **メモリ消費が大幅減**
- 大規模クラスタで Secret を多数持つときの性能対策

### Pod への注入 4 方法

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    image: 192.168.56.10:5000/todo-api:0.1.0
    # 1) 環境変数(個別)
    env:
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: db-cred
          key: password
    # 2) 環境変数(まとめて)
    envFrom:
    - secretRef:
        name: app-env
        optional: true   # 無くてもエラーにしない
    # 3) Volume マウント(ファイル)
    volumeMounts:
    - name: tls
      mountPath: /etc/tls
      readOnly: true
  volumes:
  - name: tls
    secret:
      secretName: api-tls
      defaultMode: 0400
      items:
      - key: tls.crt
        path: server.crt
      - key: tls.key
        path: server.key
```

そして 4 つ目は **projected volume** で複数 Source を統合できます。

```yaml
  volumes:
  - name: app-secrets
    projected:
      defaultMode: 0400
      sources:
      - secret:
          name: db-cred
          items:
          - key: password
            path: db/password
      - secret:
          name: redis-cred
          items:
          - key: password
            path: redis/password
      - configMap:
          name: app-config
          items:
          - key: app.yaml
            path: app.yaml
```

### 環境変数 vs ファイルマウントどっちが安全?

| 観点 | env | ファイル |
|------|------|---------|
| プロセス /proc/<pid>/environ | **見える** | 見えない |
| `ps -e` で見える(設定次第) | 場合により | 見えない |
| 子プロセスへの継承 | される | されない |
| クラッシュダンプ含有 | 含まれることがある | 含まれない |
| Secret 更新の自動反映 | **されない**(Pod 再起動が必要) | **される**(kubelet が ~60s で更新) |

ベストプラクティス: **ファイルマウントを基本にする**。env を使うのはアプリの作りで仕方ない場合のみ。

---

## etcd 保存時暗号化(Encryption at Rest)

etcd ディスクが盗まれても Secret が露出しない仕組み。
kube-apiserver の `--encryption-provider-config` フラグでファイルを渡す。

### v1.30 (本教材) で推奨される構成

```yaml
# /etc/kubernetes/encryption/config.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources:
  - secrets
  providers:
  - aescbc:                    # 暗号化 (現行)
      keys:
      - name: key-2025
        secret: <base64 32byte>
  - identity: {}               # 復号フォールバック (平文)
```

| Provider | 内容 | 性能 | KMS |
|----------|------|------|-----|
| `identity` | 平文 (= 暗号化なし) | 最速 | - |
| `aescbc` | AES-CBC-256 | 高 | ローカル鍵 |
| `aesgcm` | AES-GCM-256 | 高(認証付き)、ローテーション必須 | ローカル鍵 |
| `secretbox` | XSalsa20+Poly1305 | 高 | ローカル鍵 |
| `kms` v1 | 外部 KMS gRPC | 中 | 外部 |
| `kms` v2 | 外部 KMS + DEK キャッシュ | 高 | 外部 |

```mermaid
flowchart LR
    Cli[kubectl] --> API[kube-apiserver]
    API -- 平文 --> CACHE[DEK キャッシュ]
    CACHE -- AES 暗号化 --> ETC[(etcd)]
    CACHE -. KEK 取得 .-> KMS[(外部 KMS)]

    style ETC fill:#fdd,color:#000
    style KMS fill:#dfd,color:#000
    style CACHE fill:#fc8,color:#000
```

### kubeadm クラスタで設定する手順

教材環境(k8s-cp1〜3, HA)で適用。**全 control plane で同じ設定** が必須(でないと別ノードで作った Secret が他で復号できない)。

#### 鍵生成

```bash
head -c 32 /dev/urandom | base64
# eRVhB2u1Yo+xL...  (これを secret に貼る)
```

#### 設定ファイル配置

各 cp ノードで:

```bash
sudo mkdir -p /etc/kubernetes/encryption
sudo tee /etc/kubernetes/encryption/config.yaml >/dev/null <<EOF
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources:
  - secrets
  providers:
  - aescbc:
      keys:
      - name: key-2025-01
        secret: eRVhB2u1Yo+xL...
  - identity: {}
EOF
sudo chmod 600 /etc/kubernetes/encryption/config.yaml
```

#### kube-apiserver マニフェスト編集

`/etc/kubernetes/manifests/kube-apiserver.yaml` を編集:

```yaml
spec:
  containers:
  - command:
    - kube-apiserver
    - --encryption-provider-config=/etc/kubernetes/encryption/config.yaml
    # 既存フラグ群...
    volumeMounts:
    - name: enc
      mountPath: /etc/kubernetes/encryption
      readOnly: true
  volumes:
  - name: enc
    hostPath:
      path: /etc/kubernetes/encryption
      type: Directory
```

kubelet が manifest 変更を検知して自動で apiserver を再起動。

#### 既存 Secret の再暗号化

設定変更は **新しく書かれるものにのみ適用** されます。既存 Secret を再暗号化:

```bash
kubectl get secrets -A -o json | kubectl replace -f -
```

各 Secret が write される → 新しい provider で暗号化される。

#### etcd を直接覗いて確認

k8s-cp1 で:

```bash
sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  get /registry/secrets/default/demo \
  | hexdump -C | head
```

暗号化前:

```
00000000  /registry/secrets/default/demo
00000020  k8s\x00\x0a\x0c\n\x02v1\x12\x06Secret...
       (平文の YAML が見える)
```

暗号化後:

```
00000000  /registry/secrets/default/demo
00000020  k8s:enc:aescbc:v1:key-2025-01:
       (以降ランダムバイト)
```

`k8s:enc:aescbc:v1:key-2025-01:` というプレフィックスが入ります。

### 鍵ローテーション

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources:
  - secrets
  providers:
  - aescbc:
      keys:
      - name: key-2025-04   # 新キー (書き込みはこれで)
        secret: <new>
      - name: key-2025-01   # 旧キー (復号用)
        secret: <old>
  - identity: {}
```

順序:

1. 新キーを **2 番目** に追加して deploy (読みのフォールバックとして用意)
2. 全 cp に行き渡ったら **新キーを 1 番目** に並べ替え (書き込みが新キーに)
3. 全 Secret を `kubectl replace` で再暗号化
4. 旧キーを削除
5. 全 Secret を `kubectl replace` で書き直し(safe)
6. 全 cp 再起動

これは半年〜年 1 回のローテーション運用が推奨。

### KMS v2 で外部 KMS 連携(発展)

Vault Transit と組み合わせる例(コンセプト):

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources:
  - secrets
  providers:
  - kms:
      apiVersion: v2       # v1.29+
      name: vault-kms
      endpoint: unix:///opt/kms/sockets/vault-kms.sock
      timeout: 3s
  - identity: {}
```

ローカルに `vault-kms-plugin` (gRPC サーバ) を立て、apiserver が UNIX socket 経由で KMS 操作を依頼。DEK は apiserver がキャッシュし、KEK は Vault に。

```mermaid
sequenceDiagram
    participant Client as kubectl
    participant API as kube-apiserver
    participant Plugin as vault-kms-plugin
    participant Vault as Vault Transit
    participant Etcd as etcd
    Client->>API: create secret (plaintext)
    API->>API: DEK をローカル生成 (or キャッシュ)
    alt DEK 未暗号化
        API->>Plugin: encrypt(DEK)
        Plugin->>Vault: transit encrypt
        Vault-->>Plugin: ciphertext
        Plugin-->>API: encrypted DEK
    end
    API->>API: secret を DEK で AES 暗号化
    API->>Etcd: PUT {encrypted_data, encrypted_DEK}
    Etcd-->>API: OK
    API-->>Client: 201 Created
```

教材環境で本格運用するのは要件が大きいので、本書では **AES-CBC + ローカル鍵** までを必須、KMS v2 は概念理解までにとどめます。

### `kubectl get --raw` で暗号化を確認するテクニック

apiserver は復号して返すので、`kubectl` 経由では分かりません。
唯一信用できるのは **etcd を直接覗くこと**(上の hexdump)。
監査用に **etcd dump** を取って periodically 検証する CI を組む組織もあります。

---

## Secret を Git に置きたい (GitOps)

平文 Secret を Git に置けないので、暗号化済みオブジェクトを置く 3 方式を比較。

| 方式 | 暗号化主体 | 復号場所 | 鍵管理 |
|------|----------|---------|--------|
| Sealed Secrets | クラスタ内 controller の公開鍵で | クラスタ内 controller | controller の秘密鍵(クラスタ依存) |
| SOPS+age | 開発者 / CI の鍵 | デプロイ時 (kustomize 等) | age key を 1Password 等で配布 |
| ESO + Vault | Vault に既に保管 | クラスタ内 ESO が pull | Vault 側 |

```mermaid
flowchart TB
    subgraph Sealed["Sealed Secrets"]
        SC1[平文]-->SC2[kubeseal で暗号化]
        SC2-->SC3[Git に push]
        SC3-->SC4[Apply]
        SC4-->SC5[controller が復号→Secret 作成]
    end
    subgraph SOPS["SOPS + age"]
        SO1[平文]-->SO2[sops で暗号化]
        SO2-->SO3[Git に push]
        SO3-->SO4[kustomize secret-generator]
        SO4-->SO5[Apply 時に復号→Secret 作成]
    end
    subgraph ESO["External Secrets Operator"]
        E1[Vault に保管]
        E2[Git: ExternalSecret 参照のみ]
        E2-->E3[Apply]
        E3-->E4[ESO controller が Vault から pull]
        E4-->E5[Secret 作成]
        E1-.->E4
    end

    style SC5 fill:#dfd,color:#000
    style SO5 fill:#dfd,color:#000
    style E5 fill:#dfd,color:#000
```

### 1. Sealed Secrets(Bitnami)

クラスタ内に controller を 1 つ置き、その公開鍵で暗号化した SealedSecret CRD を Git に置く方式。

#### インストール

```bash
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace kube-system --create-namespace
```

#### CLI 取得

```bash
KUBESEAL_VERSION='0.27.0'
wget "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${KUBESEAL_VERSION}/kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz"
tar -xzf kubeseal-0.27.0-linux-amd64.tar.gz kubeseal
sudo install -m 755 kubeseal /usr/local/bin/kubeseal
```

#### 暗号化

```bash
kubectl create secret generic db-cred \
  --from-literal=password='S3cr3t!' \
  --dry-run=client -o yaml | kubeseal -o yaml > db-cred-sealed.yaml
```

出力 `db-cred-sealed.yaml`:

```yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: db-cred
  namespace: prod
spec:
  encryptedData:
    password: AgB+8a3...(長い base64)
  template:
    metadata:
      name: db-cred
      namespace: prod
    type: Opaque
```

これを Git に commit して push。

#### apply で復号

```bash
kubectl apply -f db-cred-sealed.yaml
# sealedsecret.bitnami.com/db-cred created

# 自動で Secret が生成される
kubectl get secret db-cred -n prod
# NAME      TYPE     DATA   AGE
# db-cred   Opaque   1      5s
```

#### スコープ

SealedSecret には 3 つのスコープ:

| スコープ | 意味 | 暗号化時のフラグ |
|----------|------|------|
| `strict`(デフォルト) | 同じ名前空間・同じ名前でしか復号できない | (なし) |
| `namespace-wide` | 同じ名前空間内なら名前変更可 | `--scope namespace-wide` |
| `cluster-wide` | クラスタ全体で復号可能 | `--scope cluster-wide` |

`strict` がデフォルト。名前を変えると復号できなくなるので、コピペで再利用する場合は注意。

#### バックアップが重要

Sealed Secrets は **controller の秘密鍵で復号** します。クラスタを作り直すと過去の SealedSecret が全部復号不能に。

```bash
# 鍵バックアップ (運用必須)
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
  -o yaml > sealed-secrets-key.backup.yaml
# これを 1Password 等に保管
```

新クラスタ復元時:

```bash
kubectl apply -f sealed-secrets-key.backup.yaml
kubectl rollout restart deployment sealed-secrets -n kube-system
```

#### 鍵ローテーション

controller はデフォルトで 30 日ごとに新しい鍵を生成。古い鍵も保持して復号できるので、過去の SealedSecret は引き続き使える。
ただし **マニフェストを再暗号化** するべき:

```bash
kubeseal --re-encrypt < db-cred-sealed.yaml > db-cred-sealed-new.yaml
```

### 2. SOPS + age(Mozilla SOPS)

ファイル全体を編集可能なまま暗号化(YAML の値部分だけが暗号化、key 名は平文)。

#### age とは

curve25519 ベースの軽量公開鍵暗号。GPG より圧倒的にシンプル。

```bash
# age インストール (Ubuntu)
sudo apt install age

# 鍵生成
age-keygen -o key.txt
# Public key: age1qpkxxxx...
```

#### sops インストール

```bash
SOPS_VERSION=3.9.0
wget https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64
chmod +x sops-v3.9.0.linux.amd64
sudo mv sops-v3.9.0.linux.amd64 /usr/local/bin/sops
```

#### `.sops.yaml`(リポジトリ直下)

```yaml
creation_rules:
- path_regex: '.*\.enc\.ya?ml$'
  encrypted_regex: '^(data|stringData)$'
  age: age1qpkxxxx...
```

`encrypted_regex` で「**`data` と `stringData` フィールドだけ暗号化**」を指定。これで diff が読めるまま秘匿可能。

#### 暗号化

```yaml
# secret.yaml (平文)
apiVersion: v1
kind: Secret
metadata:
  name: db-cred
  namespace: prod
stringData:
  password: S3cr3t!
```

```bash
sops -e secret.yaml > secret.enc.yaml
git add secret.enc.yaml
```

`secret.enc.yaml` の中身(抜粋):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-cred
  namespace: prod
stringData:
  password: ENC[AES256_GCM,data:hF8b...,iv:...,tag:...]
sops:
  age:
  - recipient: age1qpkxxxx...
    enc: |
      -----BEGIN AGE ENCRYPTED FILE-----
      ...
      -----END AGE ENCRYPTED FILE-----
```

#### 復号(運用時)

```bash
export SOPS_AGE_KEY_FILE=/path/to/key.txt
sops -d secret.enc.yaml | kubectl apply -f -
```

#### kustomize と連携

```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
generators:
- generator.yaml
```

```yaml
# generator.yaml
apiVersion: viaduct.ai/v1
kind: ksops
metadata:
  name: db-cred-generator
files:
- secret.enc.yaml
```

ArgoCD や Flux で kustomize の前処理として SOPS を統合できる(`viaduct-ai/ksops`)。

### 3. External Secrets Operator(本書のメイン)

ESO は **Git には参照だけを置き、実体は外部 Secret Manager (Vault / AWS Secrets Manager / GCP / Azure / 1Password 等)** からクラスタ内 Secret を生成するオペレータ。

#### 推奨される理由

| メリット | 内容 |
|---------|------|
| Single Source of Truth | シークレットの正本は Vault などに 1 つ |
| 多クラスタ対応 | 同じ Vault から複数クラスタが取得可能 |
| 自動 rotation | Vault で更新 → 自動で Secret 更新(再 Pod 起動付き) |
| 既存資産を活用 | 既に Vault や AWS SM がある組織は移行が楽 |
| 監査ログが集中 | Vault のログで「誰がいつ Secret を読んだか」追跡 |

#### Provider 一覧(主要)

```mermaid
flowchart LR
    ESO[External Secrets Operator]
    ESO --> V[HashiCorp Vault]
    ESO --> AWS[AWS Secrets Manager]
    ESO --> AWSPS[AWS Parameter Store]
    ESO --> GCP[GCP Secret Manager]
    ESO --> AZ[Azure Key Vault]
    ESO --> OP[1Password Connect]
    ESO --> GitLab[GitLab Project Variables]
    ESO --> Kube[Kubernetes Secret as Provider<br/>クラスタ間複製]
    ESO --> Doppler[Doppler]
    ESO --> AKEY[Akeyless]
    ESO --> Web[Webhook (汎用)]

    style ESO fill:#fc8,color:#000
```

教材では Vault を使うが、Provider を差し替えるだけで他にも応用可能。

---

## HashiCorp Vault 連携

ESO の Provider として最も使われる Vault のセットアップから。

### Vault の基本

| 概念 | 内容 |
|------|------|
| seal / unseal | Vault は起動時に "sealed" 状態。3-of-5 のキーシェアで unseal が必要 |
| root token | 全権限の初期トークン。本番では破棄推奨 |
| Secret Engine | kv / database / pki / transit など、Secret を提供するモジュール |
| Auth Method | userpass / approle / kubernetes / oidc / aws / jwt など |
| Policy | HCL で書く権限定義(path に対する capabilities) |

### クラスタ内に Vault を立てる(HA)

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault \
  -n vault --create-namespace \
  --set='server.ha.enabled=true' \
  --set='server.ha.raft.enabled=true' \
  --set='server.ha.replicas=3' \
  --set='server.dataStorage.storageClass=nfs-csi' \
  --set='server.dataStorage.size=10Gi'
```

期待される結果:

```bash
kubectl get pods -n vault
# NAME                                    READY   STATUS    RESTARTS   AGE
# vault-0                                 0/1     Running   0          1m
# vault-1                                 0/1     Running   0          1m
# vault-2                                 0/1     Running   0          1m
# vault-agent-injector-xxx                1/1     Running   0          1m
```

READY 0/1 なのは sealed 状態だから(正常)。

### 初期化と unseal

```bash
kubectl exec -n vault vault-0 -- vault operator init \
  -key-shares=5 -key-threshold=3 -format=json > vault-keys.json

cat vault-keys.json | jq -r '.unseal_keys_b64[]'
# (5 個の鍵が出る。安全な場所に保管)

cat vault-keys.json | jq -r '.root_token'
# (root token)
```

これは **1 度だけしか取れない**。`vault-keys.json` を 1Password 等にバックアップ。
**5 つの鍵を 5 人に分けて配るのが本来の運用**(SSS 方式)。

unseal:

```bash
for i in 0 1 2; do
  for j in 0 1 2; do
    kubectl exec -n vault vault-$i -- vault operator unseal $(jq -r ".unseal_keys_b64[$j]" vault-keys.json)
  done
done
```

```bash
kubectl get pods -n vault
# vault-0   1/1   Running   0   3m
# vault-1   1/1   Running   0   3m
# vault-2   1/1   Running   0   3m
```

### Raft クラスタ確認

```bash
kubectl exec -n vault vault-0 -- vault operator raft list-peers
# Node          Address             State      Voter
# ----          -------             -----      -----
# vault-0       vault-0.vault.../   leader     true
# vault-1       vault-1.vault.../   follower   true
# vault-2       vault-2.vault.../   follower   true
```

### kv v2 Secret Engine の有効化

```bash
kubectl exec -n vault vault-0 -- /bin/sh -c '
  export VAULT_TOKEN='$(jq -r .root_token vault-keys.json)'
  vault secrets enable -version=2 -path=secret kv
  vault kv put secret/todo/db username=todo password=S3cr3t!
  vault kv put secret/todo/redis password=R3disP@ss
'
```

確認:

```bash
kubectl exec -n vault vault-0 -- /bin/sh -c '
  export VAULT_TOKEN='$(jq -r .root_token vault-keys.json)'
  vault kv get secret/todo/db
'
# === Secret Path ===
# secret/data/todo/db
# 
# === Data ===
# Key         Value
# ---         -----
# password    S3cr3t!
# username    todo
```

### Kubernetes 認証メソッドの有効化

Vault が k8s SA トークンを検証して「この SA に kv 読ませて良い」と判断するための連携。

```bash
kubectl exec -n vault vault-0 -- /bin/sh -c '
  export VAULT_TOKEN='$(jq -r .root_token vault-keys.json)'
  vault auth enable kubernetes
  vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443"
'
```

### Policy 定義

```bash
kubectl exec -i -n vault vault-0 -- /bin/sh -c '
  export VAULT_TOKEN='$(jq -r .root_token vault-keys.json)'
  vault policy write todo-read - <<EOF
path "secret/data/todo/*" {
  capabilities = ["read"]
}
path "secret/metadata/todo/*" {
  capabilities = ["read", "list"]
}
EOF
'
```

### Vault Role 作成(SA とのバインド)

ESO が使う SA `external-secrets` (`external-secrets` namespace) に `todo-read` ポリシーを付与:

```bash
kubectl exec -n vault vault-0 -- /bin/sh -c '
  export VAULT_TOKEN='$(jq -r .root_token vault-keys.json)'
  vault write auth/kubernetes/role/todo-eso \
    bound_service_account_names=external-secrets \
    bound_service_account_namespaces=external-secrets \
    policies=todo-read \
    ttl=1h
'
```

---

## External Secrets Operator(ESO)導入

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace \
  --set installCRDs=true \
  --set replicaCount=3
```

```bash
kubectl get pods -n external-secrets
# NAME                                  READY   STATUS    RESTARTS   AGE
# external-secrets-xxx                  1/1     Running   0          1m
# external-secrets-cert-controller-xxx  1/1     Running   0          1m
# external-secrets-webhook-xxx          1/1     Running   0          1m
```

### SecretStore 定義(名前空間スコープ)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-store
  namespace: prod
spec:
  provider:
    vault:
      server: "http://vault.vault.svc.cluster.local:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "todo-eso"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

### ExternalSecret 定義

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: todo-db-cred
  namespace: prod
spec:
  refreshInterval: 1m         # 1 分ごとに Vault から取得
  secretStoreRef:
    name: vault-store
    kind: SecretStore
  target:
    name: todo-db-cred         # 作る Secret の名前
    creationPolicy: Owner
    deletionPolicy: Delete
    template:
      type: Opaque
      metadata:
        annotations:
          managed-by: external-secrets
      data:
        # アプリが欲しい形に整形
        DATABASE_URL: "postgres://{{ .username }}:{{ .password }}@postgres:5432/todo?sslmode=require"
  data:
  - secretKey: username
    remoteRef:
      key: todo/db
      property: username
  - secretKey: password
    remoteRef:
      key: todo/db
      property: password
```

ポイント:

- `data` で Vault のキーごとに取り、`template` で **アプリ向けの DATABASE_URL** に整形
- Vault 側で `password` が変わると 1 分以内に Secret に反映
- そのままだと Pod の env は更新されないので、後述の **reloader** で連動

```bash
kubectl apply -f todo-db-externalsecret.yaml
kubectl get externalsecret -n prod
# NAME           STORE          REFRESH INTERVAL   STATUS         READY
# todo-db-cred   vault-store    1m                 SecretSynced   True

kubectl get secret todo-db-cred -n prod -o yaml
```

### ClusterSecretStore(クラスタ全体共有)

複数 Namespace で同じ Vault を使うなら ClusterSecretStore 1 つで済む。

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-shared
spec:
  provider:
    vault:
      server: "http://vault.vault.svc.cluster.local:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "todo-eso"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

### PushSecret(逆方向)

Kubernetes Secret を **Vault に書き戻したい** ケース(自動生成された証明書など)もある。

```yaml
apiVersion: external-secrets.io/v1alpha1
kind: PushSecret
metadata:
  name: backup-tls-to-vault
  namespace: prod
spec:
  refreshInterval: 10s
  secretStoreRefs:
  - name: vault-store
    kind: SecretStore
  selector:
    secret:
      name: api-tls
  data:
  - match:
      secretKey: tls.crt
      remoteRef:
        remoteKey: backup/api/tls-crt
```

クラスタ内で生成された値の Vault バックアップに使える。

---

## CSI Secret Store Driver

Pod の Volume に **Secret リソースを経由せず**、直接 Vault などから取得した値をマウントする仕組み。
Secret CSI Driver + Provider plugin の組合せ。

### なぜ CSI?

ESO は最終的に Secret リソースを etcd に書きます。万一 etcd 暗号化が無いと平文露出のリスク。
CSI は **Pod 起動時に provider から直接 tmpfs にマウント** するので、etcd を一切経由しません。

### インストール

```bash
helm repo add secrets-store-csi-driver https://kubernetes-sigs.github.io/secrets-store-csi-driver/charts
helm install csi-secrets-store \
  secrets-store-csi-driver/secrets-store-csi-driver \
  -n kube-system \
  --set syncSecret.enabled=true   # 任意で K8s Secret に sync も可

# Vault Provider plugin
helm install vault-csi-provider hashicorp/vault \
  -n vault --reuse-values \
  --set "csi.enabled=true"
```

### SecretProviderClass 定義

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: todo-db-spc
  namespace: prod
spec:
  provider: vault
  parameters:
    vaultAddress: "http://vault.vault:8200"
    roleName: "todo-eso"
    objects: |
      - objectName: "db-password"
        secretPath: "secret/data/todo/db"
        secretKey: "password"
      - objectName: "db-username"
        secretPath: "secret/data/todo/db"
        secretKey: "username"
```

### Pod 側

```yaml
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: todo-api
  containers:
  - name: api
    image: 192.168.56.10:5000/todo-api:0.1.0
    volumeMounts:
    - name: secrets
      mountPath: "/mnt/secrets"
      readOnly: true
  volumes:
  - name: secrets
    csi:
      driver: secrets-store.csi.k8s.io
      readOnly: true
      volumeAttributes:
        secretProviderClass: "todo-db-spc"
```

Pod 起動後、`/mnt/secrets/db-password` のファイルとして読める。Secret リソースは作られない。

### ESO + CSI どっち使う?

| 観点 | ESO | CSI Secret Store |
|------|-----|------------------|
| 環境変数として使える | ◎(普通の Secret なので env 注入) | △(`syncSecret` で K8s Secret も作るオプションはある) |
| etcd 経由 | する(暗号化推奨) | しない |
| 再 mount 自動更新 | Secret は更新、Pod は別途 reloader 必要 | rotation 機能で更新 |
| 設定の量 | 比較的少 | やや多 |
| 適合シーン | 普通の k8s 環境、コンテナの慣習に従う | 高いコンプライアンス要求環境 |

教材は **ESO を主、CSI は補足** 扱いとします。

---

## Secret rotation 戦略

Secret は「作って終わり」ではなく **定期的にローテーション** するもの。
パターン:

### 1. 時間ベース(定期 rotation)

- 30 日 / 90 日ごとにアプリ用 DB パスワードを再生成
- Vault の `database` Secret Engine を使えば **動的に PostgreSQL ロールを発行** できる(動的シークレット)
- TTL を 24 時間にして、ESO が refresh interval で取り直す

```hcl
# Vault 設定
vault secrets enable database
vault write database/config/todo-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles="todo-read,todo-write" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/todo?sslmode=disable" \
  username="admin" password="adminpass"

vault write database/roles/todo-write \
  db_name=todo-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';
    GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl="24h" max_ttl="72h"
```

ESO 側:

```yaml
spec:
  refreshInterval: 30m
  data:
  - secretKey: username
    remoteRef:
      key: database/creds/todo-write
      property: username
  - secretKey: password
    remoteRef:
      key: database/creds/todo-write
      property: password
```

これで **24 時間ごとに DB ユーザ自体が変わる**。漏洩しても影響時間が短い。

### 2. イベントベース

- 退職者発生 → 関連 Secret 即時失効
- インシデント検知 → 自動 rotation

Vault では `vault lease revoke -prefix database/creds/todo-write` で **全インスタンスを一括失効** できる。

### 3. Reloader で Pod 再起動

Secret/ConfigMap が更新されても、Pod の env は変わりません(volume はファイルが置き換わるが、アプリが読み直すかは別問題)。

Stakater Reloader を使うと、annotation で連動できる:

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm install reloader stakater/reloader -n reloader --create-namespace
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
  annotations:
    reloader.stakater.com/auto: "true"
    # または特定の secret/configmap だけ:
    # secret.reloader.stakater.com/reload: "todo-db-cred"
```

Secret 更新を検知して Deployment の rolling update を発動。

```mermaid
sequenceDiagram
    participant V as Vault
    participant E as ESO
    participant S as Secret
    participant R as Reloader
    participant D as Deployment
    Note over V: 管理者が password 変更
    E->>V: GET /v1/secret/data/todo/db
    V-->>E: 新しい値
    E->>S: kubectl patch secret
    R->>S: watch detected change
    R->>D: patch annotation (force restart)
    D->>D: rolling update
    Note over D: 新しい Pod は新パスワードを取得
```

---

## cert-manager 連携(TLS 証明書管理)

TLS 証明書も「Secret の一種」。手作業で更新するのは限界があるので、cert-manager に任せる。

### インストール

```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  -n cert-manager --create-namespace \
  --set installCRDs=true \
  --set replicaCount=2
```

### ClusterIssuer(社内 CA を使う例)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: internal-ca
spec:
  ca:
    secretName: internal-ca-key-pair
---
apiVersion: v1
kind: Secret
metadata:
  name: internal-ca-key-pair
  namespace: cert-manager
type: Opaque
data:
  tls.crt: <base64>
  tls.key: <base64>
```

### Certificate リソース

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: todo-api-tls
  namespace: prod
spec:
  secretName: todo-api-tls
  duration: 2160h        # 90 日
  renewBefore: 360h      # 15 日前に更新
  subject:
    organizations: [example]
  commonName: api.todo.svc.cluster.local
  dnsNames:
  - api.todo.svc.cluster.local
  - todo-api.prod.svc.cluster.local
  issuerRef:
    name: internal-ca
    kind: ClusterIssuer
```

cert-manager は内部で:

1. 秘密鍵を生成
2. CSR(証明書署名要求)を作って Issuer に送る
3. CA が署名して証明書を返す
4. `secret/todo-api-tls` を作成(`type: kubernetes.io/tls`)
5. `renewBefore` 前になったら自動更新

### Let's Encrypt 連携(クラスタが外向きの場合)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
    - dns01:
        cloudflare:
          email: ops@example.com
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
```

### trust-manager で CA を配る

cert-manager の姉妹プロジェクト trust-manager で、CA 証明書を全 Pod に同期できる:

```yaml
apiVersion: trust.cert-manager.io/v1alpha1
kind: Bundle
metadata:
  name: internal-cas
spec:
  sources:
  - useDefaultCAs: true
  - secret:
      name: internal-ca-key-pair
      key: tls.crt
  target:
    configMap:
      key: ca-bundle.pem
    namespaceSelector:
      matchLabels: {trust: "yes"}
```

ラベル付きの Namespace に ConfigMap として配布。

---

## ハンズオン: TODO アプリの本番相当 Secret 構成

ここまでの要素を統合し、Vault + ESO + cert-manager + Reloader で本番品質の構成を組みます。

### 全体図

```mermaid
flowchart TB
    subgraph Source["ソース管理"]
        Git[Git: ExternalSecret マニフェスト]
    end
    subgraph Cluster["クラスタ"]
        ETCD[(etcd<br/>AES-CBC 暗号化)]
        Vault[(Vault HA<br/>kv v2 / database)]
        ESO[ESO controller]
        CM[cert-manager]
        Rel[Reloader]
        SC[SecretStore]
        ES[ExternalSecret]
        Cert[Certificate]
        Sec[Secret todo-db-cred]
        TLS[Secret todo-api-tls]
        Dep[Deployment todo-api]
    end
    Git --> ES
    Git --> SC
    Git --> Cert
    SC --> ESO
    ES --> ESO
    ESO -->|fetch| Vault
    ESO --> Sec
    Cert --> CM
    CM --> TLS
    Sec --> Dep
    TLS --> Dep
    Rel -->|annotation watch| Sec
    Rel -->|annotation watch| TLS
    Rel -->|trigger rollout| Dep
    Dep --> ETCD

    style Vault fill:#dfd,color:#000
    style ETCD fill:#fc8,color:#000
    style ESO fill:#cef,color:#000
    style CM fill:#cef,color:#000
    style Rel fill:#cef,color:#000
```

### 前提

- 既に etcd 暗号化を設定済み (本ページ前半)
- Vault HA を `vault` namespace に展開済み
- ESO を `external-secrets` namespace に展開済み
- cert-manager を `cert-manager` namespace に展開済み
- Reloader を `reloader` namespace に展開済み

### 手順 1: Vault に Secret を投入

```bash
ROOT_TOKEN=$(jq -r .root_token vault-keys.json)
kubectl exec -n vault vault-0 -- /bin/sh -c "
  export VAULT_TOKEN=$ROOT_TOKEN
  vault kv put secret/todo/db username=todo password='S3cr3tDB!'
  vault kv put secret/todo/redis password='R3disP@ss!'
  vault kv put secret/todo/notification webhook-url='https://hooks.slack.com/...'
"
```

### 手順 2: Kubernetes 認証 Role(prod 用)

```bash
kubectl exec -n vault vault-0 -- /bin/sh -c "
  export VAULT_TOKEN=$ROOT_TOKEN
  vault policy write todo-prod-read - <<'EOF'
path \"secret/data/todo/*\" { capabilities = [\"read\"] }
path \"secret/metadata/todo/*\" { capabilities = [\"read\", \"list\"] }
EOF
  vault write auth/kubernetes/role/todo-prod \
    bound_service_account_names=external-secrets \
    bound_service_account_namespaces=external-secrets \
    policies=todo-prod-read ttl=1h
"
```

### 手順 3: ClusterSecretStore

```yaml
# k8s/vault-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-prod
spec:
  provider:
    vault:
      server: "http://vault.vault.svc.cluster.local:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "todo-prod"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

```bash
kubectl apply -f k8s/vault-store.yaml
```

### 手順 4: ExternalSecret 3 種

```yaml
# k8s/todo-secrets.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: todo-db
  namespace: prod
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: vault-prod
    kind: ClusterSecretStore
  target:
    name: todo-db-cred
    creationPolicy: Owner
    template:
      type: Opaque
      data:
        DATABASE_URL: "postgres://{{ .username }}:{{ .password }}@postgres.prod:5432/todo?sslmode=require"
  data:
  - secretKey: username
    remoteRef: {key: todo/db, property: username}
  - secretKey: password
    remoteRef: {key: todo/db, property: password}
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: todo-redis
  namespace: prod
spec:
  refreshInterval: 1m
  secretStoreRef: {name: vault-prod, kind: ClusterSecretStore}
  target:
    name: todo-redis-cred
    template:
      type: Opaque
      data:
        REDIS_URL: "redis://:{{ .password }}@redis.prod:6379/0"
  data:
  - secretKey: password
    remoteRef: {key: todo/redis, property: password}
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: todo-notification
  namespace: prod
spec:
  refreshInterval: 5m
  secretStoreRef: {name: vault-prod, kind: ClusterSecretStore}
  target:
    name: todo-notification-cred
  data:
  - secretKey: SLACK_WEBHOOK_URL
    remoteRef: {key: todo/notification, property: webhook-url}
```

### 手順 5: TLS 証明書

```yaml
# k8s/todo-tls.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: todo-api-tls
  namespace: prod
spec:
  secretName: todo-api-tls
  duration: 2160h
  renewBefore: 360h
  commonName: todo-api.prod.svc.cluster.local
  dnsNames:
  - todo-api.prod.svc.cluster.local
  - api.todo.internal
  issuerRef:
    name: internal-ca
    kind: ClusterIssuer
```

### 手順 6: Deployment(全部参照)

```yaml
# k8s/todo-api.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
  namespace: prod
  annotations:
    reloader.stakater.com/auto: "true"   # Reloader 連携
spec:
  replicas: 3
  selector:
    matchLabels: {app: todo-api}
  template:
    metadata:
      labels: {app: todo-api}
    spec:
      serviceAccountName: todo-api
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        fsGroup: 65532
        seccompProfile: {type: RuntimeDefault}
      containers:
      - name: api
        image: 192.168.56.10:5000/todo-api@sha256:abcd...   # digest 固定
        imagePullPolicy: IfNotPresent
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities: {drop: [ALL]}
        envFrom:
        - secretRef: {name: todo-db-cred}
        - secretRef: {name: todo-redis-cred}
        - secretRef: {name: todo-notification-cred}
        env:
        - name: TLS_CERT_PATH
          value: /etc/tls/tls.crt
        - name: TLS_KEY_PATH
          value: /etc/tls/tls.key
        volumeMounts:
        - name: tls
          mountPath: /etc/tls
          readOnly: true
        - name: tmp
          mountPath: /tmp
        resources:
          requests: {cpu: 100m, memory: 128Mi}
          limits: {cpu: 500m, memory: 256Mi}
        readinessProbe:
          httpGet: {path: /healthz, port: 8000, scheme: HTTPS}
      volumes:
      - name: tls
        secret:
          secretName: todo-api-tls
          defaultMode: 0400
      - name: tmp
        emptyDir: {medium: Memory, sizeLimit: 16Mi}
```

### 手順 7: 適用と確認

```bash
kubectl apply -f k8s/vault-store.yaml
kubectl apply -f k8s/todo-secrets.yaml
kubectl apply -f k8s/todo-tls.yaml
kubectl apply -f k8s/todo-api.yaml

kubectl get externalsecret -n prod
# NAME                STORE        REFRESH INTERVAL   STATUS         READY
# todo-db             vault-prod   1m                 SecretSynced   True
# todo-redis          vault-prod   1m                 SecretSynced   True
# todo-notification   vault-prod   5m                 SecretSynced   True

kubectl get certificate -n prod
# NAME           READY   SECRET         AGE
# todo-api-tls   True    todo-api-tls   1m

kubectl get secret -n prod
# todo-db-cred              Opaque             3
# todo-redis-cred           Opaque             1
# todo-notification-cred    Opaque             1
# todo-api-tls              kubernetes.io/tls  2
```

### 手順 8: rotation の動作確認

```bash
# Vault でパスワード変更
kubectl exec -n vault vault-0 -- /bin/sh -c "
  export VAULT_TOKEN=$ROOT_TOKEN
  vault kv put secret/todo/db username=todo password='N3wP@ss!'
"

# 1 分待つと Secret が更新される
kubectl get secret todo-db-cred -n prod -o jsonpath='{.data.password}' | base64 -d
# N3wP@ss!

# Reloader が検知して Deployment を rolling restart
kubectl rollout status deployment/todo-api -n prod
# deployment "todo-api" successfully rolled out
```

これで「**Vault の値を変えるだけで本番アプリのパスワードが切り替わる**」が動きました。

### 手順 9: 監査・観測

ESO は Prometheus メトリクス を吐く:

```
externalsecret_sync_calls_total{name="todo-db"} 60
externalsecret_sync_calls_error{name="todo-db"} 0
externalsecret_status_condition{name="todo-db", condition="Ready", status="True"} 1
```

Vault のログでは「いつどの SA が読みに来たか」追跡可能(audit device 有効化):

```bash
kubectl exec -n vault vault-0 -- vault audit enable file file_path=stdout
```

---

## トラブル事例集

### 症状: ExternalSecret が SecretSyncedError

```bash
kubectl describe externalsecret todo-db -n prod
# Status:
#   Conditions:
#     Reason:                SecretSyncedError
#     Message:               could not get secret data from provider: ... permission denied
```

原因切り分け:

```mermaid
flowchart TD
    A[SecretSyncedError] --> B{kubectl describe<br/>Message を確認}
    B --> C{エラー種別}
    C -- "permission denied" --> D[Vault Policy 不一致<br/>→ vault policy read]
    C -- "no auth method" --> E[k8s auth 未有効<br/>→ vault auth list]
    C -- "service account not in role" --> F[bound_service_account_names<br/>確認]
    C -- "token signature invalid" --> G[Vault が apiserver の<br/>JWT 発行者を検証できない<br/>→ kubernetes_host 設定]
    C -- "connection refused" --> H[Vault sealed/down<br/>→ kubectl get pods -n vault]
    C -- "namespace mismatch" --> I[ClusterSecretStore か<br/>SecretStore か再確認]

    style C fill:#fc8,color:#000
```

### 症状: Pod が起動するが Secret が見つからない

```
Pending: secret "todo-db-cred" not found
```

- ExternalSecret がまだ同期されていない
- 名前空間が違う
- ExternalSecret の `target.name` のタイポ

```bash
kubectl get externalsecret todo-db -n prod -o yaml | grep -A2 target
```

### 症状: Vault unseal が必要

Pod 再起動後、自動で sealed に戻る。

```bash
kubectl get pods -n vault
# vault-0   0/1   Running
```

自動 unseal するには:

1. **auto-unseal** を Cloud KMS と組合せる(本番推奨)
2. OperatorHub の vault-auto-unsealer を入れる
3. (検証なら)Pod start hook で unseal キーを叩く

教材では手動で OK:

```bash
for i in 0 1 2; do
  kubectl get pod vault-$i -n vault -o jsonpath='{.status.phase}'
done
# 全部 sealed なら unseal を流す
```

### 症状: Secret 更新後も Pod が古い値で動いている

- env で渡している → Pod 再起動が必要
- volume 経由でも kubelet が反映するまで最大 60 秒 + アプリが再読込しないと反映されない

対策: Reloader を入れて annotation `reloader.stakater.com/auto: "true"` を付ける。

### 症状: Sealed Secret apply 後に SealedSecret unsealing failed

```bash
kubectl describe sealedsecret db-cred -n prod
# Events:
#   Warning  ErrUnsealFailed  ... namespace does not match
```

原因: スコープが `strict`(デフォルト)で、`metadata.namespace` が暗号化時と違う。
対策: 暗号化時に `--namespace prod` を付ける、または `--scope namespace-wide`。

### 症状: cert-manager の Certificate が Ready False

```bash
kubectl describe certificate todo-api-tls -n prod
# Status:
#   Conditions:
#     Type: Ready    Status: False
#     Message: Issuing certificate as Secret does not exist
```

原因:

- Issuer (ClusterIssuer) が Ready=False
- DNS01 で CloudFlare API token Secret が無い
- HTTP01 で対応する Ingress が無い

```bash
kubectl describe clusterissuer internal-ca
# Status:
#   Conditions:
#     Type: Ready   Status: True
```

Issuer から潰す。

### 症状: etcd の暗号化を有効にしたが既存 Secret が暗号化されない

EncryptionConfiguration は **書き込み時にだけ適用** されます。既存の Secret は読み取り時に旧 provider(identity)で平文として読まれ、再書き込みされない限りそのまま。

対策:

```bash
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
```

これで全 Secret が `replace` 経由で書き直され、新 provider で暗号化される。

### 症状: kubectl describe secret では `<secret>` と出るが、kubectl get -o yaml では値が見える

これは **意図された挙動**。describe は安全のため値を隠すが、`get -o yaml` は API を叩いて raw を返す。
RBAC で `secrets/get` 権限を持つユーザは中身を見られる。安全のため:

- 開発者ロールから secrets/get を外す
- 必要なら Vault Auth で代替
- 監査ログで `get secret` を監視

---

## ベストプラクティス総まとめ

```mermaid
flowchart LR
    subgraph 基本["まず全クラスタで"]
        B1[etcd Encryption at Rest]
        B2[RBAC で secrets/get 制限]
        B3[immutable Secret]
        B4[volume mount を優先]
    end
    subgraph GitOps["GitOps と組合せ"]
        G1[ESO + Vault]
        G2[ClusterSecretStore で集約]
        G3[Reloader で自動再起動]
    end
    subgraph 高度["コンプライアンス要求高"]
        H1[KMS v2 + 外部 KMS]
        H2[CSI Secret Store]
        H3[Vault 動的 Secret]
        H4[cert-manager で TLS 自動化]
    end
    基本 --> GitOps --> 高度

    style B1 fill:#dfd,color:#000
    style G1 fill:#dfd,color:#000
    style H1 fill:#dfd,color:#000
```

### Do

| やる事 | 理由 |
|--------|------|
| etcd Encryption at Rest を必ず有効化 | バックアップ・スナップショット漏洩対策 |
| Secret の RBAC を狭く | get/list/watch をデフォルトで持たせない |
| Volume マウントで注入 | env より安全(プロセス環境変数の漏出防止) |
| `defaultMode: 0400` | other 読取禁止 |
| readOnlyRootFilesystem + 別 emptyDir | tmp 書込みは別マウント |
| immutable Secret(変わらないもの) | 性能・misuse 防止 |
| ESO + Vault で正本を Git の外に | GitOps と秘匿性の両立 |
| Reloader で自動 rollout | rotation を意味あるものに |
| cert-manager で TLS 自動更新 | 期限切れ事故ゼロ |
| Vault 動的 Secret(DB / PKI) | 漏洩時の被害最小化 |

### Don't

| やらない事 | 理由 |
|------------|------|
| 平文 Secret を Git に置く | コミット履歴に永遠に残る |
| Slack で Secret を共有 | 監査不能、漏洩経路 |
| 共有 PC で `kubectl get secret -o yaml` | 画面録画やキャッシュに残る |
| Secret を env で渡してアプリログにダンプ | スタックトレース等で漏れる |
| Secret を ConfigMap に入れる | RBAC・暗号化対象から外れる |
| `latest` Secret を使い続ける | rotation 不能 |
| rotation スクリプトを cron で手書き | テストが効かない、サイレント失敗 |
| 鍵を 1 人の PC にしか置かない | 退職・故障で詰む |

---

## 参考リンク

- Kubernetes Encryption at Rest: <https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/>
- KMS v2 KEP-3299: <https://github.com/kubernetes/enhancements/tree/master/keps/sig-auth/3299-kms-v2-improvements>
- External Secrets Operator: <https://external-secrets.io/>
- HashiCorp Vault: <https://developer.hashicorp.com/vault/docs>
- Vault Helm chart: <https://github.com/hashicorp/vault-helm>
- Sealed Secrets: <https://github.com/bitnami-labs/sealed-secrets>
- SOPS: <https://github.com/getsops/sops>
- age: <https://github.com/FiloSottile/age>
- Secrets Store CSI Driver: <https://secrets-store-csi-driver.sigs.k8s.io/>
- cert-manager: <https://cert-manager.io/docs/>
- trust-manager: <https://cert-manager.io/docs/trust/trust-manager/>
- Stakater Reloader: <https://github.com/stakater/Reloader>

---

## チェックポイント

ここまでで以下を **自分の言葉で** 説明できるか確認してください。

- [ ] base64 が暗号化でない理由と、それでも `data` フィールドで使う理由
- [ ] Secret と ConfigMap を分けている運用上のメリットを 3 つ以上
- [ ] etcd Encryption at Rest が「書き込み時にのみ適用」される性質と、既存 Secret の再暗号化方法
- [ ] KMS v1 と v2 の最大の違い(DEK キャッシュ)
- [ ] Sealed Secrets / SOPS+age / ESO の3方式それぞれの強みと弱み
- [ ] ESO の SecretStore と ClusterSecretStore の使い分け
- [ ] Vault の seal/unseal の意味と、auto-unseal が本番で必要な理由
- [ ] Vault Kubernetes Auth で SA → Vault Role がどう紐づくか
- [ ] env 注入と volume 注入のセキュリティ差(`/proc/<pid>/environ` 含む)
- [ ] CSI Secret Store Driver が ESO より優れる点
- [ ] Reloader が解決する問題(Secret 更新後の Pod 反映)
- [ ] cert-manager の Certificate / Issuer / ClusterIssuer の関係
- [ ] Vault 動的 Secret(`database/creds/...`)がパスワード rotation で優れる理由
- [ ] `kubectl describe secret` で値が隠れるのに `get -o yaml` で見える理由

---

## 10章 まとめ

ここまでで Kubernetes セキュリティの 5 大柱を一通り扱いました。

```mermaid
flowchart TB
    subgraph "認証認可"
        A1[RBAC]
        A2[ServiceAccount]
    end
    subgraph "ワークロード分離"
        B1[Pod Security Standards]
    end
    subgraph "サプライチェーン"
        C1[イメージ署名・SBOM]
        C2[Trivy / Cosign / Kyverno]
    end
    subgraph "シークレット"
        D1[etcd 暗号化]
        D2[Vault + ESO]
        D3[cert-manager]
    end
    A1 --> All[統合された<br/>セキュリティ運用]
    A2 --> All
    B1 --> All
    C1 --> All
    C2 --> All
    D1 --> All
    D2 --> All
    D3 --> All

    style All fill:#dfd,color:#000
```

実運用ではどれか 1 つだけでは穴が開きます。

| 仮想シナリオ | 防げる柱 |
|-------------|---------|
| 攻撃者が Secret を直接読みに来る | RBAC + etcd 暗号化 |
| 攻撃者が乗っ取った Pod で escalate | PSS + SA トークン制限 |
| 攻撃者が悪意あるイメージを push | イメージ署名 + Admission |
| 攻撃者が漏洩したパスワードを使う | 動的 Secret + rotation |
| 攻撃者がノードに侵入してメモリダンプ | volume + tmpfs(env 回避) |

「**1 つの侵入で全てを失わない**」のが多層防御(Defense in Depth)。

→ 次は [11. オブザーバビリティ]({{ '/11-observability/' | relative_url }})
