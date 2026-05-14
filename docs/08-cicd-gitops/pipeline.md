---
title: CIパイプライン
parent: 08. CI/CDとGitOps
nav_order: 1
---

# CIパイプライン
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## このページのゴール

このページを読み終えると、以下を **自分の言葉で説明できる** ようになります。

- CI が何を解決するために生まれたか、歴史的経緯を含めて説明できる
- GitHub Actions の workflow / job / step / action / runner の関係を図示できる
- CI で必ず実装すべき品質ゲート (lint / test / build / scan / sign) を 5 つ以上挙げ、それぞれのツールを答えられる
- イメージタグに `latest` を使わない技術的根拠と、推奨される命名規則を 3 つ挙げられる
- アプリリポジトリとマニフェストリポジトリを分離する利点と、CI から後者を更新する仕組みを説明できる
- CI のセキュリティリスク (Supply Chain Attack) の代表例と、その緩和策を答えられる
- 失敗したワークフローを切り分ける手順を、ありがちなエラーごとに説明できる

---

## CI が解決する問題: 統合地獄からの脱出

### 統合地獄 (Integration Hell) とは

1990 年代、ソフトウェア開発の現場では「**統合地獄**」と呼ばれる現象が頻発していました。

```mermaid
gantt
    title 統合地獄の典型的なタイムライン (1990年代)
    dateFormat YYYY-MM-DD
    section 開発者A
    機能Aを実装 :a1, 2024-01-01, 60d
    section 開発者B
    機能Bを実装 :b1, 2024-01-01, 60d
    section 開発者C
    機能Cを実装 :c1, 2024-01-01, 60d
    section 統合フェーズ
    マージ衝突解決 :crit, m1, 2024-03-01, 30d
    結合テスト :crit, m2, after m1, 20d
    リリース :milestone, after m2, 0d
```

3 人の開発者がそれぞれ 2 ヶ月間独立に作業し、最後の 1 ヶ月を全員でマージ作業と結合テストに費やす。これが「統合地獄」です。

この問題に対し、 **Kent Beck** が 1996 年に提唱した **Extreme Programming (XP)** の中で「Continuous Integration」が解として登場します。彼の主張は単純明快でした。

> 「全員が、少なくとも1日に1回は、共通のメインラインに統合せよ」

これを支える技術的プラクティスが以下です。

| プラクティス | 目的 |
|-------------|------|
| バージョン管理 | 全員が同じ場所で作業 |
| 自動ビルド | 「自分の環境では動く」を排除 |
| 自動テスト | 統合直後に壊れたかを即検知 |
| ビルド失敗時の即時対応 | red を緑にするまで他の作業をしない |

### Jenkins の登場と「Jenkinsfile 暗黒時代」

2005 年、Sun Microsystems の **川口耕介** 氏が **Hudson** を公開しました。当初は単純な GUI ベースの CI サーバでしたが、 **プラグインアーキテクチャ** によって急速に普及します。

2011 年に Oracle との商標問題で **Jenkins** にフォークされ、現在も多くの組織で使われています。

しかし Jenkins の時代には以下の問題がありました。

| 問題 | 内容 |
|------|------|
| プラグイン依存 | 数千あるプラグインのバージョン管理が地獄 |
| `Jenkinsfile` の Groovy | 言語仕様が複雑、デバッグ困難 |
| マスター/エージェントの管理 | サーバを自前で運用する必要がある |
| 設定 GUI と Pipeline as Code の混在 | 「ジョブの定義」が一箇所にない |

### SaaS CI の台頭

2011 年に **Travis CI** が登場し、OSS プロジェクトに無料で CI を提供しました。続いて **CircleCI** (2011)、 **GitLab CI** (2013)、 **GitHub Actions** (2018) と続きます。

これらに共通する設計思想:

1. **設定は YAML でリポジトリに置く** (Pipeline as Code)
2. **イベントドリブン** (push / PR / tag / schedule)
3. **コンテナベースの実行環境** (再現性の担保)
4. **マーケットプレイス** (再利用可能な部品)

```mermaid
flowchart LR
    subgraph "Jenkins時代"
    j1[Jenkins サーバ<br/>自前運用] -->|定期 poll| g1[Git]
    end
    subgraph "GitHub Actions時代"
    g2[GitHub] -->|webhook| r1[Runner]
    r1 -->|結果| g2
    end
```

### なぜ GitHub Actions を本教材で使うか

| 選択肢 | メリット | デメリット |
|--------|---------|-----------|
| **GitHub Actions** | リポジトリと一体、無料枠が大きい、Marketplace 充実 | GitHub に依存 |
| GitLab CI | GitLab を使うなら一択、Auto DevOps 強力 | GitLab セルフホスト or .com 必要 |
| Jenkins | 完全自前運用可能、プラグイン豊富 | サーバ管理の重さ |
| CircleCI | 並列性能が高い、設定が直感的 | OSS 以外は有料 |
| Drone | 軽量、Go 製で OSS | エコシステムが小さい |
| Tekton | Kubernetes ネイティブ、CRD 設計 | 学習コスト高、UI 弱い |

本教材では「ローカル完結」「学習コストの低さ」「無料枠の広さ」から GitHub Actions を選びます。

ただし、 **本番運用では Tekton + Argo Workflows のように、Kubernetes 上で動く CI** に魅力があります。クラスタの中で全部完結し、シークレット管理も一元化できるからです。これは発展課題として最後に触れます。

---

## GitHub Actions のメンタルモデル

### 用語の階層

```mermaid
flowchart TB
    repo[Repository] --> wf1[Workflow A<br/>.github/workflows/ci.yaml]
    repo --> wf2[Workflow B<br/>.github/workflows/release.yaml]
    wf1 --> job1[Job: test]
    wf1 --> job2[Job: build-push]
    job1 --> s1[Step 1: checkout]
    job1 --> s2[Step 2: setup-python]
    job1 --> s3[Step 3: pytest]
    s2 --> act[Action: actions/setup-python@v5]
    job1 --> runner[Runner: ubuntu-latest]
```

| 概念 | 定義 |
|------|------|
| **Workflow** | 1 つの YAML ファイル。トリガとジョブの集合 |
| **Event** | Workflow を起動する出来事 (push, PR, schedule など) |
| **Job** | 1 つの runner 上で連続実行されるステップ群 |
| **Step** | shell コマンドか Action の呼び出し |
| **Action** | 再利用可能な処理単位 (Docker Action, JavaScript Action, Composite Action) |
| **Runner** | 実際にジョブを実行するマシン (GitHub-hosted or Self-hosted) |

### 1ファイルの最小構造

```yaml
# .github/workflows/hello.yaml
name: hello                     # workflow 名 (UI表示用)
on: [push]                      # トリガ

jobs:
  greet:                        # job ID
    runs-on: ubuntu-latest      # runner
    steps:                      # 実行単位の列
      - run: echo "Hello, CI"   # shell コマンド
      - uses: actions/checkout@v4  # action 呼び出し
```

これだけで動きます。`run` は shell 実行、`uses` は再利用部品呼び出し。

### Runner の種類

| 種類 | 用途 | 料金 |
|------|------|------|
| **GitHub-hosted (ubuntu-latest)** | 通常用途 | public repo は無料、private は分単位課金 (2 vCPU で 1x) |
| **GitHub-hosted (large)** | 重いビルド | 高い (4/8/16/32/64 core 選択可) |
| **GitHub-hosted (windows/macos)** | クロスプラットフォーム | macOS は特に高い (10x) |
| **Self-hosted** | 自前マシン、ローカルネットワーク必要 | サーバ代のみ |

本教材では大半 `ubuntu-latest` を使いますが、 **ローカルレジストリ (192.168.56.10:5000) に push したい場合のみ Self-hosted Runner を VMware 環境内に1台立てます**。

### トリガ (Event) の種類

`on:` に指定できる主要なトリガ。

