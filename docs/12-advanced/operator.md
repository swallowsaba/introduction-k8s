---
title: Operator
parent: 12. 発展トピック
nav_order: 1
---

# Operator
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## このページのゴール

このページを読み終えると、以下を **自分の言葉で説明できる** ようになります。

- **Operator パターン** がなぜ生まれ、何を解決しようとしているのか(歴史的経緯)
- **Custom Resource Definition (CRD)** と **Custom Controller** がどう連携して「制御ループ」を構成するか
- **Operator Capability Levels**(Level 1〜5)の意味と、Operator の成熟度をどう評価するか
- 代表的な Operator(CloudNativePG、Strimzi、prometheus-operator、cert-manager 等)で何ができるか
- 自作 Operator の選択肢(kubebuilder / Operator SDK / kopf / Metacontroller)とそれぞれの向き不向き
- サンプルアプリの PostgreSQL を **CloudNativePG(CNPG)** に置き換える実践と、これにより何が楽になるか
- Operator パターンの **限界と落とし穴**(暴走、API バージョン互換、フィナライザの罠など)

---

## 1. Operator パターンとは何か

### 1.1 ひと言で

**Operator パターン** は「Kubernetes の制御ループの仕組みを、**人間の運用知識をコード化** する形で拡張するアーキテクチャパターン」です。
具体的には次の 2 要素の組み合わせを指します。

1. **Custom Resource Definition (CRD)**: Kubernetes に「新しい種類のリソース型」を定義する機能(API 拡張)
2. **Custom Controller**: その新リソースを監視して、宣言された望ましい状態に向けて Kubernetes の他のリソースを動かすプログラム

```mermaid
flowchart LR
    user[User] -->|kubectl apply| crd[Custom Resource<br>kind: Cluster]
    crd --> ctrl[Operator Controller<br>= 専門知識をコード化]
    ctrl -->|reconcile| sts[StatefulSet]
    ctrl -->|reconcile| svc[Service]
    ctrl -->|reconcile| pvc[PVC]
    ctrl -->|reconcile| sec[Secret]
    ctrl -->|backup| s3[(S3 / MinIO)]
    ctrl -->|metrics| prom[(Prometheus)]
```

「DB の運用ノウハウを持つ DBA(データベース管理者)が、いつもクラスタの隣にいる」という状態を、ソフトウェアで実現したもの ── と捉えるのが直感的です。

### 1.2 「制御ループ」の復習

Kubernetes の中核的な動作原理は **Controller Pattern (Control Loop)** です。Operator もまったく同じ原理で動きます。

```
loop forever:
    actual = observe(world)                # 現状を観測
    desired = read_spec(resource)          # 望ましい状態を読み取り
    if actual != desired:                  # 差分があれば
        actions = compute_diff(actual, desired)
        apply(actions)                     # 修正アクションを実行
    update_status(resource, actual)        # status を更新
```

この単純なループは、Kubernetes の `kube-controller-manager` 内の各ビルトインコントローラ(Deployment Controller、ReplicaSet Controller、Job Controller、Endpoint Controller 等)も同じ構造で動いています。
**Operator は、これと同じ仕組みでアプリ固有のリソースを扱うコントローラを「外付け」する** だけのことです。

```mermaid
flowchart TB
    subgraph KCM[kube-controller-manager 内]
        dc[Deployment Controller]
        rc[ReplicaSet Controller]
        jc[Job Controller]
        ec[Endpoint Controller]
    end
    subgraph Op[Operator Pod]
        cnpg[CloudNativePG Controller]
        ks[Strimzi Controller]
        cm[cert-manager Controller]
    end
    api[(kube-apiserver)]
    etcd[(etcd)]
    api <--> etcd
    KCM <-->|watch/update| api
    Op <-->|watch/update| api
```

ビルトインも Operator も、同じ API Server 経由でリソースを監視・更新するという、**Kubernetes API を中心にしたフラットな構造** になっています。これが Operator パターンの強さです。

### 1.3 Operator パターンの正式定義

Brandon Phillips(CoreOS、後に Red Hat)が 2016 年の CoreOS ブログ記事 で次のように定義しました(意訳)。

> An Operator is **an application-specific controller** that extends the Kubernetes API to create, configure, and manage instances of complex stateful applications **on behalf of a Kubernetes user**.

ポイント:

- **アプリ固有 (application-specific)**: 汎用の Controller(Deployment Controller 等)とは違い、特定のアプリ(etcd、PostgreSQL、Kafka 等)の運用ノウハウを内包する
- **API を拡張する**: ユーザは Pod や Deployment ではなく、`kind: PostgreSQLCluster` のような「アプリのドメインに合った言葉」で宣言する
- **ステートフルアプリの管理**: 元々の動機がステートフル系(etcd、Prometheus、DB)だったため、こう書かれている。ただし現代はステートレスでも Operator はよく使われる
- **ユーザに代わって運用 (on behalf of)**: 運用作業の「代行」が本質

つまり Operator は **「アプリの DBA や SRE をソフトウェア化したもの」** という表現が、最も実態に近いです。

---

## 2. なぜ Operator が必要か ─ 歴史的経緯

### 2.1 Kubernetes の初期(2014〜2016 年)とステートフル運用の壁

Kubernetes 1.0 が公開されたのは 2015 年 7 月。当初は **ステートレスな Web アプリの運用** が主な想定で、ステートフルなアプリ(DB、メッセージブローカ等)の運用は **想定外** に近い扱いでした。

理由:

1. **Pod は使い捨て前提**: Pod は IP がランダム、再起動でホスト名も変わる
2. **永続ストレージの仕組みが未熟**: PersistentVolume はあったが、StatefulSet (当時 PetSet) は 1.5 (2016/12) まで無かった
3. **順序保証なし**: Deployment は Pod を並行起動する。DB のように「primary を先に立てて、replica が join」みたいな順序制御ができない
4. **アイデンティティ(永続的なホスト名)が無い**: pod-abc123 のようなランダム名

当時、本番で MySQL や PostgreSQL を Kubernetes に乗せるのは **「自殺行為」** とすら言われていました。Google 自身も、Borg(Kubernetes の前身)では DB は別系統で運用していました。

### 2.2 StatefulSet(PetSet)の登場 ─ 半分解決した問題

2016 年 12 月、Kubernetes 1.5 で **PetSet(後の StatefulSet)** が登場。これは「ステートフルアプリ運用への第一歩」でした。

StatefulSet が提供したもの:

- **安定した名前**: `postgres-0`、`postgres-1`、`postgres-2`(serial、変わらない)
- **安定したストレージ**: 各 Pod に個別の PVC を割り当て
- **順序保証された起動**: postgres-0 → postgres-1 → postgres-2 の順
- **順序保証された削除**: 逆順

しかし StatefulSet は **「アプリのことは何も知らない」**。例えば PostgreSQL なら:

- **レプリカ間のレプリケーション設定**: pg_hba.conf、wal_level、archive_command など、誰がやる?
- **プライマリ昇格**: 旧 primary が落ちたら、誰が「次の primary」を選ぶ?
- **アプリケーション側への接続先切り替え**: primary 変更後、クライアントの DSN はどう更新?
- **バックアップ**: pg_basebackup、WAL アーカイブ、PITR テスト
- **メジャーバージョンアップグレード**: pg_upgrade、データ互換性

これらすべてを、ユーザは **自前で Init Container や Sidecar や CronJob で組み立てる** 必要がありました。
そして、組み立てた経験を社内ドキュメントに残し、退職する時に後任に引き継ぐ ── というのを世界中の会社が個別に行っていました。

