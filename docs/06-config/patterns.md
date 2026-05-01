---
title: 設計パターン
parent: 06. 設定とSecret
nav_order: 3
---

# 設計パターン
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

ConfigMap / Secret の使い方そのものは簡単ですが、**実運用で破綻しない設計** にするにはいくつかのパターンを押さえる必要があります。

## パターン1: 環境差異の扱い

dev / stg / prod で違う値はどう持つか。

選択肢:

1. **環境ごとにConfigMapを用意** (Namespace分離)
   - シンプル。ただし共通設定の重複に注意
2. **Helmでvaluesを切替**
   - `values-dev.yaml`, `values-prod.yaml` で差分管理
3. **Kustomizeでoverlays**
   - `base` + `overlays/dev`, `overlays/prod`

本教材では Helm と Kustomize の両方を 7 章で扱います。

## パターン2: 設定の更新を反映させる

ConfigMap / Secret を更新しても、**Pod の環境変数は再起動しないと反映されない**。

選択肢:

1. **Volume マウント + アプリ側でファイル監視** (ホットリロード)
2. **`kubectl rollout restart deploy/app`** で再起動
3. **annotations にハッシュを埋め込んで自動再起動** (Helm `sha256sum` 関数)

```yaml
spec:
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
```

ConfigMap が変わると annotation も変わり、Pod が再作成されるトリック。Helm でよく使う。

## パターン3: 機密情報の管理場所

「Secret に書いて apply」だけだと、**YAML をリポジトリに置いた瞬間平文で漏れる** 問題がある。

| 方法 | 概要 | 学習用 | 本番用 |
|------|------|--------|--------|
| Secret 直書き | YAMLにbase64で埋め込む | △ | ✗ |
| .env をローカル管理して `kubectl create` | リポジトリには入れない | ◯ | △ |
| Sealed Secrets | 公開鍵で暗号化、リポジトリ可 | ◯ | ◯ |
| External Secrets Operator | Vault/AWS Secrets Manager から動的取得 | ◯ | ◎ |
| SOPS + Helm Secrets | SOPS暗号化したvalues.yamlをcommit | ◯ | ◯ |

10章 [Secret管理]({{ '/10-security/secret-management/' | relative_url }}) で実装まで踏み込みます。

## パターン4: 12-Factor App との整合

[The Twelve-Factor App](https://12factor.net/) は次のように述べています:

> III. 設定 ─ 設定を環境変数に格納する

Kubernetes の ConfigMap / Secret はこの考え方と相性が良いです。

- アプリは環境変数経由で設定を読む
- イメージは不変、設定だけ環境ごとに差し替え
- `imagePullPolicy: Always` で最新を取りに行く必要がない構成にできる

## パターン5: 「設定」と「機密」の境界線

何を ConfigMap、何を Secret に入れるか:

| 例 | 分類 |
|----|------|
| ログレベル、タイムアウト値、機能フラグ | ConfigMap |
| DB ホスト名、Service URL | ConfigMap |
| DB ユーザー名 | ConfigMap (組織方針による) |
| DB パスワード | Secret |
| API トークン、JWT 鍵 | Secret |
| TLS 証明書/秘密鍵 | Secret |

**判断に迷ったら Secret に入れる** が安全側。

## チェックポイント

- [ ] 環境差異の扱いを 3 通り挙げられる
- [ ] ConfigMap 更新時に Pod を自動再起動させる方法
- [ ] サンプルアプリの設定値を ConfigMap と Secret に分類できる
