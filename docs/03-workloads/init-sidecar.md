---
title: Init Container と Sidecar
parent: 03. ワークロード
nav_order: 4
---

# Init Container と Sidecar
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

1 つの Pod に複数のコンテナを詰めるためのパターンを学びます。

## Init Container

メインコンテナの **前** に順次実行される、初期化用のコンテナ。

```yaml
spec:
  initContainers:
  - name: wait-for-db
    image: busybox:1.36
    command: ['sh','-c','until nc -z postgres 5432; do echo waiting; sleep 2; done']
  - name: db-migrate
    image: 192.168.56.10:5000/todo-api:0.1.0
    command: ['python','-m','alembic','upgrade','head']
    envFrom:
    - secretRef:
        name: todo-secret
  containers:
  - name: api
    image: 192.168.56.10:5000/todo-api:0.1.0
```

- 複数定義した場合、上から順に **逐次実行**
- すべて成功してから `containers` が起動
- 失敗したら `restartPolicy` に従ってリトライ

### 用途

- DB の準備完了を待つ
- DB マイグレーション実行
- 初期データの取得 (`git clone`, `wget`)
- 設定ファイルの生成

## Sidecar コンテナ

メインコンテナと **並行** で動き続ける補助コンテナ。

```yaml
spec:
  containers:
  - name: app
    image: myapp:1.0
    volumeMounts:
    - name: logs
      mountPath: /var/log/app
  - name: log-shipper
    image: fluent/fluent-bit:3.0
    volumeMounts:
    - name: logs
      mountPath: /var/log/app
      readOnly: true
  volumes:
  - name: logs
    emptyDir: {}
```

メインがログを書き、サイドカーがそれを別途送出する典型パターン。

### Native Sidecar (v1.29+)

従来 Sidecar は普通の `containers` として書いていましたが、**Pod の停止順** に問題がありました。
v1.29 から **Native Sidecar** がリリースされ、Init Container として `restartPolicy: Always` を指定すると、

- 起動順: Init → Sidecar → Main の順
- 停止順: Main → Sidecar の順 (適切)
- ライフサイクル: Sidecar は Pod の生存期間中ずっと動く

が保証されるようになりました。

```yaml
spec:
  initContainers:
  - name: log-shipper
    image: fluent/fluent-bit:3.0
    restartPolicy: Always       # ← これでSidecar扱い
    volumeMounts:
    - name: logs
      mountPath: /var/log/app
      readOnly: true
  containers:
  - name: app
    image: myapp:1.0
```

## マルチコンテナ Pod の典型パターン

| パターン | 説明 | 例 |
|----------|------|------|
| Sidecar | メインを補助 | ログ転送、メトリクス公開 |
| Ambassador | 外部通信を代理 | Envoy で TLS 終端 |
| Adapter | 出力形式を変換 | アプリログを JSON 化 |
| Init | 起動前準備 | DB マイグレーション |

## チェックポイント

- [ ] Init Container と Sidecar の違いを説明できる
- [ ] Native Sidecar が解決した問題は何か
- [ ] サンプルアプリの API Pod に Init を入れるなら何を入れるか