「これを **ソフトウェア化して共通化** しよう」── これが Operator パターンが生まれた最大の動機です。

### 2.3 CoreOS による Operator パターンの提唱(2016 年 11 月)

2016 年 11 月、CoreOS は **etcd Operator** と **Prometheus Operator** をオープンソースで公開し、同時に **「Operator パターン」** という概念を提唱しました。

- etcd Operator: etcd クラスタの作成・スケール・バックアップ・メンバー入れ替え・バージョンアップを自動化
- Prometheus Operator: Prometheus / Alertmanager / ServiceMonitor / PodMonitor の宣言的管理

両方とも当時の Kubernetes コミュニティに大きな衝撃を与えました。

- 「ステートフル運用が **Kubernetes 上で完結する** 道が見えた」
- 「自分たちの社内ノウハウを **OSS として公開** する流れが生まれた」

CoreOS は 2018 年に Red Hat に買収され、2019 年に **Operator SDK** と **Operator Lifecycle Manager (OLM)** を発表、Red Hat OpenShift の中核技術として位置付けました。

### 2.4 CRD の API 拡張機能の標準化

Operator パターンの土台になる **Custom Resource Definition (CRD)** は、Kubernetes 1.7(2017 年 6 月)で `apiextensions.k8s.io/v1beta1` として導入されました。
それ以前は **ThirdPartyResource (TPR)** という前身がありましたが、不安定・スケールしない・バリデーション弱いといった問題で、1.7 で TPR は非推奨、1.8 で削除されました。

CRD は次の安定化を経て、今に至ります:

- 1.7 (2017): `apiextensions.k8s.io/v1beta1` 導入
- 1.13 (2018): CRD のバリデーション(OpenAPI v3 Schema)強化
- 1.15 (2019): バージョニング、Webhook Conversion 対応
- 1.16 (2019): `apiextensions.k8s.io/v1` GA(stable)
- 1.22 (2021): v1beta1 削除

「v1 が GA する 2019 年以降」が、Operator が現代的に書ける時代の本格スタートと言えます。

### 2.5 Operator の爆発的普及(2018〜2024 年)

CRD の安定化を受けて、各 OSS / ベンダから Operator が次々登場しました。代表例だけでも:

| 年 | Operator | 提供元 |
|----|----------|--------|
| 2016 | etcd Operator | CoreOS |
| 2016 | Prometheus Operator | CoreOS |
| 2017 | Spark Operator | Google |
| 2018 | Strimzi (Kafka) | Red Hat |
| 2018 | cert-manager | Jetstack |
| 2018 | Crunchy Postgres Operator | Crunchy Data |
| 2019 | Elastic Cloud on K8s (ECK) | Elastic |
| 2019 | MongoDB Community Operator | MongoDB |
| 2020 | CloudNativePG (前身 cnp.io) | EDB / 2nd Quadrant |
| 2020 | Zalando Postgres Operator | Zalando |
| 2021 | Argo CD (Argoproj 配下、Operator パターンで実装) | Intuit / 多数 |
| 2022 | Cilium Operator | Isovalent |
| 2024 | CloudNativePG が CNCF Graduated | CNCF |

2026 年現在、**OperatorHub.io** には 400+ の Operator が掲載され、CNCF Landscape の Application Definition セクションには 80+ の Operator が登録されています。

### 2.6 まとめ ─ Operator が解決した 3 つの問題

| 問題 | 解決 |
|------|------|
| ステートフル運用は手作業が多すぎる | 運用知識をコード化して再利用 |
| 各社が同じ車輪を再発明している | OSS として公開、業界標準を形成 |
| Kubernetes はステートレスにしか向かないという誤解 | Operator で「ほぼ何でも乗る」状態に |

---

## 3. CRD ─ Operator の API 層

Operator を語る前に、その基盤になる **CRD** を理解する必要があります。CRD は Operator なしでも単体で意味があります(設定 DB として使うパターン等)。

### 3.1 CRD とは

CRD は「Kubernetes API に **自分専用のリソースタイプを追加** する仕組み」です。
標準で存在する `kind: Pod`、`kind: Deployment`、`kind: Service` などの隣に、`kind: PostgreSQLCluster`、`kind: Certificate`、`kind: Kafka` などを新設できます。

CRD を作成すると:

- `kubectl get postgresqlcluster` で一覧表示できるようになる
- `kubectl apply -f my-cluster.yaml` で作成・更新できる
- API Server が **etcd に保存** する
- バリデーションは OpenAPI v3 Schema で記述
- 標準リソースと同様に **RBAC、ラベル、アノテーション、Owner Reference、Finalizer** が使える

### 3.2 最小の CRD 例

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: webapps.example.com    # <plural>.<group> 形式が必須
spec:
  group: example.com
  scope: Namespaced            # または Cluster
  names:
    plural: webapps
    singular: webapp
    kind: WebApp
    shortNames: [wa]
  versions:
  - name: v1
    served: true
    storage: true
    schema:
      openAPIV3Schema:
        type: object
        properties:
          spec:
            type: object
            required: [image, replicas]
            properties:
              image:
                type: string
              replicas:
                type: integer
                minimum: 1
                maximum: 100
              port:
                type: integer
                default: 8080
          status:
            type: object
            properties:
              availableReplicas:
                type: integer
              conditions:
                type: array
                items:
                  type: object
    subresources:
      status: {}
      scale:
        specReplicasPath: .spec.replicas
        statusReplicasPath: .status.availableReplicas
    additionalPrinterColumns:
    - name: Image
      type: string
      jsonPath: .spec.image
    - name: Replicas
      type: integer
      jsonPath: .spec.replicas
    - name: Available
      type: integer
      jsonPath: .status.availableReplicas
    - name: Age
      type: date
      jsonPath: .metadata.creationTimestamp
```

### 3.3 主要フィールドすべての解説

#### `metadata.name`

`<plural>.<group>` 形式で、CRD 自体の名前。例: `webapps.example.com`。
これと `spec.names` を間違える人が多いので注意。

#### `spec.group`

**API グループ**。`example.com`、`postgresql.cnpg.io`、`cert-manager.io` のように **逆ドメイン形式** にするのが慣例(競合回避のため)。
実在のドメインを使う必要は無いが、**社内独自 Operator なら社内ドメイン** を使うとよい。

#### `spec.scope`

`Namespaced`(Namespace 単位、Pod や Service と同じ)または `Cluster`(クラスタワイド、Node や ClusterRole と同じ)。

| Scope | 例 | いつ使う |
|-------|----|--------|
| Namespaced | Certificate、Kafka、PostgreSQLCluster | Namespace ごとに分離したい(マルチテナント) |
| Cluster | ClusterIssuer、StorageClass の CR 拡張 | 全クラスタで共有したい設定 |

迷ったら **Namespaced を選ぶ**。あとから Cluster にするのは難しいが、逆は比較的容易。

#### `spec.names`

- `plural`: URL とコマンドで使う複数形(`webapps`)
- `singular`: 単数形(`webapp`)
- `kind`: YAML の `kind:` フィールドに書く CamelCase 名(`WebApp`)
- `shortNames`: `kubectl get wa` のような短縮名(任意)
- `categories`: `kubectl get all` で含めるグループ(`[all]` 等)

#### `spec.versions[]`

複数の API バージョンを同時提供できる。

```yaml
versions:
- name: v1alpha1
  served: false           # 提供停止(古い API を残しつつ非公開化)
  storage: false
