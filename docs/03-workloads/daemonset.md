---
title: DaemonSet
parent: 03. ワークロード
nav_order: 2
---

# DaemonSet
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

**DaemonSet** は、クラスタの各ノードに 1 つずつ Pod を起動するワークロード。

## 用途

ノードごとに必要なエージェント類:

- ログ収集 (Fluent Bit, Promtail)
- メトリクス収集 (Node Exporter)
- ネットワークプラグイン (Calico, Cilium のPod)
- セキュリティエージェント (Falco)
- ストレージドライバ (CSI)

## YAML例: Node Exporter

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    metadata:
      labels:
        app: node-exporter
    spec:
      hostNetwork: true
      hostPID: true
      containers:
      - name: exporter
        image: prom/node-exporter:v1.8.0
        args:
        - --path.rootfs=/host
        ports:
        - containerPort: 9100
        volumeMounts:
        - name: host
          mountPath: /host
          readOnly: true
      volumes:
      - name: host
        hostPath:
          path: /
      tolerations:
      - operator: Exists       # マスターノードにも入る
```

`tolerations: operator: Exists` で `NoSchedule` Taint があるノード(マスター含む)にもデプロイできます。

## ノードの一部にだけ配置

```yaml
spec:
  template:
    spec:
      nodeSelector:
        gpu: "true"
```

## アップデート戦略

```yaml
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
```

`OnDelete` を選ぶと、Pod を手動で消すまで古いまま動きます。慎重に更新したい監視・ログ系で使うことが。

## チェックポイント

- [ ] DaemonSet を使うべきケースを 3 つ言える
- [ ] マスターノードにも DaemonSet を配置するための YAML 設定