| トリガ | 説明 | 主な用途 |
|--------|------|---------|
| `push` | コミット push 時 | main へのマージで本番デプロイ |
| `pull_request` | PR の作成/更新時 | PR 上でテスト |
| `workflow_dispatch` | UI から手動実行 | 手動デプロイ、リリース作業 |
| `schedule` | cron 式 | nightly build、定期スキャン |
| `release` | release 作成時 | リリース成果物の生成 |
| `workflow_call` | 別 workflow から呼ばれた時 | 再利用可能 workflow |
| `repository_dispatch` | 外部 API から webhook | CD パイプラインからの逆呼び出し |

```yaml
on:
  push:
    branches: [main]              # main 限定
    paths: ['src/**', 'Dockerfile']  # このパスが変わった時のみ
  pull_request:
    branches: [main]
    paths-ignore: ['docs/**']      # ドキュメントだけの変更は無視
  schedule:
    - cron: '0 3 * * *'            # 毎日 3:00 UTC
  workflow_dispatch:
    inputs:
      environment:
        description: 'デプロイ先環境'
        required: true
        default: 'dev'
        type: choice
        options: [dev, stg, prod]
```

`paths` / `paths-ignore` の活用は重要です。例えば README だけ更新したのにフルビルドが走るのは無駄なので、 **テスト対象に関係ないパスは ignore する** のが定石です。

### Context と Expression

`${{ }}` 内では JavaScript ライクな式が書けます。

```yaml
- name: 条件付き実行
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: echo "main へのpushです"

- name: 環境変数の利用
  run: echo "SHA: ${{ github.sha }}"
  env:
    COMMIT_MSG: ${{ github.event.head_commit.message }}
```

主要な context:

| context | 内容例 |
|---------|--------|
| `github` | `github.sha`, `github.ref`, `github.actor`, `github.event_name` |
| `env` | workflow / job / step レベルの環境変数 |
| `secrets` | リポジトリの Secrets |
| `vars` | リポジトリの Variables (非機密) |
| `inputs` | workflow_dispatch / workflow_call の入力 |
| `needs` | 依存ジョブの outputs |
| `matrix` | matrix 戦略の現在値 |
| `runner` | runner 情報 (OS, arch) |

---

## CI/CD の責務分担を再確認

```mermaid
flowchart LR
    dev[開発者] -->|push| app[appリポジトリ<br/>todo-app]
    app -->|GitHub Actions| ci[CI]
    ci -->|build/test/scan| reg[(Registry<br/>GHCR)]
    ci -->|tag更新コミット| manifest[manifestリポジトリ<br/>todo-manifests]
    manifest -->|Argo CD watch| k8s[K8s クラスタ]
    k8s -->|status| argo[Argo CD]
    argo -->|UI/notify| dev
```

- **CI**: ビルド、テスト、スキャン、イメージ push、 **マニフェストリポジトリ更新**
- **CD**: マニフェスト変更を検知してクラスタに反映 (Argo CD)

### CI と CD の境界線

「Continuous Delivery」と「Continuous Deployment」の違いに注目してください。

| 用語 | 何を意味するか | 本教材での実装 |
|------|--------------|--------------|
| Continuous Integration | コード統合とビルド・テスト | GitHub Actions の test/build ジョブ |
| Continuous Delivery | 「いつでもデプロイできる状態」を保つ。最終リリースは人間 | manifest repo 更新 + 手動 sync |
| Continuous Deployment | テスト通過後、人間の介入なしに本番反映 | manifest repo 更新 + Argo CD selfHeal |

本教材の最終形は Continuous Deployment ですが、本番では Continuous Delivery (人間承認あり) で運用するのが一般的です。

---

## なぜリポジトリを分けるか (App vs Manifest)

歴史的経緯では混在もありましたが、現代の GitOps では **分離が定石** です。理由を深掘りします。

### 1. デプロイ履歴 = manifest repo の git log

アプリのコードは頻繁に変わりますが、マニフェスト変更は「本番に何が反映されたか」と1対1対応します。
manifest repo の `git log` を見れば、本番に何がいつ入ったかが一目瞭然です。

```bash
# manifest repo で
git log --oneline overlays/prod/
# a3f2c1b deploy: todo-api 2024-01-15-a3f2c1b
# 9b8e7d4 deploy: todo-frontend 2024-01-15-9b8e7d4
# 4c5d6e7 chore: bump postgres 16.1 -> 16.2
```

### 2. 権限分離

| リポジトリ | 触る人 | 必要な権限 |
|----------|--------|----------|
| app repo | アプリ開発者 | コード書き換え |
| manifest repo | SRE / リードエンジニア | 本番設定変更 |

開発者全員に本番マニフェストへの直接書き込み権限を与えなくて済みます。CI bot だけが書き込めるように設定できます。

### 3. アプリの CI とインフラの CD の進化速度を分けられる

- アプリ: 毎日リリースしたい
- インフラ: Helm chart のバージョン上げは慎重に

それぞれのリポジトリで独立して進化させられます。

### 4. ロールバック容易性

`git revert` を manifest repo で打てば、即時前のバージョンに戻ります。app repo の変更を revert する必要がありません (= 既にビルド済みのイメージを再利用)。

### 5. 複数アプリの統合管理

複数のマイクロサービスを一括で「本番環境」として管理できます。

```
todo-manifests/
├── apps/
│   ├── todo-api/
│   ├── todo-frontend/
│   ├── todo-worker/
│   └── postgres/
└── overlays/
    ├── dev/
    ├── stg/
    └── prod/
```

### 反論: モノレポでも良いのでは?

一部の組織 (Google, Meta) はモノレポを採用しています。1 つのリポジトリにコードもマニフェストも入る方式です。

| 方式 | メリット | デメリット |
|------|---------|-----------|
| モノレポ | 全体のアトミックな変更可、リファクタしやすい | リポジトリ巨大化、ツール特殊 |
| 分離 (本教材) | 権限分離、デプロイ履歴明瞭、ツール標準的 | 複数リポジトリの同期に注意 |

本教材は学習目的かつ標準的なパターンとして **分離** を採用します。

```
github.com/<USER>/todo-app          # コード + Dockerfile + GitHub Actions
github.com/<USER>/todo-manifests    # K8s YAML (Helm/Kustomize)
```

---

## サンプルアプリのリポジトリ構造

### todo-app リポジトリ

```
todo-app/
├── .github/
│   └── workflows/
│       ├── ci.yaml          # PR / main へのpush
│       └── release.yaml     # tag push 時
├── api/                     # FastAPI コード
│   ├── pyproject.toml
│   ├── src/todo_api/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── ...
│   └── tests/
├── frontend/                # 静的HTML/JS
│   └── ...
├── worker/                  # 通知 Worker
│   └── ...
├── Dockerfile.api
├── Dockerfile.frontend
├── Dockerfile.worker
└── README.md
```

### todo-manifests リポジトリ

```
todo-manifests/
├── base/                    # Kustomize base
│   ├── kustomization.yaml
│   ├── api-deployment.yaml
│   ├── api-service.yaml
│   ├── frontend-deployment.yaml
│   ├── postgres-statefulset.yaml
│   ├── redis-statefulset.yaml
│   └── ingress.yaml
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml
│   │   └── values.yaml      # 環境固有の値
│   ├── stg/
│   └── prod/
└── README.md
```

ここで `overlays/<env>/values.yaml` の中に **イメージタグ** を書きます。CI はこの値を書き換えてコミットします。

```yaml
# overlays/prod/values.yaml
api:
  image:
    repository: ghcr.io/your-user/todo-api
    tag: 2024-01-15-a3f2c1b
frontend:
  image:
    repository: ghcr.io/your-user/todo-frontend
    tag: 2024-01-15-a3f2c1b
worker:
  image:
    repository: ghcr.io/your-user/todo-worker
    tag: 2024-01-15-a3f2c1b
```

---

## CI パイプラインの全体像

これから構築する CI ワークフローの全ステージを俯瞰します。