- name: v1beta1
  served: true            # 提供中
  storage: false
- name: v1
  served: true            # 提供中
  storage: true           # etcd にこの形式で保存
```

- `served: true`: その version で API Server がリクエストを受ける
- `storage: true`: そのバージョンで etcd に保存される(**1 つだけ true**)

複数バージョンを共存させる場合、**Conversion Webhook** で相互変換するか、いずれも互換的なスキーマである必要がある。

#### `spec.versions[].schema.openAPIV3Schema`

**OpenAPI v3 Schema** で CR の構造をバリデーションする。これが弱いと、ユーザが間違った YAML を投げてもエラーにならず、Controller がパースエラーで死ぬ ── という事態になる。

主なバリデーション:

| キーワード | 意味 | 例 |
|-----------|------|----|
| `type` | string / integer / boolean / object / array | `type: integer` |
| `required` | 必須フィールド | `required: [image, replicas]` |
| `minimum`, `maximum` | 整数の範囲 | `minimum: 1, maximum: 100` |
| `pattern` | 正規表現 | `pattern: '^[a-z0-9-]+$'` |
| `enum` | 列挙 | `enum: [Always, Never, IfNotPresent]` |
| `default` | デフォルト値(v1 以降) | `default: 8080` |
| `x-kubernetes-validations` | CEL(Common Expression Language)バリデーション(1.25+) | 後述 |
| `x-kubernetes-preserve-unknown-fields` | 未知のフィールドを許容 | レガシー互換用 |

##### CEL によるバリデーション(1.25+)

OpenAPI Schema では表現できない複雑なルール(フィールド間の関係など)は **CEL** で書ける。

```yaml
schema:
  openAPIV3Schema:
    type: object
    properties:
      spec:
        type: object
        properties:
          minReplicas:
            type: integer
          maxReplicas:
            type: integer
        x-kubernetes-validations:
        - rule: "self.maxReplicas >= self.minReplicas"
          message: "maxReplicas must be >= minReplicas"
```

#### `spec.versions[].subresources`

- `status: {}`: `status` サブリソースを有効化。**Controller だけが status を更新し、ユーザが kubectl apply で書き換えない** ように分離できる(重要)
- `scale`: `kubectl scale --replicas=N` を CR に対して使えるようにする

#### `spec.versions[].additionalPrinterColumns`

`kubectl get` の出力に追加カラムを表示。

```bash
$ kubectl get webapps
NAME      IMAGE         REPLICAS   AVAILABLE   AGE
nginx     nginx:1.25    3          3           2m
```

#### `spec.preserveUnknownFields`

`false` 必須(v1 以降)。`true` は脆弱性の温床になる。

#### `spec.conversion`

Webhook ベースのバージョン間変換(Conversion Webhook)を設定する。複雑なので、可能なら同一フィールド構造で複数バージョン提供 → 不要にする戦略がよい。

### 3.4 status サブリソースの分離 ─ なぜ重要か

CRD を作るときに **必ず `subresources.status: {}` を指定** すべき理由を説明します。

`status` サブリソースを有効化すると:

1. ユーザが `kubectl apply` で YAML を再適用しても、**status フィールドは上書きされない**
2. Controller は専用の API パス `/apis/<group>/<version>/namespaces/<ns>/<plural>/<name>/status` で status を更新
3. RBAC で「**spec の更新権限**」と「**status の更新権限**」を分離できる

これを忘れると:

- ユーザが古い YAML を `apply` した瞬間に、status が古い値で上書きされる
- Controller が「動いてる」と更新した status が、次の apply で「動いてない」に戻る
- 監視アラートが誤発火

実装ミスでよく見るので、CRD を書くときは **指差し確認** してください。

---

## 4. Controller ─ Operator の心臓

CRD が「API 層」なら、Controller は「**ロジック層**」です。

### 4.1 Reconcile ループの実装パターン

Operator の Controller は、典型的に次のようなループを回します。

```go
// Go の擬似コード(controller-runtime ベース)
func (r *MyReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    // 1. 対象の CR を取得
    var cr MyCustomResource
    if err := r.Get(ctx, req.NamespacedName, &cr); err != nil {
        if errors.IsNotFound(err) {
            // 削除済み(子リソースは Owner Reference で連鎖削除される)
            return ctrl.Result{}, nil
        }
        return ctrl.Result{}, err
    }

    // 2. 削除中なら Finalizer で後始末
    if !cr.DeletionTimestamp.IsZero() {
        return r.handleDeletion(ctx, &cr)
    }
    if !containsString(cr.Finalizers, myFinalizer) {
        cr.Finalizers = append(cr.Finalizers, myFinalizer)
        if err := r.Update(ctx, &cr); err != nil { return ctrl.Result{}, err }
    }

    // 3. desired state(YAML)から子リソースの仕様を計算
    desired := r.buildDesiredStatefulSet(&cr)

    // 4. 既存の子リソースを取得して比較・適用
    var existing appsv1.StatefulSet
    err := r.Get(ctx, client.ObjectKey{Namespace: cr.Namespace, Name: cr.Name}, &existing)
    switch {
    case errors.IsNotFound(err):
        // 無ければ作成(Owner Reference 設定)
        ctrl.SetControllerReference(&cr, desired, r.Scheme)
        if err := r.Create(ctx, desired); err != nil { return ctrl.Result{}, err }
    case err != nil:
        return ctrl.Result{}, err
    default:
        // あれば update(Server-Side Apply 推奨)
        if !equal(desired.Spec, existing.Spec) {
            existing.Spec = desired.Spec
            if err := r.Update(ctx, &existing); err != nil { return ctrl.Result{}, err }
        }
    }

    // 5. status を更新(別 subresource API)
    cr.Status.Phase = "Running"
    cr.Status.Replicas = existing.Status.Replicas
    if err := r.Status().Update(ctx, &cr); err != nil { return ctrl.Result{}, err }

    // 6. 一定時間後に再実行(無くてもイベントベースで動く)
    return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}
```

このループの **6 ステップが Operator の本質** です。どんなフレームワークを使っても、骨組みは同じになります。

### 4.2 イベント駆動と watch

Controller は **「タイマーで定期的にループ」する** のではなく、Kubernetes API Server からの **Watch** で「リソースが変わった」イベントを受け取り、関連する CR の Reconcile を呼びます。

```mermaid
sequenceDiagram
    participant User
    participant API as kube-apiserver
    participant Op as Operator Controller
    participant Etcd as etcd
    User->>API: kubectl apply (kind: WebApp)
    API->>Etcd: 保存
    API-->>Op: Watch 通知(WebApp 追加)
    Op->>API: Reconcile: StatefulSet を作成
    API->>Etcd: 保存
    API-->>Op: Watch 通知(StatefulSet 追加 - 自分が作ったもの)
    Note over Op: 子リソースの変化も自分宛に通知される
    API-->>Op: Watch 通知(Pod Ready)
    Op->>API: Reconcile: status を更新
