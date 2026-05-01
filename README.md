# 入門 Kubernetes

Minikube から始めて、VMware Workstation 上の kubeadm で **HA構成のクラスタを自前構築** し、
本番運用・GitOps・可観測性・SRE まで網羅する **ローカル完結型 Kubernetes 学習教材** です。

公開サイト: `https://swallowsaba.github.io/introduction-k8s/`

## このリポジトリの中身

```
introduction-k8s/
├── _config.yml                # Jekyll サイト設定 (just-the-docs テーマ)
├── Gemfile                    # ローカルプレビュー用
├── index.md                   # トップページ
├── docs/
│   ├── 01-introduction/       # 第1章 はじめに
│   ├── 02-resources/          # 第2章 リソース基礎
│   ├── 03-workloads/          # 第3章 ワークロード
│   ├── 04-networking/         # 第4章 ネットワーキング
│   ├── 05-storage/            # 第5章 ストレージ
│   ├── 06-config/             # 第6章 設定とSecret
│   ├── 07-production/         # 第7章 本番運用 (kubeadm/Probe/HPA/Helm/Kustomize)
│   ├── 08-cicd-gitops/        # 第8章 CI/CD と GitOps
│   ├── 09-observability/      # 第9章 可観測性
│   ├── 10-security/           # 第10章 セキュリティ
│   ├── 11-sre/                # 第11章 SRE運用
│   ├── 12-advanced/           # 第12章 発展トピック
│   └── 99-appendix/           # 付録 (チートシート、本番チェックリスト、参考文献)
├── sample-app/                # サンプルアプリ「ミニTODO」のソース + マニフェスト
│   ├── frontend/              # Nginx + 静的HTML
│   ├── api/                   # FastAPI
│   ├── worker/                # 通知バッチ
│   └── k8s/                   # 章ごとのKubernetesマニフェスト
│       ├── 02-basic/
│       ├── 03-stateful/
│       ├── 06-configmap-secret/
│       ├── 07-helm/todo-chart/
│       ├── 07-kustomize/{base,overlays/{dev,prod}}
│       └── 08-argocd/
├── .github/workflows/
│   └── pages.yml              # GitHub Pages 自動デプロイ
└── README.md                  # このファイル
```

## デプロイ方法 (GitHub Pages)

### 1. リポジトリをフォーク or クローン

```bash
git clone https://github.com/swallowsaba/introduction-k8s.git
cd introduction-k8s
```

### 2. プレースホルダ置換

`swallowsaba` を自分の GitHub ユーザー名で置換します。

#### Windows (PowerShell)

```powershell
$user = "your-username"
Get-ChildItem -Recurse -File `
  -Exclude *.png,*.jpg,*.gif `
  | Where-Object { $_.FullName -notmatch '\\\.git\\' } `
  | ForEach-Object {
      (Get-Content -Raw -Encoding UTF8 $_.FullName) `
        -replace 'swallowsaba', $user `
        | Set-Content -Encoding UTF8 -NoNewline $_.FullName
    }
```

#### Windows (Git Bash) / macOS / Linux

```bash
USER=your-username
grep -rl 'swallowsaba' . --exclude-dir=.git \
  | xargs sed -i.bak "s/swallowsaba/$USER/g"
find . -name "*.bak" -delete
```

#### エディタで一括置換

VS Code が手元にあれば最も簡単です:

1. リポジトリのフォルダを VS Code で開く
2. **Ctrl + Shift + H** で「フォルダー全体での置換」
3. 検索: `swallowsaba`
4. 置換: `your-username`
5. 「すべて置換」

対象ファイル例:

- `_config.yml` (`aux_links`)
- `index.md` (GitHubボタンのリンク)
- `docs/**/*.md` 内のリポジトリ参照
- `sample-app/k8s/08-argocd/*.yaml`

### 3. GitHub に push

```bash
git add -A && git commit -m "Customize for my account"
git push
```

### 4. GitHub Pages を有効化

1. GitHub のリポジトリ → **Settings** → **Pages**
2. **Source** で **GitHub Actions** を選択
3. main ブランチに push されると自動でビルド・公開されます
4. 数分後に `https://swallowsaba.github.io/introduction-k8s/` でアクセス可能

## ローカルでプレビューする(任意)

GitHub Pages にデプロイするだけなら不要ですが、編集しながら手元で確認したい場合の手順です。

### Windows

1. **RubyInstaller** で Ruby をインストール
   - <https://rubyinstaller.org/downloads/> から **Ruby+Devkit 3.2.x (x64)** をダウンロード
   - インストール最後の画面で `MSYS2 development toolchain` のインストール(`ridk install` で `3` を選択)を実行
2. PowerShell で:

   ```powershell
   cd introduction-k8s
   gem install bundler
   bundle install
   bundle exec jekyll serve
   ```

3. ブラウザで <http://localhost:4000/introduction-k8s/>

#### よくあるエラー

- `wdm` が入らない → Gemfile では Windows のみ条件で導入する書き方になっているので無視可。出ないなら問題なし
- `eventmachine` でビルドエラー → Devkit が未インストール。`ridk install` で再導入
- `--livereload` でファイル監視がうまく動かない → `--force_polling` オプションを足すと安定

### macOS / Linux

```bash
cd introduction-k8s
bundle install
bundle exec jekyll serve
```

## 学習を進める順序

1. ブラウザで公開サイトを開く(またはローカル `bundle exec jekyll serve`)
2. 第1章から順に読み進めます
3. 各章のハンズオンで `sample-app/k8s/` 配下のマニフェストを使います
4. 各章末の「チェックポイント」を **自分の言葉で** 答えられるか確認

## サンプルアプリのビルド

ローカルで Docker が動くなら:

```bash
# Frontend
cd sample-app/frontend
docker build -t 192.168.56.10:5000/todo-frontend:0.1.0 .
docker push 192.168.56.10:5000/todo-frontend:0.1.0

# API
cd ../api
docker build -t 192.168.56.10:5000/todo-api:0.1.0 .
docker push 192.168.56.10:5000/todo-api:0.1.0

# Worker (notify CronJob 用)
cd ../worker
docker build -t 192.168.56.10:5000/todo-worker:0.1.0 .
docker push 192.168.56.10:5000/todo-worker:0.1.0
```

レジストリの設定は第1章 `学習環境の準備` を参照してください。
GHCR を使う場合は `192.168.56.10:5000` を `ghcr.io/swallowsaba` に置き換えます。

## ライセンス

MIT License。教育目的・改変を歓迎します。

## フィードバック

issue / PR 歓迎です。誤字脱字、技術的誤り、より良い説明の提案など、ご自由にお寄せください。