```mermaid
flowchart TB
    start([push / PR]) --> chk[checkout]
    chk --> lint[Lint<br/>ruff / hadolint / kubeconform]
    lint --> sec1[Secret scan<br/>gitleaks]
    sec1 --> test[Unit & Integration Test<br/>pytest]
    test --> sbom1[依存関係 SBOM<br/>syft]
    test --> build[Build image<br/>docker buildx]
    build --> scan[Image scan<br/>Trivy]
    scan --> sign[Image sign<br/>cosign]
    sign --> push[Push to GHCR]
    push --> attest[SLSA attestation]
    attest --> mfup[manifest repo の<br/>image.tag を更新]
    mfup --> commit[git commit & push<br/>to todo-manifests]
    commit --> done([Argo CD が検知])

    style lint fill:#bbf
    style sec1 fill:#fbb
    style test fill:#bbf
    style build fill:#bfb
    style scan fill:#fbb
    style sign fill:#fbb
    style push fill:#bfb
    style mfup fill:#ffb
```

各ステージごとに詳しく見ていきます。

---

## ステージ1: Checkout

最初に必ず実行するステージです。`actions/checkout` を使います。

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0           # 全履歴を取得 (デフォルトは 1)
    submodules: recursive    # サブモジュールも展開
    lfs: false               # Git LFS を使う場合は true
    token: ${{ secrets.GITHUB_TOKEN }}  # 別 repo を checkout するときは PAT
```

### `fetch-depth` の指定

| 値 | 用途 |
|----|------|
| `1` (デフォルト) | 通常のテスト・ビルドはこれで十分。高速 |
| `0` | 全履歴。バージョン番号生成 (`git describe`) や差分テストで必要 |
| `N` | 直近 N コミットだけ。`fetch-depth: 0` が重い時の妥協案 |

### よくあるトラブル

| 症状 | 原因 | 対処 |
|------|------|------|
| `fatal: not a git repository` | checkout なしで `git` コマンドを使った | 最初に `actions/checkout` を実行 |
| `fatal: tag describes nothing` | `fetch-depth: 1` でタグが取れない | `fetch-depth: 0` に変更 |
| `Permission denied` (private repo) | `GITHUB_TOKEN` の権限不足 | `permissions: contents: read` を追加、または PAT |

---

## ステージ2: Lint と静的解析

「CI を緑にするのは難しい」というルールを最大限に活用するため、 **失敗しやすいチェックを最初に置きます**。

### Python: ruff

```yaml
- name: Lint (ruff)
  run: |
    pip install ruff==0.4.10
    ruff check api/
    ruff format --check api/
```

`ruff` は Python の lint/format ツールで、 **flake8/black/isort を Rust で書き直したもの** です。圧倒的に高速 (10〜100倍)。

オプション詳細:
- `ruff check`: lint 実行
- `ruff format --check`: フォーマット差分があれば失敗 (`--check` なしで適用)
- `--fix`: 自動修正可能なものを修正
- `--select E,W,F,B,I`: ルール選択 (E=pycodestyle, W=warning, F=pyflakes, B=bugbear, I=isort)

### Dockerfile: hadolint

```yaml
- name: Lint Dockerfile
  uses: hadolint/hadolint-action@v3.1.0
  with:
    dockerfile: Dockerfile.api
    failure-threshold: warning
```

`hadolint` は Dockerfile の lint。ベストプラクティス違反 (latest タグ使用、root で実行など) を検出。

代表的なルール:
| ルール ID | 内容 |
|----------|------|
| DL3007 | `latest` タグの使用 |
| DL3008 | `apt-get install` でバージョン固定なし |
| DL3009 | `apt-get install` 後の `apt-get clean` なし |
| DL3025 | `CMD` に shell 形式を使用 (exec 形式推奨) |
| DL4006 | `SHELL` で pipefail オプションなし |

### Kubernetes マニフェスト: kubeconform / kube-linter

```yaml
- name: Validate K8s manifests
  run: |
    curl -L https://github.com/yannh/kubeconform/releases/download/v0.6.6/kubeconform-linux-amd64.tar.gz | tar xz
    ./kubeconform -summary -strict -kubernetes-version 1.30.0 manifests/
```

`kubeconform` は K8s YAML を OpenAPI スキーマで検証します。`kubectl apply --dry-run=server` のローカル版。

| ツール | 役割 |
|-------|------|
| `kubeconform` | スキーマ検証 (構文・型) |
| `kube-linter` | ベストプラクティス検証 (権限、リソース要求) |
| `kubeval` | (旧) スキーマ検証。kubeconform にメンテ移行 |
| `polaris` | セキュリティ・信頼性のポリシーチェック |
| `datree` | ポリシーエンジン (商用) |

### Helm chart: helm lint

```yaml
- name: Helm lint
  run: |
    helm lint charts/todo
    helm template charts/todo | kubeconform -strict -summary
```

`helm template` で YAML 展開し、`kubeconform` に通すコンボが定番。

---

## ステージ3: Secret スキャン (gitleaks)

「うっかり API キーをコミット」を防ぎます。

```yaml
- name: Secret scan
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}  # private repo は必要
```

検出されると以下のように出ます:

```
Finding:     password=hunter2
Secret:      hunter2
File:        api/config.py
Line:        42
Commit:      a3f2c1b
RuleID:      generic-api-key
```

検出後の対応:
1. 該当行を削除してコミット
2. **git 履歴からも消す** (`git filter-repo` or BFG)
3. 該当シークレットを即時無効化 (これが一番大事)

{: .warning }
> 公開リポジトリでシークレットを誤コミットしたら、 **削除しても残ります**。GitHub の自動 secret scanning が動いて、AWS や GitHub PAT は自動で revoke されることもありますが、それ以外は手動で無効化必須。

---

## ステージ4: テスト

### 単体テスト (pytest)

```yaml
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
        cache: 'pip'                   # pip cache を自動管理
    - name: Install
      run: |
        pip install --upgrade pip
        pip install -e api/[test]
    - name: Run pytest
      run: |
        cd api
        pytest \
          --cov=todo_api \
          --cov-report=xml \
          --cov-report=term \
          --junitxml=junit.xml \
          -v
    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        file: api/coverage.xml
    - name: Publish test report
      uses: mikepenz/action-junit-report@v4
      if: always()
      with:
        report_paths: 'api/junit.xml'
```

### 結合テスト (testcontainers)

PostgreSQL や Redis を本物で動かしてテストする例:

```yaml
- name: Integration test
  run: |
    cd api
    pytest tests/integration -v
  env:
    POSTGRES_URL: postgresql://test:test@localhost:5432/test
  services:
    postgres:
      image: postgres:16-alpine
      env:
        POSTGRES_PASSWORD: test
        POSTGRES_USER: test
        POSTGRES_DB: test
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
      ports:
        - 5432:5432
```

`services:` で起動した PostgreSQL は `localhost:5432` で参照できます。GitHub Actions が裏で Docker network を作ってくれます。

### マトリックステスト

複数の Python バージョンで同じテストを走らせるとき:

```yaml
strategy:
  fail-fast: false      # 1つ失敗しても他を続行
  matrix:
    python: ['3.11', '3.12', '3.13']
    os: [ubuntu-latest, macos-latest]
    exclude:
      - os: macos-latest
        python: '3.13'  # この組み合わせはスキップ
steps:
  - uses: actions/setup-python@v5
    with:
      python-version: ${{ matrix.python }}
```

これで 3×2-1 = 5 ジョブが並列実行されます。

---

## ステージ5: Docker イメージビルド

### Dockerfile のベストプラクティス

`Dockerfile.api` の良い例:

```dockerfile
# 1. ベースは具体的なバージョン指定 (latest 禁止)
FROM python:3.12.4-slim-bookworm AS builder

# 2. 依存だけ先にインストールしてキャッシュ効かせる
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user .

# 3. その後にソースをコピー
COPY src/ ./src/