```

この **Watch ベース + Reconcile 駆動** が、Kubernetes の宣言的 API の全動作の根幹です。Operator もここに乗っかっています。

### 4.3 冪等性 ─ Reconcile を何回呼んでも同じ結果に

Reconcile 関数は **何回呼ばれても、同じ望ましい状態に収束する** ように書きます(冪等性)。理由:

- Watch 通知は **重複することがある**(API Server 再起動時、リーダー切り替え時など)
- 失敗してリトライされる(`return ctrl.Result{}, err` で `err != nil` なら自動リトライ)
- 関連リソースの変化で Reconcile が連鎖的に呼ばれる

そのため、Reconcile 関数は:

- 「create → exists エラーなら無視」ではなく **「desired vs actual を比較して必要なら update」**
- 状態を **CR の status か外部システムに保存**(変数で覚えない)
- ランダム性を避ける(同じ入力で同じ出力)

### 4.4 Owner Reference と Garbage Collection

CR が削除されたら、それが作った子リソース(StatefulSet、Service、PVC 等)も連鎖削除されてほしいですよね。これを実現するのが **Owner Reference** です。

子リソースの `metadata.ownerReferences` に親 CR を記録すると、Kubernetes の **Garbage Collector** が:

- 親が消えたら子も消す(`Foreground` または `Background` propagation)

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-postgres
  ownerReferences:
  - apiVersion: postgresql.cnpg.io/v1
    kind: Cluster
    name: postgres
    uid: 12345-abcde
    controller: true             # この CR が管理者
    blockOwnerDeletion: true     # 親削除を子の削除が完了するまでブロック
```

Controller では `ctrl.SetControllerReference(parent, child, scheme)` 1 行で設定できます。

### 4.5 Finalizer ─ 削除時の後始末

CR が削除される時、**子リソースじゃない外部リソース**(クラウドリソース、外部 DB、バックアップなど)を後始末したい場合があります。これを担うのが **Finalizer** です。

仕組み:

1. CR の `metadata.finalizers` に文字列(例: `cnpg.io/cleanup`)が **1 つでもあると**、削除リクエストは **「論理削除」**(`metadata.deletionTimestamp` がセットされるだけで etcd からは消えない)
2. Controller は Reconcile 時に `deletionTimestamp` を見て後始末処理を実行
3. 終わったら Controller が `finalizers` から自分の文字列を **削除**
4. すべての finalizer が消えると、Kubernetes が etcd から物理削除

これを忘れると **「永遠に Terminating のまま消えない CR」** が発生します。トラブルシューティングの章で扱う「stuck terminating」現象の原因です。

```yaml
metadata:
  name: my-postgres
  finalizers:
  - cnpg.io/cleanup
  deletionTimestamp: "2026-05-15T10:00:00Z"   # これがあると論理削除中
```

緊急時のリセット方法(注意: 後始末されない):

```bash
kubectl patch cluster postgres -p '{"metadata":{"finalizers":[]}}' --type=merge
```

### 4.6 並列性とリーダー選出

複数の Operator Pod が同時に動くと、Reconcile が並行実行されてリソース更新が衝突します。回避方法は 2 つ。

1. **Operator を 1 Pod だけ動かす**(Deployment replicas: 1)── 単純だが SPOF
2. **リーダー選出 (Leader Election)** を使う ── 複数 Pod 立てて 1 つだけがアクティブ

controller-runtime の場合は `Options.LeaderElection: true` で簡単に有効化。内部的には Lease リソースを使った仕組みです。

```yaml
# CNPG の Lease
apiVersion: coordination.k8s.io/v1
kind: Lease
metadata:
  name: cnpg-operator-lease
  namespace: cnpg-system
spec:
  holderIdentity: cnpg-controller-manager-abc123_xxx
  leaseDurationSeconds: 15
  renewTime: "2026-05-15T10:00:00Z"
```

15 秒間 renew できなかったら他の Pod がリーダーになる、というシンプルな仕組み。

---

## 5. Operator の成熟度モデル ─ Capability Levels

Operator は単に「動く」だけでなく、**運用上どれだけ高度なことを自動化できるか** に大きな差があります。
Red Hat が提唱した **Operator Capability Levels** が業界標準です。

### Level 1: Basic Install

- CR を作ると Pod が立ち上がる(基本的な起動)
- 例: ただの Deployment ラッパー

### Level 2: Seamless Upgrades

- アプリのバージョンアップを Operator が安全に実施
- 例: マイナーバージョン上げを自動 rollout

### Level 3: Full Lifecycle

- バックアップ・リストア・スケール・障害復旧
- 例: 「3 レプリカに増やす」と書くと、データを保ったまま増える

### Level 4: Deep Insights

- メトリクス・アラート・ログ統合(Prometheus と自動連携)
- 例: ServiceMonitor を自動生成、独自メトリクスを export

### Level 5: Auto Pilot

- 異常検知 → 自己修復、パフォーマンス最適化、自動チューニング
- 例: クエリ実行計画を見て統計情報を再収集、autovacuum 調整

```mermaid
flowchart TB
    L1[Level 1: Basic Install<br>CRから起動できる]
    L2[Level 2: Seamless Upgrades<br>バージョンアップ自動化]
    L3[Level 3: Full Lifecycle<br>バックアップ・リストア]
    L4[Level 4: Deep Insights<br>監視メトリクス統合]
    L5[Level 5: Auto Pilot<br>自己修復・自動最適化]
    L1 --> L2 --> L3 --> L4 --> L5
```

| Operator | Level |
|----------|-------|
| CloudNativePG | 5 |
| Strimzi | 5 |
| prometheus-operator | 4 |
| cert-manager | 4 |
| Crunchy Postgres | 5 |
| OperatorHub の Sandbox 系 | 1〜2 が多い |

### 自社で Operator を作るときの目安

- まず **Level 1** で社内に届ける(1 ヶ月)
- 半年で **Level 3** までいけば実用ライン
- **Level 4** 以降は、専任チーム継続必要

「自社特有のアプリ運用ノウハウを Operator 化するか?」の判断軸は:

- **アプリの台数**: 1 個しかないなら手作業でいい。10 個以上の似たアプリがあるなら効果大
- **運用作業の頻度**: 月 1 回手順書を見るレベルなら不要。週次・日次の作業があるなら自動化価値高
- **誤操作リスク**: 手順を間違えると本番障害になる作業は Operator 化価値が極めて高い

---

## 6. CloudNativePG (CNPG) ─ ハンズオン

ここからはハンズオン。サンプルアプリの PostgreSQL を **CloudNativePG (CNPG)** に置き換えます。
CNPG は 2024 年に CNCF Graduated になった、現代の PostgreSQL Operator の決定版です。

### 6.1 CNPG の特徴

- **In-tree replication**: PostgreSQL の物理ストリーミングレプリケーションを直接利用(Patroni のような外部ツール不使用)
- **3-node HA**: プライマリ 1 + リードレプリカ 2 が最小推奨構成
- **自動フェイルオーバー**: プライマリ Pod 障害時、最も lag の少ないリードレプリカを昇格(通常 6〜10 秒)
- **Continuous Backup**: WAL アーカイブを S3 互換ストレージへ常時送信
- **PITR (Point In Time Recovery)**: 任意時点へのリストア
- **Major Upgrade**: pg_upgrade ベース、in-place
- **Pooler**: PgBouncer 統合
- **Monitoring**: Prometheus メトリクスを自動 export

### 6.2 アーキテクチャ

```mermaid
flowchart TB
    subgraph CR[Cluster CR: kind: Cluster]
        spec[spec.instances: 3<br>storage 5Gi<br>backup: minio<br>...]
    end
    op[CNPG Operator<br>Deployment in cnpg-system]
    CR -.watch.-> op
    op -->|create| sts[StatefulSet]
    op -->|create| svc_rw[Service: postgres-rw<br>Primary 宛]
    op -->|create| svc_ro[Service: postgres-ro<br>Replica 宛]
    op -->|create| svc_r[Service: postgres-r<br>全Pod宛]
    op -->|create| sec[Secret: 認証情報]
    sts --> p1[Pod postgres-1<br>Primary]
    sts --> p2[Pod postgres-2<br>Replica]
    sts --> p3[Pod postgres-3<br>Replica]
    p1 -- streaming --> p2
    p1 -- streaming --> p3
    p1 -- WAL --> minio[(MinIO/S3)]
    op -- backup CronJob --> p1
```

