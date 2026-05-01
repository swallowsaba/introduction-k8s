---
title: Volume
parent: 05. ストレージ
nav_order: 1
---

# Volume
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

Pod の `spec.volumes[]` でボリュームを定義し、`containers[].volumeMounts[]` でマウントします。
Volume にはたくさんの種類があり、用途で使い分けます。

## emptyDir

Pod の生存中だけ存在する一時領域。Pod が消えると一緒に消える。

```yaml
spec:
  volumes:
  - name: cache
    emptyDir:
      sizeLimit: 1Gi
      medium: Memory      # tmpfs を使う場合
  containers:
  - name: app
    volumeMounts:
    - name: cache
      mountPath: /cache
```

サイドカー間でファイル受け渡しする用途で頻出。

## hostPath

ノードのファイルシステムを直接マウント。

```yaml
volumes:
- name: log
  hostPath:
    path: /var/log
    type: Directory
```

{: .warning }
hostPath は **本番では原則使わない**。Pod がノードに依存し、セキュリティリスクも高い。
ノード上のシステム情報を見たい DaemonSet (node-exporter等) でだけ使うのが基本。

## configMap / secret

ConfigMap や Secret をファイルとしてマウント。詳細は 6 章で。

```yaml
volumes:
- name: config
  configMap:
    name: app-config
- name: tls
  secret:
    secretName: app-tls
```

## projected

複数の ConfigMap / Secret / ServiceAccountToken を 1 ディレクトリにまとめてマウント。

```yaml
volumes:
- name: combined
  projected:
    sources:
    - configMap: {name: a}
    - configMap: {name: b}
    - serviceAccountToken:
        path: token
        expirationSeconds: 3600
```

## persistentVolumeClaim

永続ストレージへの参照。次の節で詳しく扱います。

```yaml
volumes:
- name: data
  persistentVolumeClaim:
    claimName: postgres-data
```

## チェックポイント

- [ ] emptyDir と PVC の違いを説明できる
- [ ] hostPath を本番で避ける理由