# 4. multi-stage build で最終イメージを小さく
FROM python:3.12.4-slim-bookworm
RUN useradd -m -u 1000 -s /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /root/.local /home/app/.local
COPY --from=builder /app/src ./src
USER app
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["uvicorn", "todo_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile 各命令の意味と注意

| 命令 | 役割 | 注意点 |
|------|------|-------|
| `FROM` | ベースイメージ | 必ずバージョン固定、可能なら digest 固定 (`@sha256:...`) |
| `WORKDIR` | 作業ディレクトリ | `cd` の代わり。レイヤーを作らない |
| `COPY` | ファイルコピー | `.dockerignore` で除外を必須 |
| `RUN` | コマンド実行 | `&&` で繋いで1レイヤーにまとめる |
| `ENV` | 環境変数 | 後続レイヤーに残る。秘密情報を入れない |
| `USER` | 実行ユーザ | root 禁止。事前に `useradd` する |
| `HEALTHCHECK` | ヘルスチェック | K8s では readinessProbe を使うが、ローカル用には便利 |
| `EXPOSE` | ポート宣言 | ドキュメント目的のみ。実際の公開は K8s Service |
| `CMD` / `ENTRYPOINT` | 起動コマンド | `exec` 形式 (`["cmd","arg"]`) で書く |

### buildx を使ったビルド

`docker build` ではなく `docker buildx build` を使うと、クロスプラットフォーム (amd64/arm64) と高度なキャッシュが使えます。

```yaml
build-push:
  runs-on: ubuntu-latest
  permissions:
    contents: read
    packages: write              # GHCR への push
    id-token: write              # OIDC (cosign 用)
  steps:
    - uses: actions/checkout@v4

    - name: Set up QEMU            # arm64 もビルドする場合
      uses: docker/setup-qemu-action@v3

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Login to GHCR
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Set tag
      id: tag
      run: |
        DATE=$(date -u +%Y%m%d)
        SHA=$(git rev-parse --short HEAD)
        echo "tag=${DATE}-${SHA}" >> $GITHUB_OUTPUT
        echo "sha=${SHA}" >> $GITHUB_OUTPUT

    - name: Build and push
      id: build
      uses: docker/build-push-action@v6
      with:
        context: .
        file: Dockerfile.api
        platforms: linux/amd64,linux/arm64
        push: true
        tags: |
          ghcr.io/${{ github.repository_owner }}/todo-api:${{ steps.tag.outputs.tag }}
          ghcr.io/${{ github.repository_owner }}/todo-api:latest
        labels: |
          org.opencontainers.image.source=${{ github.event.repository.html_url }}
          org.opencontainers.image.revision=${{ github.sha }}
          org.opencontainers.image.version=${{ steps.tag.outputs.tag }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
        provenance: true
        sbom: true
```

### `docker/build-push-action` の主要パラメータ

| パラメータ | 意味 |
|-----------|------|
| `context` | ビルドコンテキスト (デフォルト `.`) |
| `file` | Dockerfile のパス |
| `platforms` | クロスビルドの対象 |
| `push` | レジストリへ push するか |
| `tags` | 付与するタグ (改行区切りで複数可) |
| `labels` | OCI ラベル (後述) |
| `cache-from` / `cache-to` | レイヤーキャッシュ |
| `build-args` | ARG で渡す変数 |
| `secrets` | BuildKit secret (`--mount=type=secret`) |
| `provenance` | SLSA Provenance attestation |
| `sbom` | SBOM (Software Bill of Materials) 生成 |

### OCI ラベルの推奨

OCI Image Spec で標準化されたラベルがあります。これらを付けると `docker inspect` や Argo CD UI で情報が見えます。

```dockerfile
LABEL org.opencontainers.image.title="todo-api" \
      org.opencontainers.image.description="TODO アプリの API" \
      org.opencontainers.image.source="https://github.com/USER/todo-app" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="USER" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"
```

仕様: <https://github.com/opencontainers/image-spec/blob/main/annotations.md>

### キャッシュ戦略

ビルドが遅い最大の原因はキャッシュ未活用です。

```mermaid
flowchart LR
    src[ソースコード変更] --> rebuild
    dep[依存変更] --> rebuild
    rebuild[再ビルド] --> push
    nochange[変更なし] --> cache[キャッシュヒット]
    cache --> push
```

#### 1. GHA キャッシュ (推奨、本教材)

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

GitHub Actions の標準キャッシュを使う。10GB まで無料。

`mode=max` は中間レイヤーも含めてキャッシュ (デフォルトは最終レイヤーのみ)。

#### 2. レジストリキャッシュ

```yaml
cache-from: type=registry,ref=ghcr.io/.../todo-api:buildcache
cache-to: type=registry,ref=ghcr.io/.../todo-api:buildcache,mode=max
```

ビルドキャッシュ自体をレジストリに保存。サイズ制限がない。

#### 3. inline キャッシュ

```yaml
cache-from: type=registry,ref=ghcr.io/.../todo-api:latest
cache-to: type=inline
```

イメージ自体にキャッシュメタデータを埋め込む。最も簡単だがキャッシュ効率はやや劣る。

### Dockerfile レイヤー最適化のテクニック

依存関係を先に COPY して RUN するのが基本:

```dockerfile
# 悪い例: ソース変更でも依存再インストール
COPY . .
RUN pip install .

# 良い例: 依存ファイルだけ先にコピー
COPY pyproject.toml ./
RUN pip install .
COPY src/ ./src/
```

これだけでビルド時間が劇的に変わります。

### BuildKit の `--mount=type=cache`

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .
```

pip のキャッシュを永続化。同じ依存なら再 download しません。

### `--mount=type=secret` でビルド時シークレット

```dockerfile
RUN --mount=type=secret,id=npm_token \
    NPM_TOKEN=$(cat /run/secrets/npm_token) npm install
```

```yaml
- uses: docker/build-push-action@v6
  with:
    secrets: |
      "npm_token=${{ secrets.NPM_TOKEN }}"
```

`ENV` や `ARG` でシークレットを渡すと **イメージレイヤーに残って漏洩** します。必ず `--mount=type=secret` を使いましょう。

---

## ステージ6: 脆弱性スキャン (Trivy)

ビルドしたイメージに既知の脆弱性 (CVE) があれば失敗させます。

```yaml
- name: Run Trivy
  uses: aquasecurity/trivy-action@0.24.0
  with:
    image-ref: ghcr.io/${{ github.repository_owner }}/todo-api:${{ steps.tag.outputs.tag }}
    format: 'sarif'
    output: 'trivy-results.sarif'
    severity: 'CRITICAL,HIGH'
    exit-code: '1'                # CRITICAL/HIGH があれば失敗
    ignore-unfixed: true          # 修正版がない CVE は無視
    vuln-type: 'os,library'
    timeout: '10m'

- name: Upload Trivy results to GitHub Security
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: 'trivy-results.sarif'
```

| パラメータ | 意味 |
|----------|------|
| `severity` | 検出する重要度 (UNKNOWN, LOW, MEDIUM, HIGH, CRITICAL) |
| `exit-code` | 検出時の終了コード。0 ならジョブ続行、1 で失敗 |
| `ignore-unfixed` | 修正パッチが出ていない CVE を無視 (運用上ノイズが減る) |
| `vuln-type` | os = OS パッケージ、library = アプリ依存 |
| `format` | table / json / sarif / template |

### sarif 形式と GitHub Security タブ連携

`sarif` (Static Analysis Results Interchange Format) で出力すると、GitHub の Security タブに表示され、PR でレビュアーが見られます。

```mermaid
flowchart LR
    trivy[Trivy] -->|sarif| sec[GitHub Security]
    sec -->|annotation| pr[PR]
    sec -->|alert| dev[開発者通知]
```

### 代替ツール

| ツール | 特徴 |
|-------|------|
| **Trivy** (Aqua) | OSS、定番、SBOM 対応、脆弱性以外 (IaC, シークレット) もスキャン |
| Grype (Anchore) | Trivy のライバル、Anchore Engine と統合 |
| Snyk | 商用、依存ライブラリスキャンに強い、UI 優秀 |
| Clair (Quay) | 古参、Quay Registry に統合 |
| Docker Scout | Docker Inc. 純正、Docker Desktop に統合 |

---

## ステージ7: SBOM 生成 (syft)

SBOM (Software Bill of Materials) は「このイメージは何で構成されているか」のリストです。
2021 年の Log4j 脆弱性 (Log4Shell) を契機に、米国政府が SBOM 義務化を発表 (大統領令 14028)、業界標準として定着しつつあります。

```yaml
- name: Generate SBOM
  uses: anchore/sbom-action@v0
  with:
    image: ghcr.io/${{ github.repository_owner }}/todo-api:${{ steps.tag.outputs.tag }}
    format: cyclonedx-json
    output-file: sbom.cdx.json
    upload-artifact: true
```

SBOM のフォーマット:
| フォーマット | 推進主体 |
|-------------|---------|
| **SPDX** | Linux Foundation |
| **CycloneDX** | OWASP |

両方とも JSON / YAML / XML 形式に対応。本教材では CycloneDX を使います。

---

## ステージ8: イメージ署名 (cosign)

サプライチェーン攻撃の代表例:

| 事件 | 内容 |
|------|------|
| SolarWinds (2020) | ビルドサーバが侵害され、正規署名されたマルウェアが配布 |
| Codecov (2021) | bash uploader が改ざんされ、顧客の CI 環境変数が流出 |
| ua-parser-js (2021) | npm パッケージが乗っ取られ、マルウェア混入 |
| Log4Shell (2021) | Log4j の RCE 脆弱性、業界全体に影響 |

これらに対し、 **Sigstore** プロジェクト (2021、Linux Foundation) が「イメージに署名し、誰がビルドしたか証明する」仕組みを提供しています。

### cosign による署名

```yaml
- name: Install cosign
  uses: sigstore/cosign-installer@v3

- name: Sign image (keyless, OIDC)
  env:
    COSIGN_EXPERIMENTAL: 1
  run: |
    cosign sign --yes \
      ghcr.io/${{ github.repository_owner }}/todo-api@${{ steps.build.outputs.digest }}
```

`--yes` (旧 `-y`): 確認プロンプトをスキップ
`@${{ steps.build.outputs.digest }}`: 必ず **digest** で署名 (tag は変えられるので)

### Keyless 署名 (OIDC) の仕組み

```mermaid
sequenceDiagram
    participant GHA as GitHub Actions
    participant Fulcio as Sigstore Fulcio
    participant Rekor as Rekor Transparency Log
    participant Reg as Registry

    GHA->>Fulcio: OIDC token (id_token)
    Fulcio->>GHA: 短命の証明書 (10分有効)
    GHA->>GHA: 秘密鍵で署名
    GHA->>Reg: 署名を attach
    GHA->>Rekor: 署名を transparency log に記録
    Reg-->>GHA: 完了
```

| コンポーネント | 役割 |
|-------------|------|
| **Fulcio** | OIDC を信頼して短命な X.509 証明書を発行 |
| **Cosign** | 署名・検証ツール |
| **Rekor** | 不変の透過性ログ。後から「いつ誰が署名したか」を検証できる |

### 検証側 (デプロイ時)

```bash
cosign verify \
  --certificate-identity-regexp="https://github.com/USER/todo-app/.*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/USER/todo-api:2024-01-15-a3f2c1b
```

K8s 側で **Kyverno** や **Sigstore Policy Controller** を使うと、署名されていないイメージの起動を拒否できます。

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-signed-images
spec:
  validationFailureAction: Enforce
  webhookTimeoutSeconds: 30
  rules:
  - name: check-signature
    match:
      any:
      - resources:
          kinds: [Pod]
    verifyImages:
    - imageReferences:
      - "ghcr.io/USER/*"
      attestors:
      - entries:
        - keyless:
            subject: "https://github.com/USER/*"
            issuer: "https://token.actions.githubusercontent.com"
```

---

## ステージ9: SLSA Provenance

SLSA (Supply-chain Levels for Software Artifacts) は Google が提唱し、OpenSSF が標準化した「サプライチェーンの成熟度レベル」です。

| レベル | 内容 |
|------|------|
| SLSA 0 | 何もなし |
| SLSA 1 | ビルドプロセスが自動化されている |
| SLSA 2 | ビルドが特定のサービスで実行 + Provenance 生成 |
| SLSA 3 | ビルド環境の隔離、改ざん防止 |
| SLSA 4 | 二人承認、再現可能ビルド |

GitHub Actions は **SLSA Level 3 Build Provenance** を自動生成できます。

```yaml
- uses: docker/build-push-action@v6
  with:
    # ...
    provenance: mode=max          # 詳細な provenance を生成
    sbom: true
```

`provenance: mode=max` で「どのコミットから、どのワークフローで、いつビルドされたか」を証明する署名付きメタデータが付きます。

---

## ステージ10: イメージタグ戦略

ここまで `2024-01-15-a3f2c1b` のようなタグを使ってきましたが、これは熟考の結果です。

### なぜ `latest` を使ってはいけないか

```mermaid
flowchart TB
    pod1[Pod A<br/>image: app:latest] --> tag1[実体: digest abc123]
    push[新版を push] --> tag2[latest -> digest def456]
    pod2[Pod B<br/>image: app:latest<br/>新規起動] --> tag2
    pod1 -.->|再起動| tag2

    style tag2 fill:#fbb
```

理由:

1. **不変性がない**: 同じ `latest` でも昨日と今日で中身が違う
2. **デプロイの再現性が失われる**: 過去に起きたバグを再現できない
3. **ロールバック不可**: 「前の latest」がもうない
4. **Pod 再起動でも変わる**: 同じ Deployment でも Pod を再作成すると新版を pull する可能性
5. **imagePullPolicy: IfNotPresent との相性が悪い**: ノードによって中身が違う Pod ができうる

### タグ命名規則の選択肢

| 方式 | 例 | メリット | デメリット |
|------|---|---------|-----------|
| **Git SHA short** | `a3f2c1b` | コミットと1対1 | 順序が分からない、ソート不可 |
| **日付 + SHA** (推奨) | `2024-01-15-a3f2c1b` | 時系列も分かる | やや長い |
| **Semver** | `v1.2.3` | バージョン管理しやすい | 自動付与に工夫が必要 |
| **CalVer** | `2024.01.15` | 単純 | 同日複数リリースが面倒 |
| **incrementing** | `42`, `43`... | 単純 | コミットとの紐付けが弱い |

本教材では「日付 + SHA」を採用します。`2024-01-15-a3f2c1b` の形。

### Immutable tags の設定

GHCR は `latest` の上書きを許しますが、過去タグも上書き可能です。
プロジェクト設定で **「タグの immutable 化」** を有効にすると、一度 push したタグは変更不可になります。

### Digest による参照

最も厳密なのは tag ではなく digest で参照すること:

```
ghcr.io/USER/todo-api@sha256:0123456789abcdef...
```

Argo CD や Renovate Bot を使うと自動で digest 化できます。

---

## ステージ11: マニフェストリポジトリの更新

CI の最終ステージは「別のリポジトリにコミットを作る」です。

### Personal Access Token (PAT) によるアクセス

`GITHUB_TOKEN` (workflow が自動取得) は **同じリポジトリ** にしかアクセスできません。別 repo (manifest repo) に書き込むには PAT が必要です。

1. GitHub の Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. 「`todo-manifests` リポジトリへの `contents: write` 権限」だけを持つ token を作成
3. `todo-app` リポジトリの Secrets に `MANIFEST_TOKEN` として登録

### ジョブ実装

```yaml
update-manifest:
  needs: build-push
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  steps:
    - name: Checkout manifest repo
      uses: actions/checkout@v4
      with:
        repository: ${{ github.repository_owner }}/todo-manifests
        token: ${{ secrets.MANIFEST_TOKEN }}
        path: manifests

    - name: Install yq
      run: |
        sudo wget -qO /usr/local/bin/yq \
          https://github.com/mikefarah/yq/releases/download/v4.44.1/yq_linux_amd64
        sudo chmod +x /usr/local/bin/yq

    - name: Update image tag
      working-directory: manifests
      run: |
        yq -i '.api.image.tag = "${{ needs.build-push.outputs.tag }}"' overlays/prod/values.yaml
        yq -i '.api.image.digest = "${{ needs.build-push.outputs.digest }}"' overlays/prod/values.yaml

    - name: Commit and push
      working-directory: manifests
      run: |
        git config user.name "todo-ci-bot"
        git config user.email "ci@example.com"
        git add .
        if git diff --staged --quiet; then
          echo "No changes"
          exit 0
        fi
        git commit -m "deploy(prod): todo-api ${{ needs.build-push.outputs.tag }}

        Source: ${{ github.event.repository.html_url }}/commit/${{ github.sha }}
        Triggered by: ${{ github.actor }}
        "
        git push
```

### jobs 間の output 受け渡し

`build-push` ジョブで決めた tag を `update-manifest` ジョブで使うには `outputs` を使います。

```yaml
build-push:
  outputs:
    tag: ${{ steps.tag.outputs.tag }}
    digest: ${{ steps.build.outputs.digest }}
  steps:
    - id: tag
      run: echo "tag=2024-01-15-${SHA}" >> $GITHUB_OUTPUT
    - id: build
      uses: docker/build-push-action@v6
      # ...

update-manifest:
  needs: build-push
  steps:
    - run: echo "${{ needs.build-push.outputs.tag }}"
```

### PR ベースの更新 (本番では推奨)

自動 commit ではなく PR を作る方式もあります。

```yaml
- uses: peter-evans/create-pull-request@v6
  with:
    token: ${{ secrets.MANIFEST_TOKEN }}
    path: manifests
    commit-message: "deploy(prod): todo-api ${{ needs.build-push.outputs.tag }}"
    branch: deploy/todo-api-${{ needs.build-push.outputs.tag }}
    title: "Deploy todo-api ${{ needs.build-push.outputs.tag }}"
    body: |
      自動生成された本番デプロイ PR
      - イメージ: `ghcr.io/.../todo-api:${{ needs.build-push.outputs.tag }}`
      - ソース: ${{ github.sha }}
    reviewers: sre-team
```

「dev/stg は自動マージ、prod は人間レビュー」のような運用に切り替えるとき、これが効きます。

---

## 完成形 (全ステージ統合 workflow)

ここまでの全ステージを統合した本格的な workflow です。
`.github/workflows/ci.yaml`:

```yaml
name: CI

on:
  push:
    branches: [main]
    paths:
      - 'api/**'
      - 'Dockerfile.api'
      - '.github/workflows/ci.yaml'
  pull_request:
    branches: [main]
    paths:
      - 'api/**'
      - 'Dockerfile.api'

permissions:
  contents: read

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/todo-api

jobs:
  # ============ 静的解析 ============
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install ruff
        run: pip install ruff==0.4.10

      - name: Ruff check
        run: ruff check api/

      - name: Ruff format check
        run: ruff format --check api/

      - name: Hadolint
        uses: hadolint/hadolint-action@v3.1.0
        with:
          dockerfile: Dockerfile.api
          failure-threshold: warning

      - name: Gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # ============ テスト ============
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_USER: test
          POSTGRES_DB: test
        ports: [5432:5432]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
      redis:
        image: redis:7-alpine
        ports: [6379:6379]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install
        working-directory: api
        run: |
          pip install --upgrade pip
          pip install -e .[test]

      - name: Run pytest
        working-directory: api
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test
          REDIS_URL: redis://localhost:6379/0
        run: |
          pytest \
            --cov=todo_api \
            --cov-report=xml \
            --cov-report=term \
            --junitxml=junit.xml \
            -v

      - name: Publish test report
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: 'api/junit.xml'

  # ============ ビルド & push ============
  build-push:
    needs: [lint, test]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    outputs:
      tag: ${{ steps.tag.outputs.tag }}
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - id: tag
        run: |
          DATE=$(date -u +%Y%m%d)
          SHA=$(git rev-parse --short HEAD)
          echo "tag=${DATE}-${SHA}" >> $GITHUB_OUTPUT

      - uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile.api
          platforms: linux/amd64
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.tag.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
          labels: |
            org.opencontainers.image.source=${{ github.event.repository.html_url }}
            org.opencontainers.image.revision=${{ github.sha }}
            org.opencontainers.image.version=${{ steps.tag.outputs.tag }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: mode=max
          sbom: true

      - name: Trivy scan
        uses: aquasecurity/trivy-action@0.24.0
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.tag.outputs.tag }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: '1'
          ignore-unfixed: true

      - name: Upload SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-results.sarif

      - name: Install cosign
        uses: sigstore/cosign-installer@v3

      - name: Sign image
        env:
          COSIGN_EXPERIMENTAL: 1
        run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}

  # ============ manifest 更新 ============
  update-manifest:
    needs: build-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: ${{ github.repository_owner }}/todo-manifests
          token: ${{ secrets.MANIFEST_TOKEN }}

      - name: Install yq
        run: |
          sudo wget -qO /usr/local/bin/yq \
            https://github.com/mikefarah/yq/releases/download/v4.44.1/yq_linux_amd64
          sudo chmod +x /usr/local/bin/yq

      - name: Update tag
        run: |
          yq -i '.api.image.tag = "${{ needs.build-push.outputs.tag }}"' overlays/prod/values.yaml

      - name: Commit
        run: |
          git config user.name "todo-ci-bot"
          git config user.email "ci-bot@example.com"
          git add .
          if git diff --staged --quiet; then
            echo "No changes"; exit 0
          fi
          git commit -m "deploy(prod): todo-api ${{ needs.build-push.outputs.tag }}"
          git push
```

これで `git push` から本番のマニフェストリポジトリ更新までが一気通貫します。

---

## シークレット管理のベストプラクティス

### GitHub Secrets と Variables

| 種類 | 用途 | 表示 |
|------|------|------|
| Secrets | パスワード、トークン、API キー | ログでマスクされる |
| Variables | 機密でない設定 (URL、環境名) | 平文表示 |

### スコープ

```mermaid
flowchart TB
    org[Organization Secrets] --> repo
    repo[Repository Secrets] --> env
    env[Environment Secrets] --> wf[Workflow]
```

| スコープ | 使い分け |
|---------|---------|
| Organization | 複数 repo で共有するもの (Docker Hub クレデンシャル等) |
| Repository | この repo 専用 |
| Environment | dev/stg/prod ごとの値、承認ワークフローと連携可 |

### Environment Secrets と protection rules

```yaml
jobs:
  deploy-prod:
    environment:
      name: production
      url: https://todo.example.com
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying with ${{ secrets.PROD_TOKEN }}"
```

`production` environment に **required reviewers** を設定すると、誰かが承認するまでこの job は止まります。本番デプロイの承認フローに使えます。

### OIDC によるシークレットレス認証

クラウド (AWS/GCP/Azure) へのアクセスは PAT ではなく OIDC を使うのが現代の正解です。

```yaml
permissions:
  id-token: write           # OIDC token 発行に必要
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123456789:role/github-actions
      aws-region: ap-northeast-1
```

長期トークンの保管が不要になり、セキュリティが向上します。本教材では AWS を使いませんが、考え方として覚えておいてください。

---

## CI 失敗時のデバッグ

### 1. UI でログを読む

GitHub Actions の UI で:
1. 失敗した workflow を開く
2. 失敗した job をクリック
3. 失敗した step を展開
4. 赤い × 印の行から探す

### 2. ローカル再現: act

[nektos/act](https://github.com/nektos/act) で workflow をローカル実行できます。

```bash
brew install act
act -j test                  # test ジョブだけ実行
act push                     # push イベントをシミュレート
act -s GITHUB_TOKEN=ghp_...   # シークレット指定
```

### 3. debug log を有効化

workflow を再実行するときに **「Enable debug logging」** にチェックを入れると、内部の詳細ログが表示されます。

または Secrets に以下を入れる:
- `ACTIONS_RUNNER_DEBUG=true`
- `ACTIONS_STEP_DEBUG=true`

### 4. tmate で SSH 接続

GitHub Actions の runner に SSH で入って調査できます (デバッグ専用)。

```yaml
- name: SSH session
  if: failure()
  uses: mxschmitt/action-tmate@v3
  timeout-minutes: 30
```

失敗時のみ起動して、SSH URL がログに出ます。

---

## トラブル事例集

### 症状別フローチャート

```mermaid
flowchart TD
    start[CI が失敗した] --> q1{エラー種別は?}
    q1 -->|赤い × at lint| L[Lint エラー]
    q1 -->|test 失敗| T[テスト失敗]
    q1 -->|build 失敗| B[ビルド失敗]
    q1 -->|push 失敗| P[push 失敗]
    q1 -->|manifest 更新失敗| M[manifest更新失敗]

    L --> L1[ruff check のメッセージ確認<br/>ローカルで ruff check 実行]
    T --> T1{services 起動済?}
    T1 -->|no| T2[services: の health-cmd 見直し]
    T1 -->|yes| T3[ローカルで pytest 再現]
    B --> B1{Dockerfile か buildx か?}
    B1 -->|Dockerfile| B2[ローカルで docker build]
    B1 -->|cache-from| B3[GHA cache サイズ超過の可能性]
    P --> P1{401/403?}
    P1 -->|yes| P2[permissions: packages: write 確認]
    P1 -->|no| P3[ネットワーク or レジストリ障害]
    M --> M1{PAT 期限切れ?}
    M1 -->|yes| M2[Fine-grained PAT を再発行]
    M1 -->|no| M3[branch protection 確認]
```

### よくあるエラーと対処

| エラーメッセージ | 原因 | 対処 |
|----------------|------|------|
| `Error: HttpError: Resource not accessible by integration` | `GITHUB_TOKEN` の権限不足 | `permissions:` ブロックで必要な権限を明示 |
| `denied: permission_denied: write_package` | GHCR への push 権限なし | `packages: write` を `permissions` に追加 |
| `failed to solve: failed to read dockerfile` | `file:` パスが間違い | パスを `Dockerfile.api` 等に修正 |
| `Error: buildx failed with: ERROR: failed to push... 413 Request Entity Too Large` | イメージサイズ過大 | レイヤー削減、`.dockerignore` 整備 |
| `actions/checkout@v4: Error: fatal: not a git repository` | チェックアウト前に git コマンドを使った | `actions/checkout` を最初に実行 |
| `failed to fetch oauth token: unexpected status: 401 Unauthorized` | login-action のクレデンシャル誤り | `username` `password` 確認 |
| `pip install: ERROR: Could not find a version that satisfies...` | プライベートパッケージへのアクセス権なし | PAT を環境変数で渡す |
| `pytest: error: unrecognized arguments: ...` | pytest プラグイン未インストール | `pip install -e .[test]` に含める |
| `cosign: keyless signing requires --yes flag` | cosign v2 以降の挙動 | `cosign sign --yes` を使う |
| `Error: trivy: vulnerabilities found` | CRITICAL/HIGH 検出 | 依存更新、`ignore-unfixed: true`、base image 更新 |
| `Error: git push: rejected because remote contains work` | manifest repo が他から push されている | `git pull --rebase` を入れる、または retry |
| `Service container 'postgres' is not running` | services の health-cmd 失敗 | `--health-cmd` `--health-retries` 確認 |
| `The job running on runner ... has exceeded the maximum execution time of 360 minutes` | ジョブのタイムアウト | `timeout-minutes` で明示 |

---

## CI 全体のベストプラクティス

### 1. 並列化

可能な限り並列実行する:

```yaml
jobs:
  lint:
    # ...
  test:
    # ...
  # lint と test は並列
  build:
    needs: [lint, test]
    # 両方OKならビルド
```

### 2. concurrency による重複抑止

同じ branch への連続 push で古いジョブをキャンセル:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

main への push は cancel-in-progress: false (本番デプロイは中断したくない)。

### 3. 再利用可能 workflow

複数 repo で同じ workflow を使いたいとき:

```yaml
# .github/workflows/reusable-build.yaml
on:
  workflow_call:
    inputs:
      image_name:
        required: true
        type: string
    secrets:
      registry_token:
        required: true

jobs:
  build:
    # ...
```

```yaml
# 呼び出し側
jobs:
  build-api:
    uses: ./.github/workflows/reusable-build.yaml
    with:
      image_name: todo-api
    secrets:
      registry_token: ${{ secrets.GHCR_PAT }}
```

### 4. Composite Action による step まとめ

```yaml
# .github/actions/setup/action.yaml
name: Setup
description: Python + dependencies
runs:
  using: composite
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
        cache: pip
    - shell: bash
      run: pip install -e api/[test]
```

```yaml
- uses: ./.github/actions/setup
```

### 5. Branch Protection Rules

GitHub の Settings → Branches で `main` に以下を強制:

- Require status checks to pass before merging
  - `lint`, `test` をチェックに
- Require pull request reviews before merging
  - 最低 1 名のレビュー
- Dismiss stale pull request approvals when new commits are pushed
- Require signed commits (推奨)
- Include administrators (管理者にも適用)

これで「テストせずに main へ直接 push」を防げます。

---

## ローカルレジストリへの push (発展)

学習として、本教材のローカル kubeadm 環境のレジストリ (`192.168.56.10:5000`) に push したい場合の手順です。

### 方式1: Self-hosted Runner

VMware 環境内に Self-hosted Runner を立てます。

```bash
# k8s-lb 等の VM 上で
mkdir actions-runner && cd actions-runner
curl -O -L https://github.com/actions/runner/releases/download/v2.317.0/actions-runner-linux-x64-2.317.0.tar.gz
tar xzf actions-runner-linux-x64-2.317.0.tar.gz
./config.sh --url https://github.com/USER/todo-app --token <TOKEN>
./run.sh
```

```yaml
build-push:
  runs-on: self-hosted        # ubuntu-latest ではなく self-hosted
```

この Runner からは `192.168.56.10:5000` にアクセス可能です。

{: .warning }
> **Self-hosted Runner のセキュリティ**: public repo で fork 元の PR を実行可能にすると、攻撃者の任意コードがあなたの VM 上で実行されます。private repo のみで使うか、approval を必須に。

### 方式2: パブリック GHCR を経由 + ローカルで pull (推奨)

CI は GHCR に push、クラスタは GHCR から pull。これが学習用のおすすめです。

```bash
# 各ノードで GHCR の imagePullSecret を作る
kubectl create secret docker-registry ghcr \
  --docker-server=ghcr.io \
  --docker-username=<USER> \
  --docker-password=<PAT> \
  -n prod
```

`Pod.spec.imagePullSecrets:` で参照させる。

### 方式3: ngrok 等のトンネリング (デバッグ用)

`ngrok` で `192.168.56.10:5000` をトンネル公開。本番では使わない。

---

## CI の発展形: Renovate Bot による依存自動更新

CI が回ってくれると嬉しいですが、依存ライブラリの更新も自動化したい。
**Renovate Bot** (Mend) や **Dependabot** が依存更新の PR を自動生成します。

### Renovate の設定例 (`renovate.json`)

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", ":semanticCommits"],
  "schedule": ["before 6am on monday"],
  "packageRules": [
    {
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true
    },
    {
      "matchUpdateTypes": ["major"],
      "labels": ["major-update"],
      "reviewers": ["sre-team"]
    }
  ],
  "kubernetes": {
    "fileMatch": ["overlays/.*/values\\.yaml$"]
  }
}
```

minor/patch は自動マージ、major だけ人間レビュー。manifest repo の image tag も対象にできます。

---

## ハンズオン: 最初の CI を動かす

### 前提

- GitHub アカウント
- `todo-app` リポジトリを作成済み
- `todo-manifests` リポジトリを作成済み (中身は空でも可)
- ローカルに Docker

### Step 1: 最小 API を作る

`todo-app/api/pyproject.toml`:

```toml
[project]
name = "todo-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi>=0.110", "uvicorn>=0.29"]