### 6.3 インストール

```bash
# クラスタワイドにインストール(cnpg-system Namespace を作って Operator を入れる)
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.23/releases/cnpg-1.23.1.yaml

# 確認
kubectl get pod -n cnpg-system
# 期待出力:
# NAME                                          READY   STATUS    RESTARTS   AGE
# cnpg-controller-manager-6c8f6d4f7c-abcde      1/1     Running   0          1m
```

**何が起きるか**:

- `cnpg-system` Namespace が作成される
- Operator の Deployment (`cnpg-controller-manager`) が立ち上がる
- CRD が登録される: `clusters.postgresql.cnpg.io`、`backups.postgresql.cnpg.io`、`scheduledbackups.postgresql.cnpg.io`、`poolers.postgresql.cnpg.io` 等
- 必要な RBAC(ClusterRole / ClusterRoleBinding)が設定される

**期待される出力**:

```bash
$ kubectl get crd | grep cnpg
backups.postgresql.cnpg.io                  2026-05-15T10:00:00Z
clusters.postgresql.cnpg.io                 2026-05-15T10:00:00Z
imagecatalogs.postgresql.cnpg.io            2026-05-15T10:00:00Z
poolers.postgresql.cnpg.io                  2026-05-15T10:00:00Z
scheduledbackups.postgresql.cnpg.io         2026-05-15T10:00:00Z
```

**失敗するケース**:

| 症状 | 原因 | 対処 |
|------|------|------|
| `--server-side` を付け忘れて apply 失敗 | CRD が大きすぎて annotation 制限超過 | 必ず `--server-side` を付ける |
| `cnpg-controller-manager` が ImagePullBackOff | クラスタからインターネット出られない | local registry に mirror して image: を書き換え |
| `cnpg-controller-manager` が CrashLoopBackOff、ログに `failed to elect leader` | Leader Election に必要な権限不足 | manifest の RBAC が正しく当たっているか確認 |

### 6.4 Cluster リソースを作って Postgres を立ち上げる

サンプルアプリ用の Postgres クラスタを定義します。

```yaml
# prod namespace を作成
apiVersion: v1
kind: Namespace
metadata:
  name: prod
---
# DB 認証情報の Secret(初回のみ)
apiVersion: v1
kind: Secret
metadata:
  name: postgres-credentials
  namespace: prod
type: kubernetes.io/basic-auth
stringData:
  username: todo
  password: 'change-me-in-real-life-please'
---
# MinIO 認証情報(バックアップ送信先)
apiVersion: v1
kind: Secret
metadata:
  name: minio-creds
  namespace: prod
type: Opaque
stringData:
  ACCESS_KEY_ID: minioadmin
  SECRET_ACCESS_KEY: minioadmin
---
# Cluster CR(これが CNPG の主役)
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: postgres
  namespace: prod
spec:
  description: "TODO App PostgreSQL Cluster"
  imageName: ghcr.io/cloudnative-pg/postgresql:16.2
  instances: 3                                  # 3 ノード HA
  primaryUpdateStrategy: unsupervised           # 自動 minor update
  storage:
    size: 5Gi
    storageClass: nfs
  bootstrap:
    initdb:
      database: todo
      owner: todo
      secret:
        name: postgres-credentials
      postInitSQL:
        - CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
        - CREATE SCHEMA IF NOT EXISTS app;
  postgresql:
    parameters:
      max_connections: "200"
      shared_buffers: "256MB"
      effective_cache_size: "768MB"
      work_mem: "8MB"
      maintenance_work_mem: "64MB"
      wal_buffers: "16MB"
      checkpoint_completion_target: "0.9"
      random_page_cost: "1.1"        # SSD/NFS 想定
    pg_hba:
      - host all all all md5
  resources:
    requests:
      cpu: "200m"
      memory: "512Mi"
    limits:
      cpu: "2"
      memory: "2Gi"
  monitoring:
    enablePodMonitor: true            # prometheus-operator と連携
  backup:
    barmanObjectStore:
      destinationPath: s3://backups/postgres
      endpointURL: http://minio.minio.svc:9000
      s3Credentials:
        accessKeyId: {name: minio-creds, key: ACCESS_KEY_ID}
        secretAccessKey: {name: minio-creds, key: SECRET_ACCESS_KEY}
      wal:
        compression: gzip
      data:
        compression: gzip
        immediateCheckpoint: false
        jobs: 2
    retentionPolicy: "30d"
---
# 毎日 02:00 に物理バックアップ
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata:
  name: postgres-daily
  namespace: prod
spec:
  cluster: {name: postgres}
  schedule: "0 0 2 * * *"          # 秒含む 6 フィールドの cron 表記
  backupOwnerReference: self
```

```bash
kubectl apply -f postgres-cluster.yaml
```

**何が起きるか**:

1. Operator が CR を検出 → 順次 Pod を起動
2. `postgres-1` が **bootstrap** (initdb) で初期化、データベース・ユーザ作成
3. `postgres-2`、`postgres-3` が `postgres-1` から **pg_basebackup** でクローン後、ストリーミングレプリケーション開始
4. Service が 3 種類自動生成: `postgres-rw`(プライマリ)、`postgres-ro`(レプリカのみ)、`postgres-r`(全 Pod)

**期待される出力**:

```bash
$ kubectl get cluster -n prod
NAME       AGE   INSTANCES   READY   STATUS                     PRIMARY
postgres   2m    3           3       Cluster in healthy state   postgres-1

$ kubectl get pod -n prod -l cnpg.io/cluster=postgres
NAME         READY   STATUS    RESTARTS   AGE
postgres-1   1/1     Running   0          2m
postgres-2   1/1     Running   0          1m30s
postgres-3   1/1     Running   0          1m

$ kubectl get svc -n prod | grep postgres
postgres-r     ClusterIP   10.96.45.10   <none>   5432/TCP   2m
postgres-ro    ClusterIP   10.96.45.20   <none>   5432/TCP   2m
postgres-rw    ClusterIP   10.96.45.30   <none>   5432/TCP   2m
```

### 6.5 主要フィールド詳細

CNPG の `Cluster` CR は非常に多機能で、フィールドが大量にあります。実運用で頻出する **約 40 個** を解説します。

#### 6.5.1 基本

| フィールド | 意味 | デフォルト |
|-----------|------|-----------|
| `spec.description` | 説明文字列(運用備考) | なし |
| `spec.imageName` | PostgreSQL のイメージ | ghcr.io/cloudnative-pg/postgresql:<latest> |
| `spec.imagePullPolicy` | IfNotPresent / Always / Never | IfNotPresent |
| `spec.instances` | レプリカ数(1〜) | 必須 |
| `spec.minSyncReplicas` | 同期レプリカ最小数 | 0 |
| `spec.maxSyncReplicas` | 同期レプリカ最大数 | 0(=非同期) |
| `spec.primaryUpdateStrategy` | unsupervised(自動) / supervised(手動) | unsupervised |
| `spec.primaryUpdateMethod` | restart / switchover | restart |
| `spec.startDelay` | Pod 起動後の確認待ち秒 | 30 |
| `spec.stopDelay` | Pod 停止前の grace 秒 | 1800 |

