---
title: Job と CronJob
parent: 03. ワークロード
nav_order: 3
---

# Job と CronJob
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

長時間動き続ける Pod ではなく、**完了を目的とするバッチ処理** には Job / CronJob を使います。

## Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pi
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 4
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: pi
        image: perl:5.34
        command: ["perl","-Mbignum=bpi","-wle","print bpi(2000)"]
```

- `restartPolicy` は `OnFailure` か `Never`
- `backoffLimit` 超えても成功しなければ Failed
- `ttlSecondsAfterFinished` を入れないと、完了済 Job が残り続ける

```bash
kubectl apply -f job.yaml
kubectl get jobs
kubectl logs -l job-name=pi
```

### 並列実行パターン

| パターン | spec |
|---------|------|
| 1個だけ実行 | `completions:1, parallelism:1` |
| 固定 N 個並列 | `completions:10, parallelism:5` |
| ワーカープール (動的) | `parallelism:5` のみ、外部キューを参照 |

## CronJob

サンプルアプリの「期限切れTODOの通知バッチ」で使います。

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: todo-notify
spec:
  schedule: "0 9 * * *"           # 毎朝9時 (UTC)
  timeZone: "Asia/Tokyo"           # v1.27+
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  startingDeadlineSeconds: 60
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: notify
            image: 192.168.56.10:5000/todo-worker:0.1.0
            command: ["python","notify.py"]
            envFrom:
            - configMapRef:
                name: todo-config
            - secretRef:
                name: todo-secret
```

- `concurrencyPolicy: Forbid` : 前回 Job 実行中なら新規はスキップ
- `startingDeadlineSeconds` : この秒数以内に開始できないなら諦める

## 本番での注意

- **冪等性** : 1度と複数回で結果が同じになるよう作る (重複実行に備える)
- **タイムアウト** : `activeDeadlineSeconds` を入れて暴走を止める
- **完了済 Job の蓄積** : `ttlSecondsAfterFinished` または `historyLimit` を必ず設定
- **アラート** : Job 失敗を監視に乗せる (9 章で扱います)

## チェックポイント

- [ ] Deployment と Job の使い分けを言える
- [ ] CronJob を本番運用するときに最低限設定すべき項目を 3 つ