[project.optional-dependencies]
test = ["pytest>=8", "pytest-cov>=5", "httpx>=0.27"]
```

`todo-app/api/src/todo_api/main.py`:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/todos")
def list_todos():
    return [{"id": 1, "title": "K8s 学習"}]
```

`todo-app/api/tests/test_main.py`:

```python
from fastapi.testclient import TestClient
from todo_api.main import app

client = TestClient(app)

def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

### Step 2: Dockerfile を作る

`todo-app/Dockerfile.api`:

```dockerfile
FROM python:3.12.4-slim-bookworm AS builder
WORKDIR /app
COPY api/pyproject.toml ./
RUN pip install --no-cache-dir --user --upgrade pip && \
    pip install --no-cache-dir --user fastapi uvicorn
COPY api/src ./src

FROM python:3.12.4-slim-bookworm
RUN useradd -m -u 1000 app
WORKDIR /app
COPY --from=builder /root/.local /home/app/.local
COPY --from=builder /app/src ./src
USER app
ENV PATH=/home/app/.local/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "todo_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
```

### Step 3: ローカルで動作確認

```bash
cd todo-app
docker build -f Dockerfile.api -t todo-api:dev .
docker run --rm -p 8000:8000 todo-api:dev &
curl http://localhost:8000/healthz
# {"status":"ok"}
```

**期待される出力**: HTTP 200、JSON `{"status":"ok"}`

**失敗するケース**:

| 症状 | 原因 | 対処 |
|------|------|------|
| `ModuleNotFoundError: No module named 'todo_api'` | `--app-dir src` がない | CMD を見直す |
| `ImportError: cannot import name 'app'` | パスが間違い | `src/todo_api/main.py` を確認 |
| `OSError: [Errno 98] Address already in use` | 8000 番が使用中 | `docker ps` で停止、または別ポート |

### Step 4: GitHub Actions を設置

上記の workflow YAML を `.github/workflows/ci.yaml` に置き、commit & push。

### Step 5: 動作確認

```bash
git add .
git commit -m "ci: initial workflow"
git push
```

GitHub の Actions タブを開いて緑になることを確認。
GHCR の Packages タブにイメージが現れることを確認。

### Step 6: manifest repo の Secrets 設定

1. `todo-app` リポジトリの Settings → Secrets and variables → Actions
2. New repository secret: `MANIFEST_TOKEN` に PAT を登録
3. PAT は Fine-grained で `todo-manifests` の `Contents: Read and write` のみ

### Step 7: manifest 更新を確認

main に push してから少し待つと、`todo-manifests` リポジトリの `overlays/prod/values.yaml` が更新されているはず。

```bash
# todo-manifests を clone
git clone https://github.com/USER/todo-manifests
cd todo-manifests
cat overlays/prod/values.yaml
# api:
#   image:
#     tag: 2024-01-15-a3f2c1b
```

### Step 8: CI を意図的に壊して挙動を確認

```python
# tests/test_main.py に失敗するテストを追加
def test_fail_on_purpose():
    assert 1 == 2