#### 6.5.2 ストレージ

| フィールド | 意味 |
|-----------|------|
| `spec.storage.size` | 各レプリカの PVC サイズ |
| `spec.storage.storageClass` | StorageClass(本書では nfs) |
| `spec.storage.pvcTemplate` | 詳細な PVC テンプレート |
| `spec.walStorage.size` | WAL 専用ストレージ(IOPS 分離) |
| `spec.walStorage.storageClass` | WAL 用 StorageClass(SSD 推奨) |

WAL を別ボリュームにすることでパフォーマンスが大きく改善します。本番では分けるのが定石。

#### 6.5.3 PostgreSQL パラメータ

`spec.postgresql.parameters` で `postgresql.conf` のキーを直接指定できます。CNPG は **不正値だと CR が ErrorClusterStatus になる** ので、安全。

最重要パラメータ:

| パラメータ | 推奨値の目安 | 説明 |
|----------|-------------|------|
| `max_connections` | 100〜500 | アプリの接続上限 + 余裕 |
| `shared_buffers` | RAM の 25% | DB ページキャッシュ |
| `effective_cache_size` | RAM の 50〜75% | プランナのヒント |
| `work_mem` | 4〜16MB | ソート・ハッシュ用 |
| `maintenance_work_mem` | 64〜256MB | VACUUM、CREATE INDEX 用 |
| `wal_buffers` | 16MB | WAL バッファ |
| `random_page_cost` | 1.1〜1.5(SSD) | SSD なら下げる |
| `checkpoint_timeout` | 15min | チェックポイント間隔 |
| `max_wal_size` | 4GB | チェックポイントトリガ |

#### 6.5.4 認証

```yaml
spec:
  postgresql:
    pg_hba:
      - host all all 10.244.0.0/16 md5     # Pod CIDR からの接続を md5 で
      - hostssl all all 0.0.0.0/0 cert     # 外部は証明書認証
```

#### 6.5.5 バックアップ

`spec.backup.barmanObjectStore` で WAL アーカイブ + 物理バックアップを S3 互換ストレージに送ります。

| フィールド | 意味 |
|-----------|------|
| `destinationPath` | `s3://bucket/path` |
| `endpointURL` | S3 エンドポイント(MinIO 等) |
| `s3Credentials.accessKeyId.name/key` | Secret 参照 |
| `wal.compression` | gzip / lz4 / xz |
| `data.compression` | 同上 |
| `data.encryption` | サーバサイド暗号化 |
| `retentionPolicy` | "30d"(30 日)等 |

#### 6.5.6 リソース・スケジューリング

```yaml
spec:
  resources:
    requests: {cpu: 200m, memory: 512Mi}
    limits: {cpu: 2, memory: 2Gi}
  affinity:
    enablePodAntiAffinity: true            # 同 Node 重複を避ける
    topologyKey: kubernetes.io/hostname    # ノード分散
    podAntiAffinityType: required          # required または preferred
  nodeSelector:
    workload: database
  tolerations:
  - key: dedicated
    value: database
    operator: Equal
    effect: NoSchedule
```

PodAntiAffinity が **デフォルトで required** なので、ノード数が `spec.instances` を下回ると **永遠に Pending** になる罠があります。

#### 6.5.7 接続 ─ 自動生成される Service

CNPG は 3 つの Service を自動で作ります。

| Service | 用途 | セレクタ |
|---------|------|---------|
| `<name>-rw` | 書き込み接続 (Primary) | 現在のプライマリ Pod のみ |
| `<name>-ro` | 読み込み専用 (Replicas) | リードレプリカのみ |
| `<name>-r` | 任意の Pod (どこでも OK) | 全 Pod |

アプリ側の DSN は:

- 書き込み: `postgresql://todo:password@postgres-rw:5432/todo`
- 読み込み: `postgresql://todo:password@postgres-ro:5432/todo`

todo-api(FastAPI)で SQLAlchemy 使用例:

```python
# 書き込み用
engine_rw = create_engine("postgresql://todo:pwd@postgres-rw.prod.svc:5432/todo")
# 読み込み用(検索クエリ等)
engine_ro = create_engine("postgresql://todo:pwd@postgres-ro.prod.svc:5432/todo")
```

### 6.6 フェイルオーバーの観察

実際にプライマリを落として、自動復旧を観察します。

```bash
# 現プライマリ確認
$ kubectl get cluster -n prod postgres -o jsonpath='{.status.currentPrimary}'
postgres-1

# プライマリ Pod を強制削除
$ kubectl delete pod -n prod postgres-1

# 別ウィンドウで watch
$ kubectl get cluster -n prod postgres -w
NAME       AGE   INSTANCES   READY   STATUS                     PRIMARY
postgres   30m   3           3       Cluster in healthy state   postgres-1
postgres   30m   3           2       Failing over to postgres-2 postgres-1
postgres   30m   3           2       Failing over to postgres-2 postgres-2
postgres   30m   3           2       Promoting postgres-2       postgres-2
postgres   30m   3           2       Cluster in healthy state   postgres-2
postgres   31m   3           3       Cluster in healthy state   postgres-2
```

通常 **6〜10 秒** で新プライマリ稼働。`postgres-rw` Service の endpoint も自動で `postgres-2` を指すように更新されます。

アプリ側のコネクションプール(SQLAlchemy など)は接続が切れて再接続を試みるので、適切なリトライ実装があればユーザには **ほぼ意識されないレベル** で復旧します。

### 6.7 バックアップとリストア

#### バックアップ作成

```bash
# 手動バックアップ
$ kubectl cnpg backup postgres -n prod --backup-name=manual-2026-05-15
backup/manual-2026-05-15 created

# 確認
$ kubectl get backup -n prod
NAME                  AGE   CLUSTER    METHOD                PHASE       ERROR
manual-2026-05-15     1m    postgres   barmanObjectStore     completed
```

#### PITR(Point In Time Recovery)

新しい Cluster を、過去のある時刻の状態として復元できます。

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: postgres-restored
  namespace: prod
spec:
  instances: 1
  storage: {size: 5Gi, storageClass: nfs}
  bootstrap:
    recovery:
      source: postgres            # 既存 Cluster の名前
      recoveryTarget:
        targetTime: "2026-05-15 14:30:00+09:00"
  externalClusters:
  - name: postgres
    barmanObjectStore:
      destinationPath: s3://backups/postgres
      endpointURL: http://minio.minio.svc:9000
      s3Credentials:
        accessKeyId: {name: minio-creds, key: ACCESS_KEY_ID}
        secretAccessKey: {name: minio-creds, key: SECRET_ACCESS_KEY}
```

これにより `postgres-restored` Cluster が立ち上がり、データは **2026-05-15 14:30 JST の状態** になります。これが PITR の威力。

### 6.8 メジャーバージョンアップグレード

`spec.imageName` を変えるだけで minor バージョンアップは自動。
major バージョン(例: 15 → 16)は `kubectl cnpg pgupgrade` コマンドでオンライン or オフラインで実施できます。

```bash
kubectl cnpg pgupgrade postgres -n prod --new-image=ghcr.io/cloudnative-pg/postgresql:16.2
```

内部で `pg_upgrade --link` を実行し、データを物理的にコピーせず inode リンクで切り替えるので高速。

---

## 7. アプリケーション側の対応 ─ サンプルアプリの DB 切り替え

サンプルアプリ todo-api(FastAPI)が今までは自前 Postgres を見ていた DSN を、CNPG が提供する Service に切り替えます。

### 7.1 DSN の更新

ConfigMap で管理していた DSN を更新します。

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: todo-api-config
  namespace: prod
data:
  DATABASE_URL_RW: "postgresql://todo:$(POSTGRES_PASSWORD)@postgres-rw.prod.svc:5432/todo"
  DATABASE_URL_RO: "postgresql://todo:$(POSTGRES_PASSWORD)@postgres-ro.prod.svc:5432/todo"
  POOL_SIZE: "10"
  MAX_OVERFLOW: "5"
```

