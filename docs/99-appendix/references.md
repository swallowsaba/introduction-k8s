---
title: 参考文献・リンク集
parent: 99. 付録
nav_order: 3
---

# 参考文献・リンク集
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 公式ドキュメント

- [Kubernetes Documentation](https://kubernetes.io/docs/) — 一次情報。日本語版あり
- [kubectl Reference](https://kubernetes.io/docs/reference/kubectl/)
- [Kubernetes API Reference](https://kubernetes.io/docs/reference/kubernetes-api/)
- [CNCF Landscape](https://landscape.cncf.io/) — 周辺ツール俯瞰

## 書籍

- 『Kubernetes 完全ガイド 第2版』青山真也 — 日本語の決定版
- 『Programming Kubernetes』 — Operator/Controllerを学ぶなら
- 『Kubernetes in Action 2nd ed.』Marko Lukša
- 『Kubernetes Patterns』Bilgin Ibryam, Roland Huß — 設計パターン集
- 『Cloud Native DevOps with Kubernetes』 — 運用観点
- 『Site Reliability Engineering』Google — SRE のバイブル
- 『The Site Reliability Workbook』 — 同実践編

## ブログ・記事

- [Kubernetes Blog](https://kubernetes.io/blog/)
- [CNCF Blog](https://www.cncf.io/blog/)
- [learnk8s blog](https://learnk8s.io/blog) — 図解がわかりやすい
- [Datadog Container Report](https://www.datadoghq.com/container-report/) — 業界トレンド
- [SREcon の発表アーカイブ](https://www.usenix.org/conferences/byname/925)

## 動画

- [TGI Kubernetes (Joe Beda)](https://www.youtube.com/playlist?list=PL7bmigfV0EqQzxcNpmcdTJ9eFRPBe-iZa)
- [KubeCon の各回 YouTube プレイリスト](https://www.youtube.com/@cncf)

## 主要ツール

### CI/CD・GitOps
- [Argo CD](https://argo-cd.readthedocs.io/)
- [Argo Rollouts](https://argo-rollouts.readthedocs.io/)
- [Flux](https://fluxcd.io/)
- [Tekton](https://tekton.dev/)

### 可観測性
- [Prometheus](https://prometheus.io/)
- [Grafana / Loki / Tempo / Mimir](https://grafana.com/)
- [OpenTelemetry](https://opentelemetry.io/)
- [Pyrra (SLO)](https://github.com/pyrra-dev/pyrra)
- [Sloth (SLO)](https://sloth.dev/)

### セキュリティ
- [Kyverno](https://kyverno.io/)
- [OPA Gatekeeper](https://open-policy-agent.github.io/gatekeeper/)
- [Falco](https://falco.org/)
- [Trivy](https://trivy.dev/)
- [cosign / Sigstore](https://www.sigstore.dev/)
- [External Secrets Operator](https://external-secrets.io/)
- [Sealed Secrets](https://sealed-secrets.netlify.app/)

### Service Mesh
- [Istio](https://istio.io/)
- [Linkerd](https://linkerd.io/)
- [Cilium](https://cilium.io/)

### Operator
- [CloudNativePG](https://cloudnative-pg.io/)
- [Strimzi (Kafka)](https://strimzi.io/)
- [prometheus-operator](https://prometheus-operator.dev/)
- [kubebuilder](https://kubebuilder.io/) — Operator自作の標準
- [kopf](https://kopf.readthedocs.io/) — Pythonで自作

### 開発・運用ツール
- [k9s](https://k9scli.io/) — TUI
- [Lens](https://k8slens.dev/) — IDE
- [Headlamp](https://headlamp.dev/) — OSS UI
- [Stern](https://github.com/stern/stern) — マルチPodログ
- [kubectx / kubens](https://github.com/ahmetb/kubectx)
- [krew](https://krew.sigs.k8s.io/) — kubectl plugin manager

## ベンチマーク・標準

- [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
- [kube-bench](https://github.com/aquasecurity/kube-bench)
- [SLSA](https://slsa.dev/) — サプライチェーンセキュリティ
- [12-Factor App](https://12factor.net/)

## 練習問題集

- [Killer.sh](https://killer.sh/) — CKAD/CKA/CKS の模擬試験
- [Kubernetes the Hard Way (Kelsey Hightower)](https://github.com/kelseyhightower/kubernetes-the-hard-way) — 自分でクラスタを組む
- [Awesome Kubernetes](https://github.com/ramitsurana/awesome-kubernetes) — リソース集

## 認定資格

- **CKA** (Certified Kubernetes Administrator) — クラスタ運用
- **CKAD** (Certified Kubernetes Application Developer) — アプリ開発
- **CKS** (Certified Kubernetes Security Specialist) — セキュリティ
- **KCNA** (Kubernetes and Cloud Native Associate) — 入門