```

push して、Actions が赤くなることを確認。`build-push` ジョブが走らないことも確認。

これで CI の振る舞いが理解できました。

---

## CI 設計の落とし穴 (本番運用編)

### 1. CI が遅いと開発体験が壊れる

目標: PR から 10 分以内に CI 完了。それを超えると人間は別タスクに移ってしまい、レビューサイクルが伸びる。

対策:
- 並列化
- キャッシュ
- 大きなテストは別 workflow に分割 (`schedule` で nightly に)
- パス絞り込み (`paths:`) で不要なジョブをスキップ

### 2. CI が green でも本番が壊れる

CI で見ているのは「ビルドが通る、テストが通る」だけ。本番固有の問題は別。

| 本番固有 | 確認方法 |
|---------|---------|
| 通信遅延 | 結合テスト環境を本番相当の構成に |
| ストレージ性能 | 性能試験を別 workflow で nightly |
| マニフェスト整合性 | `helm template` + `kubeconform` を CI で |
| 設定ミス | Argo CD diff で commit 前確認 |

### 3. シークレットの誤コミットを検出できない時間がある

`gitleaks` を CI に入れても、 **PR より先にコミットされた時点で公開リポジトリだとアウト** です。
push の前 (pre-commit hook) でも検出する仕組みを推奨:

```bash
brew install pre-commit
echo "
repos:
- repo: https://github.com/gitleaks/gitleaks
  rev: v8.18.4
  hooks:
  - id: gitleaks