```yaml
# todo-api Deployment の env(抜粋)
env:
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: postgres-credentials
      key: password
- name: DATABASE_URL_RW
  valueFrom:
    configMapKeyRef:
      name: todo-api-config
      key: DATABASE_URL_RW
```

### 7.2 接続実装(SQLAlchemy)

```python
# todo_api/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL_RW = os.environ["DATABASE_URL_RW"]
DATABASE_URL_RO = os.environ["DATABASE_URL_RO"]

engine_rw = create_engine(
    DATABASE_URL_RW,
    pool_size=int(os.getenv("POOL_SIZE", 10)),
    max_overflow=int(os.getenv("MAX_OVERFLOW", 5)),
    pool_pre_ping=True,                 # 接続切れたら再接続
    pool_recycle=300,                   # 5分で強制再接続
)
engine_ro = create_engine(DATABASE_URL_RO, pool_size=10, pool_pre_ping=True)

SessionRW = sessionmaker(bind=engine_rw)
SessionRO = sessionmaker(bind=engine_ro)
```

`pool_pre_ping=True` が重要。フェイルオーバー直後の死んだ接続を弾いて再接続できます。

---

## 8. その他の主要 Operator(CNCF Landscape より)

| 用途 | Operator | Stars | 特徴 |
|------|----------|------|------|
| PostgreSQL | **CloudNativePG** (CNCF Graduated) | 5K+ | 本書採用、機能フル |
| PostgreSQL | Crunchy Postgres | 4K+ | 商用品質、有償サポート |
| PostgreSQL | Zalando Postgres | 4K+ | Zalando 社実運用、Patroni ベース |
| MySQL | Percona Operator for MySQL | 1K+ | バックアップ・PITR 強い |
| MySQL | Oracle MySQL Operator | 1K+ | 公式 |
| Redis | OT-Container-Kit Redis Operator | 1K+ | レプリカ・Sentinel |
| Redis | Spotahome Redis Operator | 1.6K+ | 安定 |
| Kafka | **Strimzi** | 5K+ | Kafka の事実上標準 |
| Elasticsearch | **ECK** | 2.5K+ | Elastic 公式 |
| MongoDB | MongoDB Community Operator | 1.3K+ | 公式 |
| Cassandra | K8ssandra | 1K+ | DataStax |
| 監視 | **prometheus-operator** | 9K+ | デファクト |
| 監視 | Grafana Operator | 1K+ | Grafana の宣言的管理 |
| 証明書 | **cert-manager** | 13K+ | Let's Encrypt 自動化 |
| Ingress | NGINX Operator | 1K+ | NGINX Ingress を CR で |
| GitOps | Argo CD | 19K+ | 本書 11 章で使用 |
| ML | Kubeflow | 14K+ | ML パイプライン |
| サーバレス | Knative Operator | 1.5K+ | Knative インストール管理 |

### 探し方

- <https://operatorhub.io/> ─ 公式カタログ
- <https://artifacthub.io/> ─ Helm Chart も含めた汎用カタログ
- CNCF Landscape の Application Definition セクション

### 選定基準

- **CNCF Graduated / Incubating か?**
- **GitHub Stars と Commit 頻度**(Sandbox 級だと枯れてないことがある)
- **Capability Level**(Level 3 以上が実用ライン)
- **メーカー / コミュニティの活発さ**
- **本番採用事例**

---

## 9. 自作 Operator ─ 選択肢

自作する道具は大きく分けて 4 系統あります。

### 9.1 kubebuilder + controller-runtime(Go、最も標準)

Kubernetes コミュニティ公式。Go で書く。

```bash
go install sigs.k8s.io/kubebuilder/v3/cmd/kubebuilder@latest
kubebuilder init --domain example.com --repo example.com/myop
kubebuilder create api --group webapp --version v1 --kind WebApp
make manifests
make run
```

長所:

- Kubernetes コミュニティのスタンダード
- パフォーマンスが高い
- 上級者向けの自由度

短所:

- Go の学習が必要
- ボイラープレートが多い

### 9.2 Operator SDK(Red Hat 系統、Go / Helm / Ansible)

kubebuilder の上に Helm Chart や Ansible Playbook を Operator 化する機能を載せたもの。

```bash
operator-sdk init --plugins=helm --domain example.com --group webapp --version v1 --kind WebApp
operator-sdk init --plugins=ansible --domain example.com
```

長所:

- **既存の Helm Chart をそのまま Operator 化できる**(コーディング不要)
- Red Hat OpenShift と統合

短所:

- 高機能化が難しい(Helm の制約に縛られる)

### 9.3 kopf(Python)

Python で Operator を書ける。学習コストが低い。

```python
import kopf
import kubernetes.client as k

@kopf.on.create('myapp.example.com', 'v1', 'webapps')
def create_fn(spec, name, namespace, **_):
    appsV1 = k.AppsV1Api()
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "replicas": spec.get('replicas', 1),
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": [{"name": "app", "image": spec['image']}]}
            }
        }
    }
    kopf.adopt(deployment)             # Owner Reference 自動設定
    appsV1.create_namespaced_deployment(namespace=namespace, body=deployment)

@kopf.on.update('myapp.example.com', 'v1', 'webapps')
def update_fn(spec, name, namespace, old, new, **_):
    # 更新時の処理
    ...

@kopf.on.delete('myapp.example.com', 'v1', 'webapps')
def delete_fn(name, namespace, **_):
    # 削除時の後始末(Finalizer 動作)
    ...

@kopf.timer('myapp.example.com', 'v1', 'webapps', interval=60)
def health_check(spec, status, **_):
    # 60 秒ごとに実行
    ...
```

長所:

- **Python なので習得が速い**
- プロトタイピング向け
- 試験運用 / 小規模で使いやすい

短所:

- Go ほどパフォーマンスが出ない
- 大規模(数百 CR)で動かす場合はリソース消費注意

### 9.4 Metacontroller(YAML + 任意言語の Webhook)

シンプルさを極めた選択肢。Controller のロジックを **HTTP Webhook(任意言語)** で書く。

```yaml
apiVersion: metacontroller.k8s.io/v1alpha1
kind: CompositeController
metadata:
  name: webapp-controller
spec:
  parentResource:
    apiVersion: example.com/v1
    resource: webapps
  childResources:
  - apiVersion: apps/v1
    resource: deployments
  - apiVersion: v1
    resource: services
  hooks:
    sync:
      webhook:
        url: http://webapp-controller.metacontroller/sync
```

Webhook は「親リソースの spec と現在の子リソース」を受け取り、「望ましい子リソース」を返すだけの **ステートレス関数** にできる。シンプル極まる。

### 9.5 選び方の指針

```mermaid
flowchart TB
    start[Operator自作したい] --> q1{Go書ける?}
    q1 -->|Yes| q2{機能複雑?}
    q1 -->|No| q3{Helm Chart既存?}
    q2 -->|Yes| kb[kubebuilder]
    q2 -->|No| sdk[Operator SDK Go]
    q3 -->|Yes| sdkh[Operator SDK Helm]
    q3 -->|No| q4{Python好き?}
    q4 -->|Yes| kopf[kopf]
    q4 -->|No| meta[Metacontroller]
```

