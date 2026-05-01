---
title: DR (Disaster Recovery)
parent: 11. SRE運用
nav_order: 4
---

# DR (Disaster Recovery)
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

「クラスタ全体が壊れた」「データが消えた」前提で、**何時間で・何を失わずに** 復旧できるかを設計します。

## 用語

| 用語 | 意味 |
|------|------|
| **RPO** (Recovery Point Objective) | 失ってよいデータの最大量(時間で表現) |
| **RTO** (Recovery Time Objective) | 復旧までに許される最大時間 |

サンプルアプリの目標例: RPO 1 時間 / RTO 4 時間。

## バックアップ対象

| 対象 | ツール | 頻度 |
|------|--------|------|
| etcd スナップショット | etcdctl snapshot save | 1時間ごと |
| マニフェスト | Git (GitOps) | 即時 |
| PV データ | Velero / CSI Snapshot | 6時間ごと |
| イメージ | レジストリの冗長化 / バックアップ | 都度 |

## etcd バックアップとリストア

### バックアップ (CronJob)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: etcd-backup
  namespace: kube-system
spec:
  schedule: "0 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          hostNetwork: true
          tolerations:
          - operator: Exists
          nodeSelector:
            node-role.kubernetes.io/control-plane: ""
          containers:
          - name: backup
            image: registry.k8s.io/etcd:3.5.13-0
            command:
            - sh
            - -c
            - |
              ETCDCTL_API=3 etcdctl \
                --endpoints=https://127.0.0.1:2379 \
                --cacert=/etc/kubernetes/pki/etcd/ca.crt \
                --cert=/etc/kubernetes/pki/etcd/server.crt \
                --key=/etc/kubernetes/pki/etcd/server.key \
                snapshot save /backup/etcd-$(date +%Y%m%d-%H%M).db
              find /backup -mtime +7 -delete
            volumeMounts:
            - {name: pki, mountPath: /etc/kubernetes/pki/etcd, readOnly: true}
            - {name: backup, mountPath: /backup}
          volumes:
          - name: pki
            hostPath: {path: /etc/kubernetes/pki/etcd}
          - name: backup
            nfs:
              server: 192.168.56.30
              path: /export/etcd-backup
```

### リストア

```bash
# 全 control-plane で kube-apiserver / etcd を停止
mv /etc/kubernetes/manifests /etc/kubernetes/manifests.bak

# 1 台目のみで復元
ETCDCTL_API=3 etcdctl snapshot restore /backup/etcd-20260430-1400.db \
  --data-dir /var/lib/etcd-restore \
  --name k8s-cp1 \
  --initial-cluster k8s-cp1=https://192.168.56.11:2380 \
  --initial-cluster-token etcd-cluster-1 \
  --initial-advertise-peer-urls https://192.168.56.11:2380

# data-dir を差し替え
mv /var/lib/etcd /var/lib/etcd.broken
mv /var/lib/etcd-restore /var/lib/etcd

# manifests を戻す
mv /etc/kubernetes/manifests.bak /etc/kubernetes/manifests
```

詳しい手順は kubeadm 公式ドキュメント参照。
**実際にやってみるのが一番** ─ 本教材ではローカルクラスタで etcd リストア演習をします。

## Velero による PV バックアップ

```bash
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.10.0 \
  --bucket velero \
  --secret-file ./minio-creds \
  --backup-location-config region=minio,s3ForcePathStyle=true,s3Url=http://minio.minio.svc:9000 \
  --use-volume-snapshots=false \
  --use-node-agent

# 定期バックアップ
velero schedule create daily \
  --schedule="0 2 * * *" \
  --include-namespaces=prod \
  --ttl 720h

# 手動バックアップ
velero backup create todo-pre-upgrade --include-namespaces=prod

# リストア
velero restore create --from-backup todo-pre-upgrade
```

Node Agent モード(以前の `restic`)を使うと、CSI Snapshot に対応していない StorageClass でも PV のファイルレベルバックアップが取れます。

## クラスタの再構築をスクリプト化する

GitOps で運用していれば、

1. 新クラスタを kubeadm で立てる
2. Argo CD インストール
3. Root Application 1 つ apply
4. すべてのアプリ・周辺ツールが自動で復元

という流れになります。**「クラスタ自体は使い捨て」** にできるのがGitOpsの真価。

## DR訓練

DR 計画は **試さない限り動きません**。半年に 1 回は実機演習しましょう。
ローカル環境は格好の訓練場です。

## チェックポイント

- [ ] RPO と RTO の違いを言える
- [ ] etcd リストア手順の流れを説明できる
- [ ] Velero と GitOps の役割の違い