" > .pre-commit-config.yaml
pre-commit install
```

### 4. 「テスト緑なら良し」の罠

テストカバレッジが低いと、CI 緑 = 本番安全 ではない。

- カバレッジ 80% を目安に
- mutation testing で「テストが本当に検出力があるか」確認 (`mutmut`)
- E2E テストを定期実行

### 5. CI 自体がボトルネックに

monorepo で何万ファイルあると、CI が常時走り続けて Runner が枯渇。

対策:
- `paths:` でモジュール単位の起動
- monorepo 用ツール (Bazel, Nx, Turborepo) で「変更したパッケージだけビルド」

---

## CI と CD の境界線の議論

### CIとCDを分ける派と統合派

| 流派 | 主張 | 代表 |
|------|------|------|
| 分離派 | CI = GitHub Actions, CD = Argo CD (本教材) | Weaveworks, CNCF |
| 統合派 | 全部 GitHub Actions でやれば良い | スモールプロジェクト、スタートアップ |
| クラスタ内派 | CI も CD も K8s 内で動くべき | Tekton, Argo Workflows |

分離派の理由:

1. CI と CD の責務が違う (前述)
2. pull 型 GitOps の安全性が高い
3. ツールに対する習熟度を高めやすい

統合派の理由:

1. ツールが少ない方が運用負荷が低い
2. 小規模なら全部 GitHub Actions で十分
3. デバッグが1箇所で済む

本教材は分離派ですが、これは学習目的で **概念をきちんと分けて理解する** ためです。実務ではあなたのチーム規模で選んでください。

---

## 演習: 1コミットで本番反映

1. アプリの API ハンドラに `/todos` のレスポンスを変更 (`title` を追加など)
2. `git push` する
3. Actions タブで以下を確認:
   - `lint` 緑
   - `test` 緑
   - `build-push` で digest が出る
   - `update-manifest` で別 repo にコミットが入る
4. `todo-manifests` の git log で deploy コミットを確認

```bash
cd todo-manifests
git pull
git log -1
# deploy(prod): todo-api 2024-01-15-a3f2c1b
```

これで CI フェーズは完成。次節 [Argo CD]({{ '/08-cicd-gitops/argocd/' | relative_url }}) でクラスタへの反映を学びます。

---

## 発展課題

- **複数イメージのモノレポ CI**: api/frontend/worker を変更検知して必要なものだけビルド
- **Tag based release**: `git tag v1.2.3` で安定版を別タグで push する workflow を追加
- **PR preview**: PR ごとに ephemeral 環境を立てる (CD 章で扱う)
- **依存自動更新**: Renovate Bot を導入
- **コンテナイメージ署名検証**: K8s 側で Kyverno を入れて未署名イメージを拒否

---

## まとめ

```mermaid
mindmap
  root((CI Pipeline))
    歴史
      XP (1996)
      Hudson/Jenkins (2005)
      SaaS (2011-)
      GitHub Actions (2018)
    主要ステージ
      Lint
      Test
      Build (buildx)
      Scan (Trivy)
      Sign (cosign)
      Push
      Manifest更新
    安全性
      Signed commits
      Branch protection
      Sigstore
      SBOM
      SLSA Provenance
    ベストプラクティス
      latest禁止
      digest参照
      キャッシュ活用
      並列化
      concurrency制御
      Secretsスコープ
```

---

## チェックポイント

ここまでで以下を **自分の言葉で** 説明できるか確認してください。

- [ ] アプリリポジトリとマニフェストリポジトリを分ける利点を3つ以上
- [ ] CI で実装すべき品質ゲートを 5 つ挙げ、それぞれのツールを答えられる
- [ ] イメージタグに `latest` を使わない理由を3つ以上
- [ ] Docker イメージのキャッシュを効かせるための Dockerfile の書き方
- [ ] BuildKit secret と通常の `ENV`/`ARG` の違い、なぜ前者を使うか
- [ ] cosign の keyless signing の仕組み (OIDC, Fulcio, Rekor)
- [ ] GitHub Actions の `permissions:` ブロックが必要な理由
- [ ] CI が失敗したときの調査手順 (lint/test/build/push 別)
- [ ] サプライチェーン攻撃の代表例と SLSA がそれをどう緩和するか
- [ ] 自分のリポジトリで CI が緑になり、manifest repo に自動コミットが入る状態を実現できた

→ 次は [Argo CDでGitOps]({{ '/08-cicd-gitops/argocd/' | relative_url }})


