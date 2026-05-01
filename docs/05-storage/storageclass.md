---
title: StorageClass
parent: 05. ストレージ
nav_order: 3
---

# StorageClass
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**StorageClass** は「どのストレージプロバイダで、どんなパラメータで PV を作るか」を定義するリソース。
動的プロビジョニングの中核です。

## 例: NFS

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /export
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

## ローカル環境向け StorageClass

本教材では2系統用意します。

| StorageClass | 用途 | プロビジョナ |
|--------------|------|--------------|
| local-path | 単純な単一ノードRWO | rancher/local-path-provisioner |
| nfs | RWX が必要なケース、複数ノードでの永続化 | csi-driver-nfs |

```bash
# local-path-provisioner (Minikube/単一ノード環境)
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml

# csi-driver-nfs
helm repo add csi-driver-nfs https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/master/charts
helm install csi-driver-nfs csi-driver-nfs/csi-driver-nfs \
  --namespace kube-system --version v4.7.0
```

## volumeBindingMode

| モード | 動作 |
|--------|------|
| Immediate | PVC 作成時に即 PV 作成 |
| WaitForFirstConsumer | Pod がスケジュールされるまで PV 作成を待つ |

`WaitForFirstConsumer` を選ぶと、**Pod が配置されるノードに合った PV を作る** ため、ローカルディスクや AZ 制約があるストレージで有効。

## allowVolumeExpansion

`true` にすると、PVC を編集して容量を増やせます(縮小は不可)。

```bash
kubectl edit pvc postgres-data
# spec.resources.requests.storage を 5Gi → 10Gi に
```

ストレージプロバイダがサポートしている必要あり。

## デフォルト StorageClass

```yaml
metadata:
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
```

PVC で `storageClassName` を省略するとこれが使われます。
Minikube の `standard` がこれにあたります。

## チェックポイント

- [ ] `WaitForFirstConsumer` がローカルディスクで望ましい理由
- [ ] `allowVolumeExpansion` を有効にしておくべき理由