---

## 10. Operator のテスト

Operator は **多くのリソースを操作する** ため、バグの影響範囲が大きい。テストが重要です。

### 10.1 単体テスト

Reconcile 関数の単体テスト。`controller-runtime` の `envtest` で偽の API Server を起動。

```go
func TestReconcile(t *testing.T) {
    cr := &myv1.WebApp{...}
    fakeClient := fake.NewClientBuilder().WithObjects(cr).Build()
    r := &MyReconciler{Client: fakeClient, Scheme: scheme}
    result, err := r.Reconcile(ctx, reconcile.Request{...})
    assert.NoError(t, err)
    assert.Equal(t, reconcile.Result{}, result)
    // StatefulSet が作られたか確認
    sts := &appsv1.StatefulSet{}
    err = fakeClient.Get(ctx, ..., sts)
    assert.NoError(t, err)
}
```

### 10.2 結合テスト

実 Kubernetes(kind、minikube、テスト用 kubeadm)で起動して、シナリオを回す。

```bash
# kind でテスト用クラスタ
kind create cluster --name op-test
make install            # CRD 反映
make deploy             # Operator 起動

# シナリオ実行
kubectl apply -f testdata/normal.yaml
sleep 30
kubectl get sts -n test ...
```

### 10.3 E2E テスト

実環境に近い形で、フェイルオーバー / ノード障害 / バックアップリストア など。Chaos Mesh と組み合わせるとカオステストも可能。

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: kill-primary
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces: [prod]
    labelSelectors:
      cnpg.io/cluster: postgres
      cnpg.io/instanceRole: primary
```

---

## 11. Operator パターンの限界・落とし穴

万能ではありません。よくある罠を列挙します。

### 11.1 Operator の暴走

バグのある Operator が **無限に Pod を作る** / **無限に再起動させる** ことがあります。

対策:

- リソース上限(LimitRange / ResourceQuota)を Namespace に必ず付ける
- `kubectl get events` を監視
- Operator の **rate limiting** を確認(controller-runtime はデフォルトで設定済み)

### 11.2 API バージョンアップ時の互換性

CRD のスキーマを変えると、既存 CR が不適合になることがある。**Conversion Webhook** を書くか、互換的変更にとどめる。

### 11.3 Finalizer の永久ループ

外部システム削除に失敗し続けて、Finalizer がいつまでも消えない → CR が Terminating のまま残る。

対策:

- Finalizer 処理に **タイムアウト** を入れる
- 失敗時は **status に記録** して人間が判断
- 緊急時は `kubectl patch ... finalizers=[]` で外す(ただし後始末がされない)

### 11.4 Operator 自体の更新

Operator のバージョンアップで CR の挙動が変わると、本番障害になる。

対策:

- Staging で十分検証
- Operator Lifecycle Manager (OLM) を使う(Subscription による自動更新の制御)
- 重要 Operator は手動更新を貫く

### 11.5 「全部 Operator 化」しがち

何でも Operator にする病。シンプルな Helm Chart で済むものまで CRD を作って肥大化。

判断:

- アプリのライフサイクル管理に **継続的な reconcile が必要か?**
- それとも **一度デプロイすれば終わり?**
- 後者なら Helm / Kustomize で十分

### 11.6 学習コストの過小評価

Operator 開発は「アプリの運用ノウハウ」+「Kubernetes API 内部」+「Go(または Python)」+「分散システム」の合流地点。
**新人 1 人に丸投げで作らせると 2 年後に技術負債になる** のはよくあるパターン。

---

## 12. デバッグとトラブルシュート

### 12.1 よくある症状と対処

| 症状 | 原因 | 対処 |
|------|------|------|
| CR を作っても何も起きない | Operator Pod が起動していない | `kubectl get pod -n cnpg-system` 確認 |
| Operator Pod が CrashLoop | RBAC 不足、CRD 未登録 | logs と describe |
| CR を消しても Pod が消えない | Finalizer が残ってる | `kubectl patch ... finalizers=[]` で確認 |
| 子リソース(StatefulSet)が更新されない | Operator の Reconcile に失敗 | Operator の logs を見る |
| Reconcile が無限ループ | status update で spec が変わってる | コード見直し |
| カスタム CRD が `kubectl get` で見えない | CRD が Cluster Scope なのに Namespace 指定 | `kubectl get <name> -A` で全 Namespace 確認 |
| Webhook タイムアウト | Operator Pod から Webhook サービスに到達できない | NetworkPolicy / Service / 証明書を確認 |

### 12.2 調査フロー

```mermaid
flowchart TB
    s[CRが期待通り動かない] --> q1{Operator Pod<br>Running?}
    q1 -->|No| s1[Operator Pod の Events と logs]
    q1 -->|Yes| q2{CRD 登録済み?}
    q2 -->|No| s2[CRD apply 確認]
    q2 -->|Yes| q3{CR の status は?}
    q3 -->|空| s3[Operator が CR を見つけてない<br>label selector・namespace 確認]
    q3 -->|エラー| s4[エラーメッセージから判断]
    q3 -->|Processing| s5[一旦待つ、長時間続くなら logs]
    s4 --> end1[修正して再 apply]
    s5 --> end1
```

### 12.3 Operator のログを読む

CNPG の場合:

```bash
kubectl logs -n cnpg-system deploy/cnpg-controller-manager -f --tail=200
```

ログレベル変更:

```yaml
spec:
  containers:
  - name: manager
    args:
    - --log-level=debug          # info / debug / trace
```

---

## 13. 推奨学習リソース

- **Kubernetes 公式: Custom Resources**: <https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/>
- **Operator パターン**: <https://kubernetes.io/docs/concepts/extend-kubernetes/operator/>
- **kubebuilder Book**: <https://book.kubebuilder.io/>
- **OperatorHub.io**: <https://operatorhub.io/>
- **Programming Kubernetes** (O'Reilly、Hausenblas & Schimanski) ─ Operator 自作の名著
- **CloudNativePG ドキュメント**: <https://cloudnative-pg.io/documentation/>
- **CNCF KubeCon の Operator 関連トーク**: YouTube で "kubecon operator" 検索

---

## チェックポイント

ここまでで以下を **自分の言葉で** 説明できるか確認してください。

- [ ] Operator パターンが解決する具体的な課題を **3 つ以上** 列挙できる
- [ ] CRD と Custom Controller の関係を、Kubernetes ビルトインコントローラと対比して説明できる
- [ ] Operator Capability Level の Level 1 / 3 / 5 の違いを例とともに挙げられる
- [ ] CloudNativePG が提供する機能を **5 つ以上** 列挙できる(HA / Backup / PITR / 監視 / Service 自動生成 / アップグレード等)
- [ ] サンプルアプリの Postgres を CNPG に置き換える手順と、それで何が楽になるか説明できる
- [ ] 自作 Operator の選択肢(kubebuilder / Operator SDK / kopf / Metacontroller)の使い分け基準を持っている
- [ ] Finalizer と Owner Reference の役割の違いを説明できる
- [ ] CRD で `subresources.status: {}` を必ず付けるべき理由を説明できる
- [ ] Operator の暴走を防ぐ仕組み(ResourceQuota、Rate Limiting、staging 検証)を説明できる
- [ ] 「全部 Operator 化」病の判断基準を持っている

→ 次は [Service Mesh]({{ '/12-advanced/service-mesh/' | relative_url }})
