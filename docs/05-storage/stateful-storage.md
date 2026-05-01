---
title: ステートフル運用の実例
parent: 05. ストレージ
nav_order: 4
---

# ステートフル運用の実例
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

PostgreSQL や Redis のような状態を持つアプリを、ローカル環境(オンプレ kubeadm)で運用するときのベストプラクティスをまとめます。

## バックアップ

PV のバックアップ手段:

1. アプリレベル (pg_dump, redis-cli BGSAVE)
2. ストレージレベル (CSI Snapshot)
3. クラスタレベル (Velero)

ローカル環境では Velero + MinIO の組み合わせがおすすめ。

```bash
# MinIO 立ち上げ (バックアップ先 S3互換)
helm install minio bitnami/minio --namespace minio --create-namespace

# Velero インストール
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.10.0 \
  --bucket velero \
  --secret-file ./credentials-velero \
  --backup-location-config region=minio,s3ForcePathStyle=true,s3Url=http://minio.minio.svc:9000
```

```bash
# 定期バックアップ
velero schedule create daily --schedule="0 2 * * *" --include-namespaces=prod
```

## PVC リサイズ

```bash
# 既存PVC の容量を上げる
kubectl edit pvc postgres-data
# spec.resources.requests.storage: 5Gi → 20Gi

# Pod の再作成 (ファイルシステムの拡張のため)
kubectl delete pod postgres-0
```

## Volume Snapshot

CSI Snapshot 対応のドライバなら、PV のスナップショットを取れます。

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-snap-2026-04-30
spec:
  volumeSnapshotClassName: csi-snapshot
  source:
    persistentVolumeClaimName: data-postgres-0
```

スナップショットから新しい PVC を復元できます。

## 注意点まとめ

- **PV はノードに紐付く** ことがあるので、Pod の配置制約に注意
- **削除されない設計** を意識(`reclaimPolicy: Retain`、Helm の `keep` annotation)
- **fsGroup** を設定して Pod 内ユーザーが書き込めるように

```yaml
spec:
  securityContext:
    fsGroup: 999      # postgres ユーザーのGID
```

- **書き込み性能** は CSI ドライバとストレージの実体に強く依存。NFS は遅いので DB なら local-path のほうが速い

## チェックポイント

- [ ] PVC リサイズの手順を説明できる
- [ ] ローカル環境で Velero を使うバックアップ構成がイメージできる
- [ ] fsGroup を入れる理由
