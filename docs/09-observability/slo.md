---
title: SLI/SLO/Error Budget
parent: 09. 可観測性
nav_order: 4
---

# SLI/SLO/Error Budget
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

監視を「とにかくアラートを足す」運用にすると、**疲弊し、本当に重要な問題が埋もれる** ことになります。
SRE はサービスの信頼性を **数値で目標化** することで、アラートと意思決定の質を上げます。

## 用語

| 用語 | 意味 | 例 |
|------|------|------|
| **SLI** (Service Level Indicator) | 信頼性を測る指標 | 成功率、レイテンシ、可用性 |
| **SLO** (Service Level Objective) | SLI の目標値 | 「成功率 99.9%」 |
| **SLA** (Service Level Agreement) | 顧客との契約。SLO より緩く設定 | 「99.5% を割ったら返金」 |
| **Error Budget** | SLO を割らない範囲で使える「失敗予算」 | 99.9% なら月43.8分 |

## サンプルアプリの SLO 例

| サービス | SLI | SLO |
|----------|-----|-----|
| `todo-api` | 5xxを除いたリクエスト割合 | 99.9% (30日) |
| `todo-api` | p95 レイテンシ < 500ms の割合 | 99.0% |
| `todo-frontend` | 200/300 を返した割合 | 99.95% |

## Error Budget Policy

Error Budget が尽きそうな(または尽きた)ときに、**何をするか** を事前に決めておく。

```
- Budget 残 50% 以上 : 通常通り開発・リリース
- Budget 残 10% 以下 : 信頼性向上タスクを優先、新機能リリース凍結
- Budget 枯渇        : ポストモーテム実施、根本対策完了まで凍結
```

## 実装: PrometheusRule で SLO 監視

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: todo-api-slo
spec:
  groups:
  - name: slo.rules
    rules:
    # 30日 99.9% を維持するには、エラー率 0.1% 未満であるべき

    # Burn rate ベースのアラート (Google SRE推奨)
    - alert: TodoApiErrorBudgetBurnFast
      expr: |
        (
          sum(rate(http_requests_total{job="todo-api",code=~"5.."}[1h]))
          /
          sum(rate(http_requests_total{job="todo-api"}[1h]))
        ) > 0.001 * 14.4   # 1時間で月予算の2%を消費するペース
      for: 2m
      labels:
        severity: critical
      annotations:
        summary: "Error budget burning fast (will exhaust in <2 days)"
        runbook_url: https://wiki/runbooks/todo-api-slo-burn

    - alert: TodoApiErrorBudgetBurnSlow
      expr: |
        (
          sum(rate(http_requests_total{job="todo-api",code=~"5.."}[6h]))
          /
          sum(rate(http_requests_total{job="todo-api"}[6h]))
        ) > 0.001 * 6   # 6時間で月予算の5%を消費するペース
      for: 15m
      labels:
        severity: warning
```

「2つの時間窓 + 2つの burn rate」を組み合わせると、**速く深刻な障害も、ゆっくり進む劣化も** 検知できます。

## SLO ツール

「Burn rate アラートを毎回手書きするのは大変」という人向けに、
**[Sloth](https://github.com/slok/sloth)** や **[Pyrra](https://github.com/pyrra-dev/pyrra)** といった OSS が SLO 定義から PrometheusRule を生成してくれます。

Sloth の例:

```yaml
version: "prometheus/v1"
service: "todo-api"
slos:
- name: "availability"
  objective: 99.9
  description: "Successful HTTP responses"
  sli:
    events:
      error_query: sum(rate(http_requests_total{job="todo-api",code=~"5.."}[{{.window}}]))
      total_query: sum(rate(http_requests_total{job="todo-api"}[{{.window}}]))
  alerting:
    name: TodoApiHighErrorRate
    page_alert:
      labels: {severity: critical}
    ticket_alert:
      labels: {severity: warning}
```

これだけで multi-window multi-burn-rate のアラートと記録ルールが生成されます。

## ダッシュボード

Grafana に SLO ダッシュボードを作ると、

- 現在のSLI
- 残り Error Budget(% / 時間)
- Burn rate

が一目で分かります。Pyrra は専用 UI も提供。

## チェックポイント

- [ ] SLI と SLO の違いを言える
- [ ] Error Budget が枯れた時のポリシーを 1 つ提案できる
- [ ] Multi-window burn rate アラートが解決する課題
