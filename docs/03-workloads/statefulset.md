---
title: StatefulSet
parent: 03. ワークロード
nav_order: 1
---

# StatefulSet
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**StatefulSet** は状態を持つアプリ(DB、キュー)向けのワークロード。

| | Deployment | StatefulSet |
|---|---|---|
| Pod名 | `web-xxxx-yyyy` ランダム | `db-0`, `db-1`, `db-2` 順序付き |
| Pod のIP/DNS | 不安定 | 安定 (Headless Serviceと組合せ) |
| 起動・停止順 | 並列 | 順次 (0→1→2) |
| ストレージ | 共有可 | Pod ごとに専用 PVC |
| スケール | 自由 | 順次 |

## いつ使うか

- 各 Pod が独立した永続ストレージを持つ必要がある
- Pod に固定の DNS 名/順序が必要(クォーラム制御、リーダー選出)
- Pod 識別子に応じてレプリケーションを構成する(MySQL/MongoDB/Postgres replication)

ステートレスな Web/API は **Deployment**、データベースは **StatefulSet** が基本。

## YAML例: PostgreSQL (サンプルアプリ用)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
spec:
  clusterIP: None      # Headless Service
  selector:
    app: postgres
  ports:
  - port: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16
        env:
        - name: POSTGRES_DB
          value: todo
        - name: POSTGRES_USER
          value: todo
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: standard
      resources:
        requests:
          storage: 10Gi
```

ポイント:

- `serviceName` で Headless Service と紐付け
- `volumeClaimTemplates` で **Pod ごと** に PVC が自動生成
- 各 Pod は `postgres-0.postgres` という DNS 名で到達可能

## ライフサイクルの特徴

- スケールアップは `0,1,2,...,N-1` の順
- スケールダウンは逆順
- 削除しても **PVC は残る** (データ保護)
- イメージ更新は `OnDelete` または `RollingUpdate`

```yaml
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 0   # 0未満の番号は更新しない (カナリアに使える)
```

## 本番運用の注意

### StatefulSet ≠ 高可用 DB

StatefulSet があれば DB が冗長化されるわけではありません。
**レプリケーションやフェイルオーバーはアプリ自身の責務**。

PostgreSQL なら CloudNativePG / Crunchy、MySQL なら Percona Operator など、
**Operator** を使うのが現実解です(11 章で扱います)。

### ステートフルワークロードの選択肢

ローカル完結の本教材では StatefulSet + Operator を体験しますが、本番では選択肢として:

- DBサーバー(VM)を別途立て、K8s クラスタからは外出しで接続
- マネージドDB(クラウド前提なら)
- Kubernetes 内で StatefulSet + Operator

があります。**「DBはK8sの外に出す」のが堅い** のは押さえておきましょう。

## チェックポイント

- [ ] Deployment と StatefulSet を選び分ける基準を 3 つ言える
- [ ] StatefulSet を使えば DB が高可用になるわけではない理由
- [ ] `volumeClaimTemplates` と `volumes` の違い
