---
title: 本番チェックリスト
parent: 99. 付録
nav_order: 2
---

# 本番チェックリスト
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

新サービスを本番に上げる前のチェックリスト。**全項目に「Yes」と答えられるまでローンチ延期** が原則。

## クラスタ

- [ ] Control Plane が HA 構成 (3台以上)
- [ ] etcd の自動バックアップが動いている
- [ ] etcd リストア手順を実機で試したことがある
- [ ] etcd 暗号化(EncryptionConfiguration)有効
- [ ] kube-apiserver の audit log を収集している
- [ ] 証明書期限の監視がある (`kubeadm certs check-expiration`)
- [ ] CNI は NetworkPolicy をサポート (Calico/Cilium 等)
- [ ] CoreDNS が冗長化されている
- [ ] Metrics Server が動いている
- [ ] 監視・ロギング・トレースが動いている

## Namespace / RBAC

- [ ] Namespace を環境/チーム別に分割している
- [ ] ResourceQuota が設定されている
- [ ] LimitRange でデフォルト Resources がある
- [ ] Pod Security Standards を `restricted` で適用 (または audit/warn から段階適用中)
- [ ] 各アプリ用に ServiceAccount を分けている
- [ ] `default` SA は使っていない、または最小権限
- [ ] human admin の権限は最小権限ベース、`cluster-admin` は緊急用のみ

## ワークロード

- [ ] すべての Pod に Resources Requests がある
- [ ] Memory Limits がある
- [ ] CPU Limits は付けない、または余裕を持って設定
- [ ] Liveness Probe を必要なものだけに設定
- [ ] Readiness Probe を全 Web/API に設定
- [ ] Startup Probe を起動が遅いアプリに設定
- [ ] Replicas は 2 以上(可用性 SLO ある場合)
- [ ] PodDisruptionBudget が設定されている
- [ ] 同一アプリの Pod が異なるノードに分散 (podAntiAffinity / topologySpreadConstraints)
- [ ] root で動いていない (`runAsNonRoot: true`)
- [ ] readOnlyRootFilesystem: true

## Service / Ingress

- [ ] Service の selector が正しい labels に当たっている
- [ ] Ingress に TLS が設定されている(本番)
- [ ] cert-manager 等で証明書自動更新
- [ ] NetworkPolicy で必要最小限の通信のみ許可
- [ ] DNS がすべての Pod から引ける

## ストレージ

- [ ] DB の StatefulSet には `volumeClaimTemplates` で永続 PV
- [ ] reclaimPolicy: Retain
- [ ] PV の定期バックアップ (Velero / CSI Snapshot)
- [ ] バックアップからのリストア手順を試したことがある

## 設定 / Secret

- [ ] 設定値は ConfigMap / Secret に外出し、イメージに焼き込まない
- [ ] Secret は Sealed Secrets / ESO 等で管理、Git に平文を置かない
- [ ] etcd 暗号化が有効
- [ ] パスワードや API Key の rotate 手順がある

## CI/CD

- [ ] イメージタグに `latest` を使っていない
- [ ] CI で Trivy / kube-linter / kubeconform が動いている
- [ ] イメージに署名 (cosign) と検証
- [ ] GitOps (Argo CD / Flux) でデプロイ
- [ ] ロールバック手順がある (`kubectl rollout undo` または `argocd app rollback`)
- [ ] カナリア / Blue-Green リリース可能 (本当に重要なサービスなら)

## 可観測性

- [ ] メトリクス (Prometheus) で四大指標 (Saturation, Errors, Latency, Traffic) を見ている
- [ ] ログ (Loki/ELK) を集約
- [ ] トレース (Tempo/Jaeger) を取得
- [ ] SLI / SLO を定義
- [ ] Burn rate アラートを設定
- [ ] アラートに runbook URL を付与
- [ ] On-call ローテーションがある
- [ ] Incident Channel と通知ツール (Slack/PagerDuty) の設定

## SRE

- [ ] DR 計画 (RPO/RTO) が文書化
- [ ] DR 訓練を半年に1回実施
- [ ] ポストモーテムテンプレートがある
- [ ] アクションアイテムの追跡がある
- [ ] キャパシティプランニングを月次で実施

## 通信・セキュリティ

- [ ] mTLS で内部通信暗号化(必要なら Service Mesh)
- [ ] Image scan の結果を見て、CRITICAL 脆弱性 0 を維持
- [ ] CIS Kubernetes Benchmark をクリア
- [ ] kube-bench を CI で動かしている

## ドキュメント

- [ ] アーキテクチャ図がある
- [ ] runbook (障害対応手順) がある
- [ ] on-boarding ドキュメントがある
- [ ] アラート → runbook が紐付いている
