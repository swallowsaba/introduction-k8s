---
title: NFS 完全ガイド ― 仕組みから運用まで
parent: 05. ストレージ
nav_order: 4
---

# NFS 完全ガイド ― 仕組みから運用まで
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## このページのゴール

このページは「教材の中の 1 ページ」というよりも、**NFS というプロトコル・運用技術を体系的に身につけるための独立ガイド** として書かれています。Kubernetes でのストレージ運用は、CSI ドライバが何をしているのかを理解するために、その下にある **OS レベルでの NFS の挙動** を知っておくことが極めて重要だからです。

このページを読み終えると、以下を **自分の言葉で説明できる** ようになります。

- NFS というプロトコルの歴史と進化(NFSv2 → v3 → v4 → v4.1 → v4.2)を、それぞれが何を解決するために生まれたかという観点で理解している
- NFS の通信モデル(RPC over TCP、ポートマッパー、mountd / statd / lockd の役割)、および NFSv4 でそれらがどう統合されたか
- NFS のファイルセマンティクス(close-to-open consistency、ファイルハンドル、属性キャッシュ、delegation、silly rename、ロック)を、他のファイルシステムと比較して説明できる
- NFS と他のストレージプロトコル(iSCSI、SMB/CIFS、S3、CephFS、GlusterFS)の違いを、適性ワークロードを含めて述べられる
- Ubuntu 22.04 LTS Server でゼロから NFS サーバを構築できる(パッケージ、ストレージ準備、`/etc/exports`、`/etc/nfs.conf`、ファイアウォール、AppArmor、systemd まで)
- `/etc/exports` の全主要オプション(rw, sync/async, root_squash 系, subtree_check, secure, sec=, fsid, anonuid/anongid)の意味と影響を答えられる
- NFS クライアント側の mount オプション(nfsvers, hard/soft, timeo, retrans, rsize/wsize, ac/noac, lookupcache, nconnect, noatime, nolock など)を、それぞれ何のためのものか理解している
- NFS-CSI ドライバ(`nfs.csi.k8s.io`)のアーキテクチャと、Pod 起動時の RPC フローを図で書ける
- Helm と素の YAML の両方で NFS-CSI ドライバを Kubernetes クラスタにインストールでき、各 Pod の役割(`csi-nfs-controller`, `csi-nfs-node` の各サイドカー)を確認できる
- 静的 PV(個別 / 一括スクリプト / ラベルセレクタ運用)と、動的プロビジョニング(StorageClass の全 parameters)を、それぞれの用途で使い分けられる
- NFS のセキュリティ設計(`sec=sys` / Kerberos、root_squash と Pod の SecurityContext の組み合わせ、ネットワーク分離、NetworkPolicy)を立てられる
- NFS で起こる権限問題(UID 不一致、`fsGroup` 適用範囲、`fsGroupChangePolicy: OnRootMismatch`)の根本原因を説明し、回避手順を実行できる
- NFS のパフォーマンス特性を理解し、`fio` で測定し、`nconnect`、`rsize`/`wsize`、`nfsd` プロセス数、ネットワーク帯域、サーバ側ファイルシステムを調整できる
- HA NFS の代表的構成(DRBD + Pacemaker、GlusterFS、CephFS、商用アプライアンス)の選択肢を比較できる
- NFS のスナップショット・バックアップ戦略(LVM、ZFS、rsync、CSI VolumeSnapshot)を立てられる
- 主要な NFS トラブル(Stale file handle、`Connection refused`、`Operation not permitted`、`ContainerCreating` で詰まる、性能劣化)について、調査の第一手と典型対処を即答できる
- TODO サンプルアプリ(PostgreSQL StatefulSet、Redis StatefulSet、アップロード用 RWX PVC)を、NFS だけで動かしきれる

---

## なぜストレージ深堀りで NFS を選ぶのか

「Kubernetes 学習教材なら、もっとモダンな分散ストレージ(Longhorn、Ceph)で良いのでは?」と思うかもしれません。本教材があえて NFS をストレージの中心に据えているのには、明確な理由があります。

```mermaid
flowchart TB
    A[なぜ NFS を学ぶか] --> B[ローカル環境で<br>もっとも現実的]
    A --> C[OS レベルの動作が<br>透明で学習価値が高い]
    A --> D[業務でも<br>NFS バックエンドは現役]
    A --> E[トラブルが<br>たくさん起きる<br>= 学習機会]
    B --> B1[1 台の VM で構築可能]
    B --> B2[特殊ハードウェア不要]
    C --> C1[showmount, mount<br>でその場で確認できる]
    C --> C2[CSI 抽象を剥がして<br>本質を見られる]
    D --> D1[NetApp ONTAP]
    D --> D2[AWS EFS]
    D --> D3[Azure NetApp Files]
    D --> D4[GCP Filestore]
    E --> E1[権限、ロック、性能<br>すべてに教訓]
```

具体的に並べるとこうなります。

1. **ローカル環境でもっとも現実的な「複数ノード共有ストレージ」** ─ Longhorn や Ceph は本気で運用しようとすると数台のディスク + ネットワーク要件が厳しく、学習用 VM に乗せると CPU/メモリを食いつぶします。NFS なら 1 台の VM(本教材の `k8s-nfs` = `192.168.56.30`)に小さなディスクを足すだけで動きます。
2. **OS レベルの挙動が透明** ─ NFS のマウントは Linux カーネル本体の機能なので、`mount`、`df -hT`、`showmount`、`rpcinfo`、`nfsstat` などのコマンドでその場で観察できます。CSI ドライバが裏で何をやっているかが「見える」のは、Operator や CRD で抽象化された分散ストレージにはない大きな学習利点です。
3. **業務でも NFS バックエンドは現役** ─ NetApp ONTAP、Dell PowerScale(旧 Isilon)、Synology / QNAP、AWS EFS、Azure NetApp Files / Files、GCP Filestore など、エンタープライズの多くは NFS プロトコルを話すストレージを使っています。Kubernetes クラスタからこれらを使うには、結局 NFS の知識が必要になります。
4. **失敗のしどころが多い = 学べることが多い** ─ NFS は「動くようにするだけ」なら 5 分で済みますが、「**本番品質で動かす**」となると、ファイルロック、UID マッピング、`hard`/`soft` の選択、性能チューニング、HA、バックアップなど、ソフトウェアエンジニアが学ぶべき分散システムの教訓が一通り詰まっています。

{: .note }
> 本教材で構築する VMware kubeadm 環境では、`k8s-nfs` ノード(192.168.56.30)に NFS サーバを立てて、すべてのワーカーノード(`k8s-w1`〜`k8s-w3`)から共有ストレージとして使う構成を取ります。商用アプライアンスがある場合の差し替えポイントも明記します。

---

# 第 1 部: NFS プロトコルの基礎

## 1.1 NFS の歴史と進化

NFS(Network File System)は **1984 年に Sun Microsystems が発表した** UNIX 系ネットワークファイルシステムです。「ローカルディスクのファイルにアクセスするのと同じ API でリモートのファイルにアクセスできる」という、当時としては画期的な発想で、その後の業界デファクトとなりました。

```mermaid
timeline
    title NFS のバージョン進化
    1984 : NFSv1 (Sun 社内のみ)
    1989 : NFSv2 (RFC 1094)<br>UDP only / 2GiB ファイル制限
    1995 : NFSv3 (RFC 1813)<br>TCP / 64bit / 大幅性能改善
    2003 : NFSv4 (RFC 3530)<br>ステートフル化 / ACL / 単一ポート
    2010 : NFSv4.1 (RFC 5661)<br>セッション / pNFS
    2016 : NFSv4.2 (RFC 7862)<br>SSC / sparse / labelled NFS
```

各バージョンの **「何を解決するために生まれたか」** を理解することが重要です。

### NFSv2(1989, RFC 1094)

最初に標準化されたバージョン。シンプルですが、現代の目で見ると重大な制約がありました。

- **トランスポートは UDP のみ**(信頼性のないネットワークでは破綻)
- **ファイルサイズの上限が 2 GiB**(当時としては十分でも、すぐ足りなくなった)
- **書き込みが全て同期**(性能が出ない)
- **ステートレス**(サーバ側に状態を持たない、シンプルだが機能制限あり)

### NFSv3(1995, RFC 1813)

NFS が現代まで生き残ったのは、ほぼ NFSv3 のおかげと言っても過言ではありません。NFSv3 は実用上の問題を一気に解決しました。

- **TCP のサポート**(NFSv3 over TCP が事実上の標準)
- **ファイルサイズ 64bit**(2 GiB 制限を撤廃)
- **非同期書き込み**(`COMMIT` プロシージャで明示的にフラッシュ)
- **WCC(Weak Cache Consistency)** ─ 弱い一貫性モデル

ただし、**ステートレス** という設計は維持されました。これは「サーバが落ちてもクライアントは状態を再構築できる」という利点と、「ファイルロックや認証で別プロトコル(NLM、NSM)が必要」という欠点の両方を持ち込みました。NFSv3 では以下の **副プロトコル** が必要です。

| 副プロトコル | デーモン | 役割 |
|--------------|----------|------|
| Mount Protocol | `rpc.mountd` | エクスポート列挙、初期マウント時のファイルハンドル取得 |
| NLM(Network Lock Manager) | `rpc.lockd`(カーネル組み込み) | ファイルロック |
| NSM(Network Status Monitor) | `rpc.statd` | ロック復旧時のサーバ生存通知 |
| RPC Quota | `rpc.rquotad` | クォータ問い合わせ(オプション) |
| Portmapper(SUN-RPC) | `rpcbind`(旧 portmap) | 上記の動的ポート発見 |

これらすべてが UDP/TCP の **動的ポート** で待ち受けるため、ファイアウォール越しでの NFSv3 利用は地獄でした。

### NFSv4(2003, RFC 3530)

NFSv4 は **大幅な再設計** で、NFS を「現代のネットワークファイルシステム」へと進化させました。

- **ステートフル化** ─ サーバ側がクライアント状態を持つ。これにより delegation や強い一貫性が可能に
- **単一ポート 2049 のみ**(NFSv3 の副プロトコルすべてを統合) ─ ファイアウォール対応が劇的に改善
- **複合プロシージャ(COMPOUND)** ─ 複数の操作を 1 RPC でまとめて送信 → ラウンドトリップ削減
- **ACL のサポート**(POSIX ACL に近いセマンティクス)
- **強い認証(RPCSEC_GSS / Kerberos)** がプロトコルレベルで標準化
- **疑似ファイルシステム(pseudo filesystem)** ─ サーバルートからの単一の名前空間を提供
- **lock とマウントが本体プロトコルに統合**

{: .important }
> NFSv4 で最も実用的に大きな変化は **「ポート 2049/TCP 1 本だけで通信が完結する」** ことです。これにより、ファイアウォールルールを 1 行書けば NFS が通るようになり、クラウド環境やハイブリッドクラウドでの NFS 利用がぐっと現実的になりました。

### NFSv4.1(2010, RFC 5661)

NFSv4.1 は NFSv4 の重要な改良版です。

- **セッションモデル** ─ NFSv4 のクライアント識別を改善し、exactly-once セマンティクスを保証
- **pNFS(Parallel NFS)** ─ メタデータサーバとデータサーバを分離 → スケールアウト
- **directory delegation** ─ ディレクトリ単位の委譲

pNFS は分散ファイルシステムを NFS インターフェースで提供する設計で、NetApp ONTAP、IBM Spectrum Scale(GPFS)などが対応しています。

### NFSv4.2(2016, RFC 7862)

最新の安定版。NFSv4.1 をベースに次の機能を追加しました。

- **Server-Side Copy(SSC)** ─ クライアントを経由せずにサーバ間でファイルコピー
- **Sparse File** ─ 穴を持つファイル(VM イメージなど)を効率的に扱える
- **Application Data Block(ADB)** ─ アプリ意図のヒントをサーバに伝える
- **Labeled NFS** ─ SELinux ラベルの転送
- **Allocate / Deallocate / Seek** ─ POSIX ファイル拡張

Linux カーネル 4.0+ で NFSv4.2 はクライアント・サーバとも対応しています。Ubuntu 22.04 LTS のカーネル(5.15)はもちろん対応済みなので、本教材では **デフォルトで NFSv4.2** を使う想定です。

### バージョン選択の指針

```mermaid
flowchart TB
    A[NFS バージョン選び] --> B{ファイアウォール越し?}
    B -- Yes --> C[NFSv4.1+]
    B -- No --> D{Kerberos 必要?}
    D -- Yes --> C
    D -- No --> E{古い OS が混在?}
    E -- Yes --> F[NFSv3]
    E -- No --> C
    C --> G[本教材は v4.1+]
```

| 状況 | 推奨バージョン | 理由 |
|------|--------------|------|
| 新規構築 | **NFSv4.2** | フル機能、単一ポート |
| 既存 v3 環境への追加 | NFSv4.1 | サーバが対応していれば |
| 古い NAS 機器との互換 | NFSv3 | プロトコル単純で互換性が広い |
| 高セキュリティ要件 | NFSv4.1 + Kerberos | 認証・暗号化が必須 |
| pNFS 構成 | NFSv4.1 | データサーバ分離 |

---

## 1.2 NFS の通信モデル

NFS は **RPC(Remote Procedure Call)** の上に構築されたプロトコルです。クライアントがサーバの「関数」を呼び出すような形で、ファイル操作をリモートに実行します。

### NFS over RPC のレイヤ構造

```mermaid
flowchart TB
    subgraph App["アプリ"]
        a1[open / read / write / close]
    end
    subgraph VFS["Linux VFS 層"]
        v1[VFS]
    end
    subgraph NFS["NFS クライアント<br>(カーネルモジュール)"]
        n1[NFS RPC エンコード]
    end
    subgraph RPC["SUN-RPC レイヤ"]
        r1[XDR シリアライズ<br>RPC ヘッダ追加]
    end
    subgraph TCP["TCP/IP"]
        t1[TCP ポート 2049]
    end
    a1 --> v1 --> n1 --> r1 --> t1
```

| レイヤ | 役割 |
|--------|------|
| アプリケーション | `open`/`read`/`write` などの POSIX 呼び出し |
| Linux VFS | ファイルシステム抽象 |
| NFS クライアント(`fs/nfs/` カーネルモジュール) | NFS 固有の処理、属性キャッシュ |
| SUN-RPC | XDR シリアライゼーション、リクエスト管理 |
| TCP/IP | NFSv4 は通常 TCP/2049、NFSv3 は TCP or UDP |

### NFSv3 の通信(参考)

NFSv3 では多数のサーバプロセスが連携します。

```mermaid
sequenceDiagram
    participant C as クライアント
    participant PM as portmapper:111
    participant M as mountd:dyn
    participant N as nfsd:2049
    participant L as lockd:dyn
    C->>PM: getport(MOUNT)
    PM-->>C: 32812
    C->>M: MOUNT /export
    M-->>C: file handle
    C->>PM: getport(NFS)
    PM-->>C: 2049
    C->>N: READ / WRITE / GETATTR ...
    Note over C,L: ロック取得時
    C->>PM: getport(NLM)
    PM-->>C: 32813
    C->>L: NLM_LOCK
    L-->>C: granted
```

このように **動的ポート** が多数登場するため、ファイアウォールでは一筋縄ではいきません。

NFSv3 のサービスを固定ポートで動かしたい場合、`/etc/nfs.conf`(Ubuntu 22.04+)で各デーモンのポートを固定します。

```ini
# /etc/nfs.conf 抜粋
[mountd]
port=20048

[statd]
port=32765
outgoing-port=32766

[lockd]
port=32767
udp-port=32767
```

### NFSv4 の通信(本教材の主軸)

NFSv4 は劇的にシンプルです。**TCP の単一ポート 2049 だけ** ですべてが完結します。

```mermaid
sequenceDiagram
    participant C as クライアント
    participant N as NFSv4 サーバ:2049
    C->>N: SETCLIENTID(認証 + クライアント ID 確立)
    N-->>C: clientid
    C->>N: COMPOUND[PUTROOTFH, GETFH, GETATTR]
    N-->>C: file handle, attributes
    C->>N: COMPOUND[OPEN, READ]
    N-->>C: data
    C->>N: COMPOUND[LOCK, WRITE, UNLOCK]
    N-->>C: ok
    C->>N: COMPOUND[CLOSE, RENEW]
```

`COMPOUND` プロシージャで **複数の操作を 1 つの RPC にまとめられる** ため、ラウンドトリップが減って性能が良くなります。たとえば「PUTROOTFH(ルートに移動) → LOOKUP(name) → OPEN → READ」を 1 RPC で送れます。

### ポート一覧

| バージョン | ポート | プロトコル | 役割 |
|-----------|-------|-----------|------|
| NFSv4 / 4.1 / 4.2 | 2049/TCP | TCP | すべての操作 |
| NFSv3 | 2049/TCP or UDP | NFS | データ |
| NFSv3 | 111/TCP, 111/UDP | portmapper | ポート発見 |
| NFSv3 | 動的(固定可) | mountd | 初期マウント |
| NFSv3 | 動的(固定可) | lockd | ロック |
| NFSv3 | 動的(固定可) | statd | ステータス通知 |

本教材では NFSv4.1+ を使うので、**192.168.56.30:2049/TCP を 1 ポート開ければ完了** です。

---

## 1.3 NFS のファイルセマンティクス

NFS が「ローカル FS と同じ感覚で使える」と言うときの裏で、実際には微妙な動作の違いがあります。これを知らないとアプリの整合性で痛い目に遭います。

### Close-to-Open(CTO)Consistency

NFS の根本的な一貫性モデルです。

- **OPEN 時に**、サーバから最新の属性を取り直す
- **CLOSE 時に**、ローカルでバッファしていた書き込みをすべてサーバへ送る

これにより、「**書いた側が CLOSE してから、読む側が OPEN する**」順序が守られれば一貫性が保証されます。

```mermaid
sequenceDiagram
    participant W as Writer Pod
    participant N as NFS サーバ
    participant R as Reader Pod
    W->>W: write() (ローカルバッファ)
    W->>N: close() で flush
    Note over N: ファイル更新確定
    R->>N: open() で属性取得
    R->>R: read() で最新内容
```

逆に、**両方が同時にファイルを開いたまま** だとキャッシュ整合性は崩れます。これが「NFS でファイルベースの IPC をするときに `flush + close` が必要」と言われる理由です。

### ファイルハンドル(File Handle)

NFS は「inode」の代わりに **ファイルハンドル** という不透明なバイト列でファイルを識別します。

- マウント時にルートのファイルハンドルを取得
- LOOKUP でサブディレクトリ・ファイルのハンドルを順次取得
- 以降のすべての操作はハンドルで指定

ファイルハンドルが **無効になる(stale)** とエラーになります。代表的なシナリオ:

- サーバ側でファイルを削除した後、クライアントがそのハンドルで操作を試みた
- サーバ側でファイルシステムを再マウントしてハンドル空間が変わった
- バックアップ復元でファイルが置き換わった(同名でも別 inode)

```bash
$ ls /mnt/nfs
ls: cannot access '/mnt/nfs/foo': Stale file handle
```

このエラーが出たときは、**マウントしなおす** か **クライアント側のキャッシュを破棄する** のが基本対処です。

### 属性キャッシュ(attribute caching)

毎回サーバに `stat()` を投げると遅すぎるので、NFS クライアントは属性をキャッシュします。

| マウントオプション | 既定値 | 意味 |
|-------------------|--------|------|
| `acregmin` | 3 秒 | 通常ファイル属性キャッシュの最小 |
| `acregmax` | 60 秒 | 通常ファイル属性キャッシュの最大 |
| `acdirmin` | 30 秒 | ディレクトリ属性キャッシュの最小 |
| `acdirmax` | 60 秒 | ディレクトリ属性キャッシュの最大 |
| `actimeo=N` | (上記の代わりに一括設定) | すべて N 秒 |
| `noac` | (なし) | 属性キャッシュ完全無効化 ─ **激遅** |

**`noac` は安易に付けないでください**。「データ整合性のために必要」と書かれているマニュアルを見ても、まずは `actimeo=1` のような小さい値で済むか試すべきです。

### Delegation(NFSv4 以降)

NFSv4 では、サーバがクライアントに **「このファイルは君が独占して使ってよい」** と委譲することができます。これがあると、属性問い合わせや書き込みフラッシュをスキップできて高速化します。

- **READ delegation** ─ 読み取り専用の委譲
- **WRITE delegation** ─ 書き込み込みの委譲

ただし、別クライアントがそのファイルを開きにくると **委譲が呼び戻されます(recall)**。

### サイレントリネーム(Silly Rename)

NFS には POSIX の「openしたままunlink」セマンティクスを再現するための独特な仕組みがあります。あるクライアントが開いているファイルを、同じクライアントが `unlink` した場合、NFS は実際には削除せず `.nfs0123abcd` のような **隠し名にリネーム** します。最後の `close` でクライアントが本当に削除します。

```bash
# ある Pod が開いている log.txt を rm すると...
$ ls -la /export
.nfs00000fe900000001
# .nfs ファイルが残る
```

ノード障害でクライアントが死ぬとこの **`.nfs*` ファイルが残ります**。`find /export -name '.nfs*' -mtime +7` で定期掃除する運用をする現場もあります。

### ロック(File Locking)

NFS のロックは歴史が深く、**バージョンと OS 実装に依存** します。

| バージョン | ロック方式 | 信頼度 |
|-----------|-----------|--------|
| NFSv3 | NLM(別プロトコル) | △ 障害時の整合性に弱点 |
| NFSv4+ | プロトコル組み込み | ◎ ステートフル管理で堅実 |

PostgreSQL のように `fcntl` ベースのロックを大量に使うアプリでは、**NFSv3 ではデータ破損の事例があり**、NFSv4 以上が必須です。

### キャッシュ全体像

```mermaid
flowchart LR
    subgraph Cli[NFS クライアント]
        ac[属性キャッシュ<br>acregmin/max]
        dc[ページキャッシュ<br>read/write バッファ]
        lc[ルックアップキャッシュ<br>lookupcache]
    end
    subgraph Srv[NFS サーバ]
        sc[サーバキャッシュ<br>OS のページキャッシュ]
        fs[ファイルシステム<br>ext4/XFS/ZFS]
    end
    Cli <--> Srv
    sc --> fs
```

クライアント側で 3 種類、サーバ側で 1 種類のキャッシュがあります。整合性問題が起きたら、まずどのキャッシュが原因かを切り分けます。

---

## 1.4 NFS と他のストレージプロトコルの比較

| 軸 | NFS | iSCSI | SMB/CIFS | S3 | CephFS | GlusterFS |
|----|-----|-------|----------|-----|--------|-----------|
| 抽象 | ファイル | ブロック | ファイル | オブジェクト | ファイル | ファイル |
| 共有 | 複数クライアント可 | 通常 1 イニシエータ | 複数可 | 制限なし | 複数可 | 複数可 |
| OS | UNIX 系 | OS 中立 | Windows 系 | OS 中立(HTTP) | UNIX 系 | UNIX 系 |
| Kubernetes | RWO/RWX | RWO のみ | RWO/RWX | 直接 RW 不可 | RWO/RWX | RWO/RWX |
| トランザクション性能 | △ | ◎ | △ | × | ○ | ○ |
| スケーラビリティ | △(スケールアップ) | ◎ | △ | ◎ | ◎ | ◎ |
| セットアップ難度 | 易 | 易 | 易 | 易(クラウド) | 難 | 中 |
| 学習価値 | ◎ | ◎ | ○ | ○ | ◎ | ○ |

### NFS と iSCSI

- **NFS はファイル抽象**(複数クライアントから同時アクセス可、ファイル単位の操作)
- **iSCSI はブロック抽象**(SAN として動作、通常 1 ホスト独占)

データベースの本番では iSCSI(LUN を切って ext4 で使う)が主流ですが、**Kubernetes で iSCSI を使うなら CSI ドライバが必要** で、しかも RWO のみ。「複数 Pod で共有したい」要件があれば NFS のほうが直球です。

### NFS と SMB/CIFS

- どちらもファイル共有プロトコル
- SMB は Windows 系で標準、UNIX 系では Samba 経由
- 機能差は縮小しているが、Linux 主体なら NFS がシンプル

Active Directory との統合が必要なら SMB(`samba-csi` ドライバ)、純 Linux クラスタなら NFS が定石です。

### NFS と S3

- **S3 はオブジェクトストレージ**(HTTP API、PUT/GET/LIST)
- POSIX セマンティクスは持たない(rename はコピー&削除)
- データベースの永続化には不向き
- ログ・バックアップ・静的アセット保管には最適

両者は **競合ではなく補完関係** です。本教材では NFS をプライマリストレージ、MinIO(S3 互換)を Velero などのバックアップ先として併用します。

### NFS と CephFS / GlusterFS

CephFS と GlusterFS は **「複数ノードのローカルディスクを集めて分散ファイルシステムを作る」** タイプです。NFS とは真逆のスケールアウト型。

- **NFS** ─ サーバ 1 台 + 共有(SPOF、ただし運用シンプル)
- **CephFS / GlusterFS** ─ クラスタ全体で分散・レプリケート(SPOF なし、ただし運用複雑)

学習・小規模なら NFS、大規模ならスケールアウト型が向きます。

---

## 1.5 NFS が向く / 向かないワークロード

```mermaid
flowchart TB
    A[ワークロード] --> B{特性は?}
    B --> C[読み取り中心<br>多数 Pod 共有]
    B --> D[書き込み中心<br>低レイテンシ]
    B --> E[巨大ファイル<br>シーケンシャル]
    B --> F[多数小ファイル<br>ランダム]
    C --> NFS_OK[NFS ◎]
    D --> NFS_NG[NFS △ <br>iSCSI/local 推奨]
    E --> NFS_OK
    F --> NFS_DEP[NFS ○ チューニング前提]
```

### NFS が向くワークロード

- **静的 Web アセット**(HTML/CSS/JS、画像、動画)─ 多数 Pod から RWX で読み取り
- **共有ログ収集ディレクトリ** ─ Fluentd / Vector の集約先
- **ML データセット** ─ 大量の画像・テキストを多数 Pod が読み取る
- **共有設定ディレクトリ** ─ 各 Pod が共通の設定ファイルを読む(ConfigMap で足りないとき)
- **CI/CD のキャッシュ** ─ ビルド成果物の中間保管
- **PVC のバックアップ先** ─ Velero の File System Backup ターゲット

### NFS が向かないワークロード

- **OLTP データベース**(高頻度小トランザクション)─ レイテンシがボトルネック、ロックリスク
- **etcd / Consul などの consensus ストア** ─ 専用ローカル SSD が必須
- **VM ディスクイメージ**(高 IOPS 書き込み)─ ブロックストレージ向け
- **ステートフルなメッセージブローカー(Kafka)** ─ シーケンシャル書き込みは可能だが、本番ではローカル SSD レプリケーション推奨

### TODO サンプルアプリでの判断

本教材の TODO サービスでは、各コンポーネントを以下の方針で配置します。

| コンポーネント | ストレージ | 理由 |
|--------------|------------|------|
| PostgreSQL(StatefulSet) | NFS(学習) / 本番なら local SSD + レプリケーション | 学習目的では NFSv4.1+ で十分。性能要件が出たら移行 |
| Redis(StatefulSet) | NFS | RDB スナップショットなので書き込み少 |
| Worker(CronJob) | ボリューム不要 | 状態を持たない |
| アップロード保管 | NFS RWX | 複数 API Pod で共有 |
| バックアップ | MinIO(S3 互換) | Velero ターゲット |
| ログアーカイブ | NFS | 集約読み取り |

**「本番品質を求めるなら、PostgreSQL は NFS から離す」** ことを設計時の前提として頭に入れておきます。

---

## 1.6 第 1 部のまとめ

ここまでで NFS の **「中で何が起きているのか」** という理解の土台ができました。ポイントを再確認します。

- NFSv4.1+ なら単一 TCP ポート 2049 で完結し、ファイアウォール対応が容易
- NFSv4 はステートフルになり、delegation や強い一貫性が利用可能
- 一貫性モデルは close-to-open。「同時に開いたままの整合性」は別途仕組みが必要
- ファイルロックは NFSv4+ で堅実だが、PostgreSQL のような fcntl 大量利用アプリでは慎重に
- 属性キャッシュ・ページキャッシュ・ルックアップキャッシュの 3 段階を意識する
- ワークロード適性を判断: 共有読み取りや巨大シーケンシャル書き込みは得意、低レイテンシ OLTP は苦手

第 2 部では実際に **NFS サーバを構築** していきます。

---

# 第 2 部: NFS サーバの完全構築

ここからはハンズオン形式で、本教材の `k8s-nfs`(192.168.56.30)に NFS サーバを構築します。Ubuntu 22.04 LTS Server を前提としますが、他のディストリビューションでもパッケージ名が違うだけで本質は同じです。

## 2.1 環境設計

### ハードウェア / VM スペック

```mermaid
flowchart LR
    subgraph PM[物理 / VMware ホスト]
        VM[k8s-nfs<br>192.168.56.30]
    end
    VM --- Disk1[OS ディスク<br>20 GiB]
    VM --- Disk2[NFS データディスク<br>50〜100 GiB]
```

| 項目 | 推奨 | 最低限 |
|------|------|--------|
| vCPU | 2 | 1 |
| RAM | 2 GiB | 1 GiB |
| OS ディスク | 20 GiB | 10 GiB |
| NFS データディスク | 50 GiB(別ディスク) | 10 GiB(同居可) |
| ネットワーク | 1 GbE 以上 | 100 Mbps |

**OS と NFS データを物理的に別ディスク** に置くのが本番作法です。理由:

1. ディスク I/O の競合回避
2. NFS データだけスナップショット・リサイズしやすい
3. 障害時の切り分けが容易

学習環境でも、VMware で「2 つ目の VMDK」を追加するだけなのでぜひやっておきましょう。

### ネットワーク設計

VMware Host-only(VMnet1)で `192.168.56.0/24` を使う前提です。

```
192.168.56.10  k8s-lb       (HAProxy + Registry)
192.168.56.11  k8s-cp1
192.168.56.12  k8s-cp2
192.168.56.13  k8s-cp3
192.168.56.21  k8s-w1
192.168.56.22  k8s-w2
192.168.56.23  k8s-w3
192.168.56.30  k8s-nfs      ← 今回構築する
```

NFS サーバは **クラスタ内ネットワークだけにエクスポート** します(`192.168.56.0/24` のみ許可)。インターネットには絶対に晒さないこと。

### ストレージ設計

NFS データ用ディスクを **LVM で構築** することを強く推奨します。

```mermaid
flowchart LR
    sd[/dev/sdb<br>50GiB] --> pv[PV pv0]
    pv --> vg[VG nfs_vg]
    vg --> lv[LV nfs_lv<br>50GiB ext4]
    lv --> mnt[/srv/nfs にマウント]
```

LVM を使う利点:

- **オンライン拡張**(`lvextend` + `resize2fs`)が安全
- **スナップショット** が取れる(バックアップ用)
- **複数 LV に分割** すれば、用途ごとに別配置できる

### ディレクトリ階層

```
/srv/nfs/                      # NFS データ用 LV のマウントポイント
├── k8s/
│   ├── static/                # 静的 PV 用(個別 PV を手動で切る)
│   │   ├── postgres-01/
│   │   ├── shared-uploads/
│   │   └── ml-datasets/
│   ├── dynamic/               # 動的プロビジョニング用(NFS-CSI が自動生成)
│   │   └── (PVC ごとに自動生成)
│   └── backup/                # バックアップ用(rsync 受け先など)
└── lost+found/                # ext4 のおきまり
```

`/etc/exports` ではこれらをそれぞれ別エクスポートとして公開します。

---

## 2.2 OS インストールと初期設定

### Ubuntu 22.04 LTS Server インストール

VMware で新規 VM を作成し、Ubuntu 22.04 LTS Server の ISO からインストールします。

- ホスト名: `k8s-nfs`
- ユーザ: `ubuntu`(自由)
- ネットワーク: 192.168.56.30/24、ゲートウェイは設定しない(またはクラスタ内ルータ)
- パーティション: OS は `/dev/sda` 全体、データディスクは後でフォーマット
- インストール時の追加パッケージ: 「OpenSSH server」のみチェック

### 初期設定

ログイン後、まず最低限の設定をします。

```bash
# パッケージ更新
sudo apt update && sudo apt upgrade -y

# ホスト名確認
hostnamectl
# Static hostname: k8s-nfs

# 自分の IP 確認
ip -4 addr show
# 192.168.56.30/24

# 全クラスタノードを /etc/hosts に登録
sudo tee -a /etc/hosts <<EOF
192.168.56.10 k8s-lb
192.168.56.11 k8s-cp1
192.168.56.12 k8s-cp2
192.168.56.13 k8s-cp3
192.168.56.21 k8s-w1
192.168.56.22 k8s-w2
192.168.56.23 k8s-w3
192.168.56.30 k8s-nfs
EOF

# sudo パスワードなしを設定(学習環境のみ。本番は禁止)
echo "ubuntu ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/ubuntu
sudo chmod 0440 /etc/sudoers.d/ubuntu
```

### 時刻同期

NFS は **タイムスタンプを多用** するため、サーバとクライアントの時刻ずれは様々な不具合の原因になります。

```bash
# chrony をインストール
sudo apt install -y chrony

# 設定確認
sudo systemctl status chrony

# NTP ソース確認
chronyc sources -v

# 時刻同期状態確認
chronyc tracking
# Reference ID    : ...
# Stratum         : 3
# System time     : 0.000123456 seconds slow of NTP time
```

クラスタ全ノードで chrony が動いていることを確認してください。

### 不要サービスの無効化

学習環境なら気にしなくても良いですが、本番では:

```bash
# Apache や Postfix のような勝手に入っているサービスを止める
sudo systemctl list-unit-files --state=enabled | grep -v ssh
```

---

## 2.3 NFS サーバパッケージのインストール

```bash
# NFS サーバパッケージ
sudo apt install -y nfs-kernel-server nfs-common

# バージョン確認
dpkg -l nfs-kernel-server
# nfs-kernel-server  1:2.6.1-1ubuntu1.2
```

### 関連デーモンの確認

```bash
# 起動しているサービスを確認
sudo systemctl status nfs-server.service
sudo systemctl status nfs-mountd.service
sudo systemctl status rpc-statd.service
sudo systemctl status rpcbind.service

# RPC エンドポイント確認
sudo rpcinfo -p localhost
#    program vers proto   port  service
#     100000    4   tcp    111  portmapper
#     100000    3   tcp    111  portmapper
#     100000    4   udp    111  portmapper
#     100024    1   udp  35831  status
#     100024    1   tcp  43719  status
#     100003    3   tcp   2049  nfs
#     100003    4   tcp   2049  nfs
#     100227    3   tcp   2049
#     100021    1   udp  53329  nlockmgr
#     100021    1   tcp  35395  nlockmgr
#     100005    1   udp  47265  mountd
#     100005    1   tcp  39131  mountd
#     ...
```

NFSv4 だけを使うなら、本来 `mountd`、`statd`、`lockd`、`rpcbind` は不要なのですが、Linux のサーバ実装では NFSv3 互換のために起動されます。クラスタ内専用なら問題ありませんが、ファイアウォール厳格運用なら NFSv4-only モードに切替できます(2.7 節)。

### サーバが対応しているバージョンの確認

```bash
cat /proc/fs/nfsd/versions
# +3 +4 +4.1 +4.2

# 個別に有効/無効を確認(`-`=無効、`+`=有効)
```

`+` は有効、`-` は無効を意味します。本教材では NFSv4.1+ を主に使うので、デフォルトで OK です。

---

## 2.4 ストレージ準備(LVM + ext4)

### データディスクの確認

```bash
# 接続されているディスクを確認
lsblk
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
# sda      8:0    0   20G  0 disk
# ├─sda1   8:1    0    1G  0 part /boot/efi
# ├─sda2   8:2    0    2G  0 part /boot
# └─sda3   8:3    0   17G  0 part /
# sdb      8:16   0   50G  0 disk     ← 追加した NFS データディスク
```

### LVM のセットアップ

```bash
# 必要パッケージ
sudo apt install -y lvm2

# 1. PV(Physical Volume)を作成
sudo pvcreate /dev/sdb
#   Physical volume "/dev/sdb" successfully created.

sudo pvs
#   PV         VG     Fmt  Attr PSize   PFree
#   /dev/sdb          lvm2 ---   50.00g 50.00g

# 2. VG(Volume Group)を作成
sudo vgcreate nfs_vg /dev/sdb
#   Volume group "nfs_vg" successfully created

sudo vgs
#   VG     #PV #LV #SN Attr   VSize  VFree
#   nfs_vg   1   0   0 wz--n- 50.00g 50.00g

# 3. LV(Logical Volume)を作成
# 全容量を使うなら -l 100%FREE
sudo lvcreate -n nfs_lv -l 100%FREE nfs_vg
#   Logical volume "nfs_lv" created.

sudo lvs
#   LV     VG     Attr       LSize
#   nfs_lv nfs_vg -wi-a----- 50.00g

# 4. ファイルシステムを作る
sudo mkfs.ext4 -L nfs_data /dev/nfs_vg/nfs_lv
```

{: .note }
> **ext4 vs XFS vs ZFS の選択**
>
> | FS | 特徴 | NFS バックエンドとして |
> |----|------|-------------------------|
> | ext4 | Linux 標準、安定、機能控えめ | ◎ 学習・小〜中規模 |
> | XFS | 大規模ファイル・並列書き込み強い | ◎ 大規模、特に大ファイル |
> | ZFS | スナップショット・圧縮・チェックサム | ◎ バックアップ機能を求めるなら |
>
> 本教材は ext4 を採用します。XFS なら `mkfs.xfs` に変えるだけです。ZFS は別途 `zfsutils-linux` 必要。

### マウント設定

```bash
# マウントポイント作成
sudo mkdir -p /srv/nfs

# 一時マウント
sudo mount /dev/nfs_vg/nfs_lv /srv/nfs

# 確認
df -hT /srv/nfs
# Filesystem               Type   Size  Used Avail Use% Mounted on
# /dev/mapper/nfs_vg-nfs_lv ext4   49G   24K   47G   1% /srv/nfs

# /etc/fstab に永続化
echo "/dev/nfs_vg/nfs_lv  /srv/nfs  ext4  defaults,noatime  0  2" | sudo tee -a /etc/fstab

# 検証(mount -a でエラーが出ないこと)
sudo mount -a
```

{: .important }
> **`/etc/fstab` を書き換えたら必ず `sudo mount -a` で検証してから再起動** すること。fstab に記述ミスがあるとブート時に `emergency mode` に落ちて、シリアルコンソール接続が必要になります。

### `noatime` オプションの効果

`noatime` は **「ファイルアクセス時の atime(アクセスタイムスタンプ)更新を抑制する」** マウントオプションで、NFS バックエンドでは性能が体感で 10〜30% 改善します(read のたびに inode 書き込みが発生しなくなる)。

### ディレクトリ階層作成

```bash
# 階層を作る
sudo mkdir -p /srv/nfs/k8s/{static,dynamic,backup}

# 所有者・パーミッションを設定
# 学習環境では nobody:nogroup に
sudo chown -R nobody:nogroup /srv/nfs/k8s
sudo chmod -R 0777 /srv/nfs/k8s    # 緩い設定。本番では 0750 + UID 個別

# 確認
ls -la /srv/nfs/k8s
# drwxrwxrwx 5 nobody nogroup 4096 ... .
# drwxr-xr-x 3 root   root    4096 ... ..
# drwxrwxrwx 2 nobody nogroup 4096 ... backup
# drwxrwxrwx 2 nobody nogroup 4096 ... dynamic
# drwxrwxrwx 2 nobody nogroup 4096 ... static
```

### 静的 PV 用のサブディレクトリを準備

```bash
# 例: postgres-static-01 という静的 PV 用
sudo mkdir -p /srv/nfs/k8s/static/postgres-static-01
sudo chown 999:999 /srv/nfs/k8s/static/postgres-static-01    # PostgreSQL 公式イメージの UID
sudo chmod 0750 /srv/nfs/k8s/static/postgres-static-01

# 例: 共有アップロードディレクトリ
sudo mkdir -p /srv/nfs/k8s/static/shared-uploads
sudo chown 1000:1000 /srv/nfs/k8s/static/shared-uploads
sudo chmod 0775 /srv/nfs/k8s/static/shared-uploads
```

UID/GID については 8 部で詳述しますが、**Pod の `runAsUser` / `fsGroup` と一致** させるのが基本です。

---

## 2.5 /etc/exports 完全マスター

`/etc/exports` は NFS サーバの **エクスポート定義ファイル** です。「どのディレクトリを、誰に、どのように公開するか」をここで決めます。

### 基本フォーマット

```
<共有パス> <クライアント1>(<オプション>) <クライアント2>(<オプション>) ...
```

### 本教材の最終的な /etc/exports

```bash
sudo tee /etc/exports <<'EOF'
# Kubernetes クラスタ用 NFS エクスポート
# 構成: 192.168.56.0/24 のクラスタ内 IP からのみ許可

# 静的 PV 用ルートディレクトリ(個別 PV ごとにサブディレクトリを公開してもよい)
/srv/nfs/k8s/static  192.168.56.0/24(rw,sync,no_subtree_check,no_root_squash,fsid=10)

# 動的プロビジョニング用(NFS-CSI が PVC ごとにサブディレクトリを作る)
/srv/nfs/k8s/dynamic 192.168.56.0/24(rw,sync,no_subtree_check,no_root_squash,fsid=20)

# バックアップ用(rsync ターゲット、書き込み制限)
/srv/nfs/k8s/backup  192.168.56.10/32(rw,sync,no_subtree_check,no_root_squash,fsid=30) \
                     192.168.56.0/24(ro,sync,no_subtree_check,fsid=30)
EOF
```

この一見短い設定ですが、各オプションの意味を理解することが本セクションの目的です。

### クライアント指定の書き方

| 書き方 | 意味 |
|--------|------|
| `192.168.56.30` | 単一 IP |
| `192.168.56.0/24` | CIDR(推奨) |
| `192.168.56.0/255.255.255.0` | サブネットマスク形式(古い) |
| `*.example.com` | DNS ワイルドカード(逆引き必須) |
| `@admin` | NIS グループ(現代では使わない) |
| `*` | 全許可(本番では絶対使わない) |

### 主要オプション完全リファレンス

#### 読み書き / 同期

| オプション | 意味 | 推奨 |
|-----------|------|------|
| `rw` | 読み書き許可 | 通常 |
| `ro` | 読み取り専用 | バックアップ参照、配布用 |
| `sync` | 書き込みを安定ストレージに反映してから ACK | **デフォルト・推奨** |
| `async` | カーネルバッファに入った時点で ACK | 性能優先(データ損失リスクあり) |

`sync` vs `async` の選択は **重要** です。

```mermaid
sequenceDiagram
    participant C as Client
    participant S as NFS Server
    participant D as Disk
    Note over C,D: sync モード
    C->>S: WRITE
    S->>D: 物理書き込み
    D-->>S: 完了
    S-->>C: ACK
    Note over C,D: async モード
    C->>S: WRITE
    S->>S: メモリバッファに保存
    S-->>C: ACK (即時)
    S->>D: 後で書き込み
```

`async` は書き込みが速いように **見えます** が、サーバが電源断で落ちると、ACK 済みデータがディスクに到達していない可能性があります。**データベースバックエンドでは絶対に sync を使うこと**。`async` を選ぶのは「性能テスト中」「使い捨てキャッシュ」など、データ消失を許容できる場面のみです。

#### 認証 / ID マッピング

| オプション | 意味 |
|-----------|------|
| `root_squash` | クライアントの root(UID 0)をサーバの `nobody`(`anonuid`)にマップ |
| `no_root_squash` | クライアントの root をそのまま root として扱う |
| `all_squash` | すべての UID を `anonuid` にマップ |
| `no_all_squash` | UID を尊重(デフォルト) |
| `anonuid=N` | squash 時のターゲット UID(デフォルト 65534) |
| `anongid=N` | squash 時のターゲット GID |

```mermaid
flowchart TB
    A[クライアント Pod の UID 0] --> B{root_squash?}
    B -- Yes (デフォルト) --> C[サーバで UID 65534<br>nobody として書き込み]
    B -- No --> D[サーバで UID 0<br>root として書き込み]
```

{: .warning }
> **`no_root_squash` の危険性**
>
> `no_root_squash` を有効にすると、**NFS クライアント側で `root` として動く Pod がサーバ側のファイルを `chown` できる** ようになります。これは Kubernetes 上で「悪意のある Pod が NFS サーバを乗っ取る」攻撃面につながります。
>
> 本教材では **クラスタ内ネットワーク限定 + 学習目的** で `no_root_squash` を許容していますが、本番では `root_squash` がデフォルトです。代わりに以下のいずれかで対処します。
>
> 1. Pod を `runAsNonRoot: true` で起動し、UID/GID を NFS サーバ側の所有者と一致させる
> 2. NFS-CSI ドライバの `mountPermissions` を使う
> 3. すべての Pod を `securityContext.fsGroup` で同一 GID に統一
>
> 詳しくは「第 7 部: セキュリティ」「第 8 部: 権限問題完全攻略」で扱います。

#### サブツリーチェック

| オプション | 意味 | 推奨 |
|-----------|------|------|
| `subtree_check` | エクスポートされたディレクトリのサブツリーかを毎回検査 | 古い、性能低下 |
| `no_subtree_check` | チェックしない | **現代の推奨** |

`no_subtree_check` は NFS v3 以降で実用上の問題はなく、`exportfs` も警告を出すほどなので **必ず指定** します。

#### ポート制限

| オプション | 意味 |
|-----------|------|
| `secure` | クライアントが特権ポート(<1024)から接続することを要求(デフォルト) |
| `insecure` | 任意ポートを許可 |

クラウド環境やコンテナで NAT を経由するときは `insecure` が必要なケースがあります。

#### fsid

| オプション | 意味 |
|-----------|------|
| `fsid=N` | エクスポートに固有の番号を割り当てる。NFSv4 で **必須** |
| `fsid=root` または `fsid=0` | 疑似ファイルシステムのルート(NFSv4) |

NFSv4 は **疑似ファイルシステム** という概念を持ちます。複数のエクスポートをサーバ上の単一ツリーから見えるように統合する仕組みです。

```mermaid
flowchart TB
    subgraph Server[NFS サーバの実ファイルシステム]
        a[/srv/nfs/k8s/static]
        b[/srv/nfs/k8s/dynamic]
    end
    subgraph Pseudo[NFSv4 クライアントから見えるツリー]
        r[/]
        s[/static<br>fsid=10]
        d[/dynamic<br>fsid=20]
        r --> s
        r --> d
    end
    a -.fsid=10.-> s
    b -.fsid=20.-> d
```

`fsid=0` を持つエクスポートが「ルート」になり、他のエクスポートはその下にぶら下がります。`fsid=0` を作らない場合、各エクスポートを **個別に** マウントすることになります(本教材はこの方式)。

### `/etc/exports` の検証

書いたら必ず検証します。

```bash
# 構文チェック + 反映
sudo exportfs -ra

# 現在公開しているエクスポート一覧
sudo exportfs -v
# /srv/nfs/k8s/static
#                 192.168.56.0/24(sync,wdelay,hide,no_subtree_check,sec=sys,rw,secure,no_root_squash,no_all_squash,fsid=10)
# /srv/nfs/k8s/dynamic
#                 192.168.56.0/24(sync,wdelay,hide,no_subtree_check,sec=sys,rw,secure,no_root_squash,no_all_squash,fsid=20)
# /srv/nfs/k8s/backup
#                 192.168.56.10/32(sync,wdelay,hide,no_subtree_check,sec=sys,rw,secure,no_root_squash,no_all_squash,fsid=30)
#                 192.168.56.0/24(sync,wdelay,hide,no_subtree_check,sec=sys,ro,secure,no_root_squash,no_all_squash,fsid=30)
```

{: .tip }
> `exportfs -v` の出力には **デフォルト値も明示されて表示** されるので、自分が書いていないオプションが何になっているかを確認するのに便利です。

### ローカルからの動作確認

```bash
# ローカルで自分自身をマウントしてみる
sudo mkdir /mnt/test-nfs
sudo mount -t nfs -o nfsvers=4.1 localhost:/srv/nfs/k8s/static /mnt/test-nfs
ls /mnt/test-nfs

# 書き込みテスト
sudo touch /mnt/test-nfs/hello-from-localhost
ls -la /srv/nfs/k8s/static
# 同じファイルが見える

# クリーンアップ
sudo umount /mnt/test-nfs
sudo rmdir /mnt/test-nfs
```

---

## 2.6 /etc/nfs.conf チューニング

Ubuntu 22.04+ では NFS サーバの主要設定が `/etc/nfs.conf` に集約されています。性能とセキュリティに関わる重要パラメータを見ていきます。

### 主要セクション

```ini
# /etc/nfs.conf

[general]
# デバッグ用、通常変更不要

[exportfs]
# debug=

[gssd]
# Kerberos まわり、後述

[lockd]
port=0
udp-port=0

[mountd]
manage-gids=y
# port=0
# threads=1

[nfsd]
threads=8
# host=
# port=0
# grace-time=90
# lease-time=90
# tcp=y
# udp=n
# vers2=n
# vers3=y
# vers4=y
# vers4.0=y
# vers4.1=y
# vers4.2=y

[statd]
# port=0
# outgoing-port=0

[sm-notify]
# retry-time=15
```

### 重要パラメータ

#### `[nfsd] threads`

NFS リクエストを処理するカーネルスレッド数。デフォルトは **8** ですが、実運用では **CPU コア数 × 4〜8 程度** が目安です。クライアント数 × 並列度を考慮します。

```bash
# 変更例
sudo sed -i 's/^# threads=.*/threads=32/' /etc/nfs.conf
# またはキー発見してから書き換え

# 反映
sudo systemctl restart nfs-server

# 現在のスレッド数確認
ps -ef | grep nfsd | grep -v grep | wc -l
# 32
```

スレッド数が足りないと、`nfsstat -s` で `th 0 0 0 0 0 ...` の各レンジに数値が偏って出ます。

#### `[nfsd] vers3 / vers4 / vers4.x`

各バージョンを個別に有効/無効化できます。NFSv3 を完全に切りたい場合:

```ini
[nfsd]
vers3=n
vers4=y
vers4.0=y
vers4.1=y
vers4.2=y
```

これで NFSv3 関連デーモン(mountd, lockd, statd)が起動しなくなり、ポートの占有もなくなります。

#### `[nfsd] tcp / udp`

NFSv4 は TCP のみなので、UDP を切ってよいです。

```ini
[nfsd]
tcp=y
udp=n
```

#### `[mountd] manage-gids`

クライアントが送ってくる UID から、サーバ側で **追加グループメンバシップ** を引き直すかどうか。POSIX の補助グループに依存するアプリ(古い C プロジェクトなど)で意味があります。デフォルト OFF、必要なら `y`。

```ini
[mountd]
manage-gids=y
```

#### `[lockd] port`、`[mountd] port`、`[statd] port`

NFSv3 用のポートを **固定** したいときに指定します。NFSv4 only ならゼロのままで OK。

### NFSv4-only モードの完全構成例

```ini
[nfsd]
threads=32
tcp=y
udp=n
vers3=n
vers4=y
vers4.0=y
vers4.1=y
vers4.2=y

[mountd]
manage-gids=y
```

これで `rpcinfo -p` の出力が大幅にシンプルになります。

```bash
sudo systemctl restart nfs-server
sudo rpcinfo -p localhost
#    program vers proto   port  service
#     100000    4   tcp    111  portmapper
#     100003    4   tcp   2049  nfs
```

きれい。

---

## 2.7 NFS サーバの起動と動作確認

### サービスの起動

```bash
# 自動起動の有効化
sudo systemctl enable nfs-server.service
sudo systemctl enable rpcbind.service

# 起動
sudo systemctl start nfs-server.service

# 状態確認
sudo systemctl status nfs-server.service
```

### 期待される出力

```
● nfs-server.service - NFS server and services
     Loaded: loaded (/lib/systemd/system/nfs-server.service; enabled; vendor preset: enabled)
     Active: active (exited) since Sat 2026-05-09 14:23:01 JST; 2min ago
   Main PID: 12345 (code=exited, status=0/SUCCESS)
        CPU: 60ms
```

### ポート開放確認

```bash
# 2049/tcp が LISTEN しているか
sudo ss -tlnp | grep 2049
# LISTEN 0      64                 *:2049             *:*    users:(("nfsd",pid=12346,fd=...))

# 全 NFS 関連ポート
sudo ss -tlnp | grep -E '(nfsd|rpc|mountd|statd|lockd)'

# 外から見えるか(別ノードから)
nc -zv 192.168.56.30 2049
# Connection to 192.168.56.30 2049 port [tcp/nfs] succeeded!
```

### showmount で公開状況を確認

```bash
# ローカルから
showmount -e localhost
# Export list for localhost:
# /srv/nfs/k8s/static  192.168.56.0/24
# /srv/nfs/k8s/dynamic 192.168.56.0/24
# /srv/nfs/k8s/backup  192.168.56.10/32,192.168.56.0/24

# クラスタワーカーから
ssh k8s-w1 showmount -e 192.168.56.30
# 同じ出力が見えるはず
```

`showmount` が **タイムアウト** したり **拒否** された場合、ネットワーク or ファイアウォール問題です(2.9 節を参照)。

### nfsstat で動作確認

```bash
# サーバ側統計
sudo nfsstat -s
# Server rpc stats:
# calls      badcalls   badclnt    badauth    xdrcall
# 0          0          0          0          0

# Server nfs v4:
# null             ...
# compound         ...
```

クライアントから接続が来ると数値が増えていきます。

### journalctl でログを追う

```bash
# nfs-server.service のログ
sudo journalctl -u nfs-server.service -f

# nfs-mountd.service のログ(NFSv3 互換あり時)
sudo journalctl -u nfs-mountd.service -f

# カーネル NFS 関連
sudo dmesg | grep -i nfs
```

---

## 2.8 ファイアウォール設定

Ubuntu 標準の **`ufw`** を使う前提で記述します(`firewalld` 派の方は読み替えてください)。

### NFSv4-only(本教材)の場合

```bash
# ufw を有効化(まだなら)
sudo ufw enable

# SSH 許可(切断されないように先に)
sudo ufw allow from 192.168.56.0/24 to any port 22 proto tcp

# NFSv4 用に 2049/tcp だけ許可
sudo ufw allow from 192.168.56.0/24 to any port 2049 proto tcp

# ルール確認
sudo ufw status numbered
# Status: active
#
#      To                         Action      From
#      --                         ------      ----
# [ 1] 22/tcp                     ALLOW IN    192.168.56.0/24
# [ 2] 2049/tcp                   ALLOW IN    192.168.56.0/24
```

### NFSv3 互換が必要な場合

```bash
# NFSv4 と NFSv3 共存。ポートはすべて固定する前提
# /etc/nfs.conf で以下のように固定したとする:
#   [lockd]    port=32767  udp-port=32767
#   [mountd]   port=20048
#   [statd]    port=32765  outgoing-port=32766

sudo ufw allow from 192.168.56.0/24 to any port 111 proto tcp     # rpcbind
sudo ufw allow from 192.168.56.0/24 to any port 111 proto udp
sudo ufw allow from 192.168.56.0/24 to any port 2049 proto tcp    # NFS
sudo ufw allow from 192.168.56.0/24 to any port 20048 proto tcp   # mountd
sudo ufw allow from 192.168.56.0/24 to any port 32765 proto tcp   # statd
sudo ufw allow from 192.168.56.0/24 to any port 32765 proto udp
sudo ufw allow from 192.168.56.0/24 to any port 32766 proto udp   # statd outgoing
sudo ufw allow from 192.168.56.0/24 to any port 32767 proto tcp   # lockd
sudo ufw allow from 192.168.56.0/24 to any port 32767 proto udp
```

### iptables で見ると

```bash
sudo iptables -L INPUT -n -v --line-numbers
# Chain INPUT (policy DROP)
# num   pkts bytes target     prot opt in     out     source               destination
# 1        0     0 ufw-...
```

ufw は内部で iptables/nftables ルールを生成しています。ルール変更後は **クライアントノードから接続テスト** を必ず行ってください。

```bash
# クライアントから(別ノードで)
nc -zv 192.168.56.30 2049
showmount -e 192.168.56.30
```

---

## 2.9 AppArmor との関係

Ubuntu の `nfs-kernel-server` パッケージは AppArmor プロファイルを **持ちません**(NFS サーバはカーネルモジュールで動作しているため、ユーザ空間プロファイルの対象外)。

ただし `rpcbind` などには AppArmor プロファイルがあるので、何か制約に引っかかる場合は:

```bash
# AppArmor 状態確認
sudo aa-status

# プロファイルの一覧と状態
sudo aa-status --profiled
sudo aa-status --enforced
sudo aa-status --complaining
```

問題が起きたら `journalctl` に `apparmor=DENIED` のメッセージが出ます。

---

## 2.10 ログとモニタリング

### `nfsstat` ─ NFS 統計の総合ツール

```bash
# サーバ側統計(全カウンタ)
sudo nfsstat -s

# クライアント側統計
sudo nfsstat -c

# v4 のみ
sudo nfsstat -4

# RPC 統計
sudo nfsstat -r

# 一定間隔で差分表示
sudo nfsstat -s -Z 5    # 5 秒ごとに変化分を出力
```

主な指標:

- `calls` ─ 受け取った RPC 数
- `badcalls` ─ 形式不正な RPC 数(増えたら異常)
- `compound` ─ NFSv4 の COMPOUND 数
- 各オペレーション(`read`, `write`, `getattr`...)の回数比率

### `nfsiostat` ─ クライアント I/O 統計

クライアント側で動かします(サーバ自身でも自分をマウントすれば見られる)。

```bash
sudo apt install -y nfs-common    # nfsiostat 含まれる

sudo nfsiostat 5    # 5 秒ごと
# Linux ...
#
# 192.168.56.30:/srv/nfs/k8s/static mounted on /mnt/test:
#
#  op/s     rpc bklog
#  3.45     0.00
# read:             ops/s     kB/s     kB/op   retrans   avg RTT (ms)   avg exe (ms)
#                   1.234     56.78    46.012  0 (0.0%)  2.345          3.456
# write:            ops/s     kB/s     kB/op   retrans   avg RTT (ms)   avg exe (ms)
#                   2.345     123.4    52.621  0 (0.0%)  4.567          6.789
```

各列の意味:

- `ops/s`: 秒あたり操作数
- `kB/s`: スループット
- `retrans`: 再送回数(増え続けたらネットワーク異常)
- `avg RTT`: NFS 層 RTT
- `avg exe`: アプリから見た実行時間(キャッシュヒット含む)

### Prometheus exporter

`prometheus-nfsd-exporter` または `node-exporter` の `--collector.mountstats` を使うと、NFS 統計を Prometheus に取り込めます。

```bash
# node-exporter を nfsd 統計付きで起動
node_exporter --collector.nfs --collector.mountstats
```

主要メトリクス:

- `node_nfsd_rpcs_total`
- `node_nfsd_disk_bytes_read_total`
- `node_nfsd_disk_bytes_written_total`
- `node_mountstats_nfs_operations_requests_total{operation="WRITE"}`

### ログのファシリティ

```bash
# デフォルトは syslog 経由
sudo journalctl -u nfs-server.service -n 200 --no-pager
sudo journalctl -u nfs-mountd.service -n 200 --no-pager
sudo journalctl -k -n 100    # カーネルメッセージ
```

カーネル NFS のデバッグ詳細は `/proc/sys/sunrpc/*` で制御できます。

```bash
# RPC デバッグ ON
echo 0xffff | sudo tee /proc/sys/sunrpc/rpc_debug
echo 0xffff | sudo tee /proc/sys/sunrpc/nfsd_debug

# トラブル後 戻す
echo 0 | sudo tee /proc/sys/sunrpc/rpc_debug
echo 0 | sudo tee /proc/sys/sunrpc/nfsd_debug
```

トラブルシュートのときだけ ON にします。常時 ON はログ膨張で死ねます。

---

## 2.11 サーバ構築ハンズオン: ゼロから動作確認まで

ここまでの内容を、**全部つなげた手順** として再構成します。`k8s-nfs`(192.168.56.30)で実行してください。

```bash
#!/bin/bash
# k8s-nfs サーバ構築スクリプト(対話的に実行することを推奨)
set -eux

# ===== Step 1: パッケージ =====
sudo apt update
sudo apt install -y nfs-kernel-server nfs-common lvm2 chrony ufw

# ===== Step 2: 時刻同期 =====
sudo systemctl enable --now chrony
chronyc tracking

# ===== Step 3: LVM 構築(/dev/sdb 前提) =====
# すでに作っているなら skip
if ! lvs | grep -q nfs_lv; then
  sudo pvcreate /dev/sdb
  sudo vgcreate nfs_vg /dev/sdb
  sudo lvcreate -n nfs_lv -l 100%FREE nfs_vg
  sudo mkfs.ext4 -L nfs_data /dev/nfs_vg/nfs_lv
fi

# ===== Step 4: マウント =====
sudo mkdir -p /srv/nfs
if ! mountpoint -q /srv/nfs; then
  echo "/dev/nfs_vg/nfs_lv  /srv/nfs  ext4  defaults,noatime  0  2" | sudo tee -a /etc/fstab
  sudo mount -a
fi

# ===== Step 5: ディレクトリ階層 =====
sudo mkdir -p /srv/nfs/k8s/{static,dynamic,backup}
sudo chown -R nobody:nogroup /srv/nfs/k8s
sudo chmod -R 0777 /srv/nfs/k8s

# ===== Step 6: /etc/exports =====
sudo tee /etc/exports <<'EOF'
/srv/nfs/k8s/static  192.168.56.0/24(rw,sync,no_subtree_check,no_root_squash,fsid=10)
/srv/nfs/k8s/dynamic 192.168.56.0/24(rw,sync,no_subtree_check,no_root_squash,fsid=20)
/srv/nfs/k8s/backup  192.168.56.0/24(ro,sync,no_subtree_check,fsid=30)
EOF

# ===== Step 7: nfs.conf チューニング(NFSv4-only + threads=32) =====
sudo cp /etc/nfs.conf /etc/nfs.conf.bak
sudo tee /etc/nfs.conf <<'EOF'
[nfsd]
threads=32
tcp=y
udp=n
vers3=n
vers4=y
vers4.0=y
vers4.1=y
vers4.2=y

[mountd]
manage-gids=y
EOF

# ===== Step 8: サービス起動 =====
sudo systemctl enable nfs-server
sudo systemctl restart nfs-server
sudo exportfs -ra

# ===== Step 9: ファイアウォール =====
sudo ufw --force enable
sudo ufw allow from 192.168.56.0/24 to any port 22 proto tcp
sudo ufw allow from 192.168.56.0/24 to any port 2049 proto tcp
sudo ufw status

# ===== Step 10: 動作確認 =====
echo "=== exports ==="
sudo exportfs -v
echo "=== rpcinfo ==="
sudo rpcinfo -p localhost | grep nfs
echo "=== showmount ==="
showmount -e localhost
echo "=== ports ==="
sudo ss -tlnp | grep 2049
echo "=== ローカルマウントテスト ==="
sudo mkdir -p /mnt/nfs-self-test
sudo mount -t nfs -o nfsvers=4.1 localhost:/srv/nfs/k8s/static /mnt/nfs-self-test
sudo touch /mnt/nfs-self-test/hello-from-self
ls -la /mnt/nfs-self-test
sudo umount /mnt/nfs-self-test
sudo rmdir /mnt/nfs-self-test
echo "=== ALL OK ==="
```

最後の "ALL OK" が出ればサーバ側完了です。

---

## 2.12 第 2 部のまとめ

ここまでで NFS サーバが動作する状態になりました。第 3 部ではクライアント側(全ワーカーノード)の準備、第 4 部で NFS-CSI ドライバインストールに進みます。

- ストレージは **LVM + ext4** 構成、`/srv/nfs/k8s/{static,dynamic,backup}` の階層
- `/etc/exports` は CIDR + `rw,sync,no_subtree_check,fsid=N` を基本フォーマットに
- `/etc/nfs.conf` で NFSv4 only、threads=32、TCP only に絞る
- ufw で 2049/tcp のみクラスタ内 CIDR に許可
- `exportfs -v`、`rpcinfo`、`showmount`、`ss`、`nfsstat`、`nfsiostat` がトラブルシュート定番ツール

→ 続いて第 3 部 NFS クライアント、第 4 部 NFS-CSI を構築していきます。

---

# 第 3 部: NFS クライアントの完全構築

NFS は **サーバとクライアントの両方を整える** ことで初めて動きます。Kubernetes 環境では NFS-CSI ドライバが Pod の中で mount コマンドを実行するため、**ホスト OS の NFS クライアント機能** が前提です。第 3 部ではクラスタの全ワーカーノード(`k8s-w1`〜`k8s-w3`)を NFS クライアントとして整備し、手動マウントで動作確認するところまで進めます。

## 3.1 必要パッケージのインストール

すべてのワーカーノードで以下を実行します。本教材では Ansible や `ssh ループ` でまとめて実行することも可能です。

```bash
# 全ワーカーで実行
for host in k8s-w1 k8s-w2 k8s-w3; do
  echo "===== $host ====="
  ssh $host "sudo apt update && sudo apt install -y nfs-common"
done
```

**`nfs-common` パッケージで入るもの**:

- `mount.nfs`、`mount.nfs4` ─ mount コマンドの NFS ヘルパー
- `rpc.statd`、`rpcbind` ─ NFSv3 のサポート(NFSv4 では不要だが入る)
- `nfsstat`、`nfsiostat` ─ 統計コマンド
- `showmount` ─ サーバのエクスポート一覧確認

### バージョン確認

```bash
ssh k8s-w1 "dpkg -l nfs-common | tail -1"
# ii  nfs-common  1:2.6.1-1ubuntu1.2

ssh k8s-w1 "modinfo nfs | head -5"
# filename:       /lib/modules/5.15.0-...-generic/kernel/fs/nfs/nfs.ko
# alias:          fs-nfs
# license:        GPL
# description:    The Linux network filesystem.
# author:         Trond Myklebust
```

### カーネルモジュールの確認

NFS クライアントは Linux カーネル本体のモジュールとして動作します。

```bash
# 現在ロードされているモジュール
ssh k8s-w1 "lsmod | grep -E '^(nfs|nfsv|sunrpc)'"
# 何も出ないこともある(初回マウント時に自動ロード)
```

最初の `mount -t nfs` 実行時に `nfs`、`nfsv4`、`sunrpc` モジュールが自動ロードされます。

---

## 3.2 ハンズオン: 手動マウント検証

まず **Kubernetes を介さず** に NFS が正常に動くことを確認します。これは「NFS が壊れているのか、CSI が壊れているのか」を切り分けるための基礎能力です。

### Step 1: サーバへの到達性確認

```bash
# k8s-w1 から NFS サーバへの疎通
ssh k8s-w1 << 'EOF'
ping -c 3 192.168.56.30
nc -zv 192.168.56.30 2049
EOF
```

**期待される出力**:

```
PING 192.168.56.30 (192.168.56.30) 56(84) bytes of data.
64 bytes from 192.168.56.30: icmp_seq=1 ttl=64 time=0.234 ms
...
Connection to 192.168.56.30 2049 port [tcp/nfs] succeeded!
```

`nc` で `Connection refused` や `timeout` が出る場合、第 2.8 節のファイアウォール設定を見直します。

### Step 2: エクスポート一覧の確認

```bash
ssh k8s-w1 "showmount -e 192.168.56.30"
```

**期待される出力**:

```
Export list for 192.168.56.30:
/srv/nfs/k8s/static  192.168.56.0/24
/srv/nfs/k8s/dynamic 192.168.56.0/24
/srv/nfs/k8s/backup  192.168.56.0/24
```

`clnt_create: RPC: Program not registered` が出る場合は、サーバ側で `rpcbind` が NFSv3 互換のために動いていない可能性があります。**NFSv4 only モードでは showmount は本来動作しません**(NFSv4 は mountd を使わないので)。代わりに次のように NFSv4 で直接マウントを試します。

```bash
# NFSv4 では pseudo filesystem ルートから直接マウントを試せる
ssh k8s-w1 << 'EOF'
sudo mkdir -p /tmp/test-mount
sudo mount -t nfs4 192.168.56.30:/ /tmp/test-mount
ls /tmp/test-mount
sudo umount /tmp/test-mount
EOF
```

### Step 3: 手動マウントテスト

```bash
ssh k8s-w1 << 'EOF'
# マウントポイント作成
sudo mkdir -p /mnt/nfs-test

# NFSv4.1 でマウント
sudo mount -t nfs -o nfsvers=4.1,hard,timeo=600 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-test

# 確認
mount | grep nfs-test
df -hT /mnt/nfs-test
EOF
```

**期待される出力**:

```
192.168.56.30:/srv/nfs/k8s/static on /mnt/nfs-test type nfs4 (rw,relatime,vers=4.1,rsize=1048576,wsize=1048576,...)

Filesystem                          Type  Size  Used Avail Use% Mounted on
192.168.56.30:/srv/nfs/k8s/static  nfs4   49G   24K   47G   1% /mnt/nfs-test
```

### Step 4: 書き込み・読み取り検証

```bash
ssh k8s-w1 << 'EOF'
# 書き込み
sudo bash -c 'echo "hello from k8s-w1 at $(date)" > /mnt/nfs-test/from-w1.txt'

# 内容確認
cat /mnt/nfs-test/from-w1.txt

# サーバ側で確認(別ターミナル)
EOF

ssh k8s-nfs "ls -la /srv/nfs/k8s/static/"
ssh k8s-nfs "cat /srv/nfs/k8s/static/from-w1.txt"
```

`from-w1.txt` がサーバ側で見えれば成功です。

### Step 5: 別ワーカーから同じファイルが見えるか(RWX 検証)

```bash
ssh k8s-w2 << 'EOF'
sudo mkdir -p /mnt/nfs-test
sudo mount -t nfs -o nfsvers=4.1,hard \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-test

ls -la /mnt/nfs-test
cat /mnt/nfs-test/from-w1.txt
# k8s-w1 が書いた内容が見えるはず

# k8s-w2 からも書く
sudo bash -c 'echo "hello from k8s-w2" > /mnt/nfs-test/from-w2.txt'
EOF

ssh k8s-w1 "ls /mnt/nfs-test/"
# from-w1.txt  from-w2.txt の両方が見える
```

**両ノードでファイルが共有されている** ことが確認できれば、これが「RWX(ReadWriteMany)」の正体です。

### Step 6: クリーンアップ

```bash
for host in k8s-w1 k8s-w2; do
  ssh $host << 'EOF'
sudo umount /mnt/nfs-test
sudo rmdir /mnt/nfs-test
EOF
done

ssh k8s-nfs "sudo rm /srv/nfs/k8s/static/from-*.txt"
```

---

## 3.3 mount オプション完全リファレンス

Kubernetes の NFS マウントは **CSI ドライバ経由**ですが、最終的に kubelet ホストの `mount.nfs` に渡されるオプションは、ここで紹介するものと完全に同じです。StorageClass や PV で `mountOptions:` に何を書くかを判断するために、各オプションを理解しておきます。

### プロトコル系

| オプション | 既定 | 意味 |
|-----------|------|------|
| `nfsvers=N` | 自動ネゴ | NFS バージョン指定。`4.1`、`4.2` 推奨 |
| `vers=N` | 同上 | `nfsvers` の別名 |
| `proto=tcp` | tcp | トランスポート(NFSv4 は tcp 必須) |
| `proto=udp` | ─ | UDP(NFSv3 のみ、本番では非推奨) |
| `port=N` | 2049 | サーバポート |

### 信頼性 / 障害耐性系

| オプション | 既定 | 意味 |
|-----------|------|------|
| `hard` | 既定 | サーバ応答なくても **永久にリトライ**(プロセスは I/O で固まる) |
| `soft` | ─ | 一定回数で諦めて I/O エラーを返す |
| `intr` / `nointr` | `nointr`(古い) | hard モードでも Ctrl-C で中断可(現代カーネルは廃止) |
| `timeo=N` | 600(=60 秒、NFSv4) | RPC タイムアウト(1/10 秒単位) |
| `retrans=N` | 2 | RPC 再送回数(soft 時) |

```mermaid
flowchart TB
    A[NFS サーバ無応答] --> B{mount オプション}
    B -- hard --> C[I/O 永久リトライ<br>Pod は CrashLoop しない]
    B -- soft --> D[一定時間後 EIO<br>Pod がアプリエラーで落ちる]
    C --> E[サーバ復旧で I/O 再開]
    D --> F[データ破損リスクあり]
```

{: .important }
> **`hard` を必ず使うこと**
>
> `soft` は一見「サーバが死んだら諦めてエラーにする」という賢明な挙動に見えますが、書き込み途中で EIO が返ると **データの一貫性が崩れます**。POSIX セマンティクスは「write が成功したら書けている」を前提にしているので、途中で諦められると上位アプリは状態不整合になります。**本番環境では `hard` 一択** です。

### 性能系

| オプション | 既定 | 意味 |
|-----------|------|------|
| `rsize=N` | 1048576(1 MiB) | 読み込みブロックサイズ |
| `wsize=N` | 1048576(1 MiB) | 書き込みブロックサイズ |
| `nconnect=N` | 1 | クライアントから張る TCP コネクション数(NFSv4.1+) |
| `noatime` | ─ | atime 更新抑制 |
| `nodiratime` | ─ | ディレクトリ atime 抑制 |
| `async` / `sync` | `async` | クライアント側のキャッシュフラッシュ戦略 |
| `bg` / `fg` | `fg` | マウント失敗時にバックグラウンドで再試行するか |

`nconnect` は **NFSv4.1+ で導入された強力な性能オプション** です。1 本の TCP コネクションだとシングルストリームでサーバとクライアント間の帯域を使い切れないことがありますが、`nconnect=4` のように複数本張ると並列化で性能が伸びます。

### キャッシュ系

| オプション | 既定 | 意味 |
|-----------|------|------|
| `ac` / `noac` | `ac` | 属性キャッシュ ON/OFF(`noac` は壊滅的に遅い) |
| `actimeo=N` | (個別設定) | 属性キャッシュの全項目を N 秒に |
| `acregmin=N` | 3 | 通常ファイル属性キャッシュ最小秒 |
| `acregmax=N` | 60 | 通常ファイル属性キャッシュ最大秒 |
| `acdirmin=N` | 30 | ディレクトリ属性キャッシュ最小秒 |
| `acdirmax=N` | 60 | ディレクトリ属性キャッシュ最大秒 |
| `lookupcache=all` | all | name→inode キャッシュ(all/none/pos/none) |

### ロック / セキュリティ系

| オプション | 既定 | 意味 |
|-----------|------|------|
| `lock` / `nolock` | `lock` | ファイルロック使用(`nolock` は単一クライアント前提) |
| `sec=sys` | sys | UID/GID ベース認証 |
| `sec=krb5` | ─ | Kerberos 認証 |
| `sec=krb5i` | ─ | Kerberos + 改ざん検出 |
| `sec=krb5p` | ─ | Kerberos + 暗号化 |

### 本教材で使うデフォルトオプションセット

PostgreSQL や Redis のような DB ワークロード向け:

```
nfsvers=4.1,hard,timeo=600,retrans=2,rsize=1048576,wsize=1048576,noatime,nconnect=4
```

ML データセットや共有アップロードなど大量小ファイル向け:

```
nfsvers=4.1,hard,timeo=600,rsize=1048576,wsize=1048576,noatime,actimeo=30,nconnect=4
```

---

## 3.4 ハンズオン: mount オプションの効果を比較する

ここから少し変わったハンズオンです。**同じ NFS マウントでもオプション次第でどう変わるか** を実測します。

### Step 1: NFSv3 と NFSv4.1 の比較

```bash
ssh k8s-w1 << 'EOF'
# NFSv3 でマウント(rpcbind 等が必要なのでサーバが NFSv4 only なら失敗する)
sudo mkdir -p /mnt/nfs-v3
sudo mount -t nfs -o nfsvers=3 192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-v3 \
  2>&1 | head -5

# NFSv4.1 でマウント
sudo mkdir -p /mnt/nfs-v41
sudo mount -t nfs -o nfsvers=4.1 192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-v41

# 確認
mount | grep nfs-v4
EOF
```

NFSv4 only サーバなので NFSv3 マウントは失敗するはずです。これでサーバの NFSv4 only 設定が効いていることが確認できました。

### Step 2: hard vs soft の挙動を観察

これは少し慎重に実施します。**サーバ側 NFS を意図的に止めてクライアント挙動を見る** 実験です。

```bash
# k8s-w1 で hard マウント
ssh k8s-w1 << 'EOF'
sudo mkdir -p /mnt/nfs-hard /mnt/nfs-soft
sudo mount -t nfs -o nfsvers=4.1,hard,timeo=50 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-hard

sudo mount -t nfs -o nfsvers=4.1,soft,timeo=50,retrans=2 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-soft

# テストファイル作成
sudo touch /mnt/nfs-hard/test-hard
sudo touch /mnt/nfs-soft/test-soft
EOF
```

別ターミナルで NFS サーバを止めます。

```bash
ssh k8s-nfs "sudo systemctl stop nfs-server"
```

クライアント側でアクセスを試みます。

```bash
# soft マウント側 ─ retrans=2 × timeo=50(5秒) = 約 10 秒で EIO
ssh k8s-w1 "time sudo ls /mnt/nfs-soft"
# 約 10 秒待ったあと:
# ls: cannot open directory '/mnt/nfs-soft': Stale file handle
# (または Input/output error)
# real    0m10.234s

# hard マウント側 ─ サーバ復旧まで永遠に待ち続ける
# これは Ctrl+C で中断できない(古いカーネルは intr が必要だった)
ssh k8s-w1 "timeout 20 sudo ls /mnt/nfs-hard"
# 20 秒経っても応答なし、timeout でプロセス強制終了
```

サーバを復旧:

```bash
ssh k8s-nfs "sudo systemctl start nfs-server"
sleep 5
ssh k8s-w1 "sudo ls /mnt/nfs-hard"
# test-hard と表示される ─ 復旧成功!
```

**結論**:

- `soft` は短時間でエラーを返すが、書き込み中のデータは消える
- `hard` は永久に待つが、サーバ復旧と同時にアプリは何事もなかったように継続できる
- **DB のような状態保持ワークロードでは `hard` 一択**

### Step 3: `nconnect` の性能効果を測る

```bash
ssh k8s-w1 << 'EOF'
sudo apt install -y fio

# nconnect=1(デフォルト)でベンチマーク
sudo mkdir -p /mnt/nfs-n1 /mnt/nfs-n4
sudo mount -t nfs -o nfsvers=4.1,hard,nconnect=1 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-n1

# 64K Sequential Read で 30 秒
sudo fio --name=seqread --rw=read --bs=64k --size=1G \
  --numjobs=4 --runtime=30 --time_based --direct=1 \
  --filename=/mnt/nfs-n1/fio-test --output-format=normal | grep -E '(bw|iops)'

sudo umount /mnt/nfs-n1
EOF

# nconnect=4 でマウントしなおして比較
ssh k8s-w1 << 'EOF'
sudo mount -t nfs -o nfsvers=4.1,hard,nconnect=4 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-n4

sudo fio --name=seqread --rw=read --bs=64k --size=1G \
  --numjobs=4 --runtime=30 --time_based --direct=1 \
  --filename=/mnt/nfs-n4/fio-test --output-format=normal | grep -E '(bw|iops)'

sudo umount /mnt/nfs-n4
EOF
```

1 GbE ネットワークなら、`nconnect=4` で **1.5〜3 倍** スループットが出ることが多いです。10 GbE ならさらに顕著です。

### Step 4: noatime の効果を測る

```bash
ssh k8s-w1 << 'EOF'
# atime 更新あり(デフォルト)
sudo mkdir -p /mnt/nfs-atime
sudo mount -t nfs -o nfsvers=4.1,hard \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-atime

# 大量小ファイルの読み込み
sudo mkdir -p /mnt/nfs-atime/many-files
for i in $(seq 1 1000); do
  sudo bash -c "echo $i > /mnt/nfs-atime/many-files/file-$i"
done

# 読み込みベンチ(atime 更新あり)
time sudo find /mnt/nfs-atime/many-files -type f -exec cat {} \; > /dev/null

sudo umount /mnt/nfs-atime

# noatime で同じことを
sudo mount -t nfs -o nfsvers=4.1,hard,noatime \
  192.168.56.30:/srv/nfs/k8s/static /mnt/nfs-atime

time sudo find /mnt/nfs-atime/many-files -type f -exec cat {} \; > /dev/null
EOF
```

`noatime` のほうが速いはず(小ファイルでアクセス時に inode 書き込みが省ける)。

---

## 3.5 /etc/fstab による永続マウント(参考)

Kubernetes 経由ではない、**ホストから直接** NFS をマウントしたい場合は `/etc/fstab` を使います。Kubernetes では基本的に必要ありませんが、知識として押さえておきます。

### 書き方

```bash
ssh k8s-w1 << 'EOF'
sudo mkdir -p /shared

sudo tee -a /etc/fstab <<FSTAB
192.168.56.30:/srv/nfs/k8s/static  /shared  nfs4  rw,hard,nfsvers=4.1,timeo=600,nconnect=4,noatime,_netdev,x-systemd.requires=network-online.target  0  0
FSTAB

# 検証
sudo mount -a

mount | grep shared
df -hT /shared
EOF
```

### 各フィールドの意味

| フィールド | 値 | 意味 |
|----------|----|------|
| device | `192.168.56.30:/srv/nfs/k8s/static` | サーバ:エクスポートパス |
| mountpoint | `/shared` | ローカルパス |
| type | `nfs4` | FS タイプ |
| options | `rw,hard,nfsvers=4.1,...` | mount オプション |
| dump | `0` | dump(1)対象外 |
| fsck pass | `0` | fsck 対象外 |

### 重要オプション

- `_netdev` ─ ネットワーク必要(なし → ネットワーク未起動で待たない → ブート失敗)
- `x-systemd.requires=network-online.target` ─ systemd によるネットワーク待機
- `noauto` + `x-systemd.automount` ─ アクセス時自動マウント(autofs 風)

### 注意

{: .warning }
> ホストの `/etc/fstab` に NFS を書くと、**Kubernetes 経由のマウントとは別系統** になります。kubelet が CSI に頼んで作るマウントは `/var/lib/kubelet/pods/.../volumes/kubernetes.io~csi/...` 以下に作られ、`/etc/fstab` とは無関係です。混乱しないように、本教材では **Kubernetes ワーカーノードでは /etc/fstab に NFS を書かない** ことを推奨します。

---

## 3.6 autofs(参考)

`autofs` はアクセス時に自動マウント・一定時間で自動アンマウントする仕組みです。多数の NFS エクスポートをユーザがアドホックに使う環境向け。Kubernetes では使いません。

```bash
sudo apt install -y autofs

# /etc/auto.master.d/nfs.autofs
echo "/mnt/auto /etc/auto.nfs --timeout=300" | sudo tee /etc/auto.master.d/nfs.autofs

# /etc/auto.nfs
sudo tee /etc/auto.nfs <<EOF
static -fstype=nfs4,hard,nfsvers=4.1 192.168.56.30:/srv/nfs/k8s/static
backup -fstype=nfs4,ro,hard,nfsvers=4.1 192.168.56.30:/srv/nfs/k8s/backup
EOF

sudo systemctl restart autofs

# ls /mnt/auto/static で初めてマウントされる
ls /mnt/auto/static
```

---

## 3.7 クライアントのモニタリング

### `nfsiostat`

```bash
ssh k8s-w1 "sudo nfsiostat 3"
# 3 秒ごとに統計を出す
```

主要列の見方:

- `op/s`: 毎秒オペレーション数
- `rpc bklog`: RPC バックログ(増え続けるとサーバ過負荷)
- `read/write avg RTT`: ネットワーク往復遅延
- `read/write avg exe`: アプリから見た実行時間

### `/proc/self/mountstats`

カーネルの mount 統計の生データ。`nfsiostat` の元データです。

```bash
ssh k8s-w1 "sudo cat /proc/self/mountstats | grep -A 20 nfs-test | head -30"
```

### Prometheus + Grafana

クラスタに Prometheus が動いていれば、`node-exporter` の `mountstats` コレクタで NFS 統計を自動収集できます。

```bash
# DaemonSet の args に追加
- --collector.mountstats
```

主要メトリクス:

- `node_mountstats_nfs_operations_requests_total{operation="WRITE"}`
- `node_mountstats_nfs_operations_response_time_seconds_total`
- `node_mountstats_nfs_total_read_bytes_total`

---

## 3.8 第 3 部のまとめ

第 3 部のハンズオンで、**Kubernetes を介さず NFS の動作** を理解しました。

- すべてのワーカーに `nfs-common` 必須
- マウントオプションの基礎セット: `nfsvers=4.1,hard,timeo=600,rsize=1048576,wsize=1048576,noatime,nconnect=4`
- `hard` と `soft` の挙動の違いを実機で確認
- `nconnect` で性能が顕著に伸びることを確認
- `/etc/fstab` は Kubernetes ワーカーでは使わない方針

次の第 4 部では、いよいよ NFS-CSI ドライバを Kubernetes クラスタにインストールします。

---

# 第 4 部: NFS-CSI ドライバ完全インストール

NFS-CSI ドライバは **Kubernetes と NFS を橋渡しする中核コンポーネント** です。PVC を作ると裏で NFS サーバ上にディレクトリを作成し、Pod のスケジュール先で NFS マウントを行います。第 4 部ではアーキテクチャを理解し、Helm と素の YAML の両方でインストール、各 Pod の役割を確認します。

## 4.1 NFS-CSI のアーキテクチャ

CSI 仕様は **Controller プラグイン** と **Node プラグイン** という 2 種類の役割を定義しています。

```mermaid
flowchart TB
    subgraph CP[Control Plane]
        api[kube-apiserver]
        ctrl[CSI Controller<br>Deployment<br>1 個<br>常駐サイドカー多数]
    end
    subgraph N1[k8s-w1]
        kub1[kubelet]
        node1[CSI Node<br>DaemonSet<br>1 Pod]
    end
    subgraph N2[k8s-w2]
        kub2[kubelet]
        node2[CSI Node<br>DaemonSet]
    end
    subgraph N3[k8s-w3]
        kub3[kubelet]
        node3[CSI Node<br>DaemonSet]
    end
    nfs[(NFS サーバ<br>192.168.56.30)]
    api -.PVC 監視.-> ctrl
    ctrl -.ディレクトリ作成.-> nfs
    kub1 -.Pod 起動.-> node1 -.マウント.-> nfs
    kub2 -.Pod 起動.-> node2 -.マウント.-> nfs
    kub3 -.Pod 起動.-> node3 -.マウント.-> nfs
```

### CSI Controller プラグイン(Deployment)

クラスタ全体で 1 個(または HA 構成で複数)動く Pod です。中身は **CSI ドライバ本体 + 複数の標準サイドカー** から構成されます。

| コンテナ | 役割 |
|----------|------|
| `nfs`(本体) | CSI gRPC を実装、`CreateVolume`/`DeleteVolume` を処理 |
| `csi-provisioner` | PVC を watch して `CreateVolume` を呼ぶ |
| `csi-snapshotter` | VolumeSnapshot を watch して `CreateSnapshot` を呼ぶ |
| `csi-resizer` | PVC のサイズ変更を watch して `ExpandVolume` を呼ぶ |
| `liveness-probe` | コンテナ生存確認 |

### CSI Node プラグイン(DaemonSet)

各ノードで 1 個ずつ動く Pod です。**Pod が起動するときの実マウント処理** を担当します。

| コンテナ | 役割 |
|----------|------|
| `nfs`(本体) | CSI gRPC を実装、`NodePublishVolume`/`NodeUnpublishVolume` を処理 |
| `node-driver-registrar` | kubelet に「この CSI ドライバが存在する」と登録 |
| `liveness-probe` | コンテナ生存確認 |

### Pod 起動時のフロー

```mermaid
sequenceDiagram
    participant U as kubectl apply
    participant A as kube-apiserver
    participant P as csi-provisioner
    participant Drv as NFS CSI Controller
    participant NFS as NFS Server
    participant K as kubelet
    participant N as NFS CSI Node
    U->>A: Pod + PVC 作成
    A->>P: PVC イベント
    P->>Drv: gRPC CreateVolume
    Drv->>NFS: mkdir /srv/nfs/k8s/dynamic/pvc-xxx
    NFS-->>Drv: OK
    Drv-->>P: VolumeID
    P->>A: PV を作成 → Bound
    A->>K: Pod を schedule
    K->>N: gRPC NodePublishVolume
    N->>N: mount.nfs ...
    N-->>K: OK
    K->>K: Pod 起動
```

このシーケンスを覚えておくと、トラブル時に「どこで止まっているか」を切り分けられます。

---

## 4.2 ハンズオン: Helm で NFS-CSI をインストール

本セクションは Kubernetes クラスタ(`kubectl` 設定済み)から実施します。`k8s-cp1` を踏み台にする想定です。

### Step 1: Helm CLI のインストール

```bash
ssh k8s-cp1 << 'EOF'
# Helm が無ければ
if ! command -v helm >/dev/null; then
  curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
  echo "deb [signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
  sudo apt update
  sudo apt install -y helm
fi
helm version
EOF
```

期待される出力:

```
version.BuildInfo{Version:"v3.15.0", GitCommit:"...", GitTreeState:"clean", GoVersion:"go1.22.x"}
```

### Step 2: Helm リポジトリの追加

```bash
helm repo add csi-driver-nfs https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/master/charts
helm repo update

# 利用可能なバージョン一覧
helm search repo csi-driver-nfs --versions | head -10
```

### Step 3: values ファイルの作成

学習・本番どちらでも `--set` で済むことが多いですが、設定が増えてきたら values ファイルにしておくと管理しやすいです。

```bash
cat > nfs-csi-values.yaml <<EOF
# CSI コントローラ
controller:
  replicas: 2                # HA 構成
  strategyType: Recreate     # PVC 操作中の競合回避
  resources:
    csiProvisioner:
      limits:
        memory: 200Mi
      requests:
        memory: 50Mi
    csiSnapshotter:
      limits:
        memory: 200Mi
      requests:
        memory: 50Mi
    csiResizer:
      limits:
        memory: 200Mi
      requests:
        memory: 50Mi
    nfs:
      limits:
        memory: 300Mi
      requests:
        memory: 50Mi

# Node プラグイン(DaemonSet)
node:
  resources:
    nodeDriverRegistrar:
      limits:
        memory: 100Mi
    nfs:
      limits:
        memory: 300Mi

# 機能ゲート
feature:
  enableFSGroupPolicy: true   # fsGroup を効かせる(File モード)

# externalSnapshotter サイドカーを有効化
externalSnapshotter:
  enabled: true
EOF
```

### Step 4: インストール実行

```bash
helm install csi-driver-nfs csi-driver-nfs/csi-driver-nfs \
  --namespace kube-system \
  --version v4.7.0 \
  -f nfs-csi-values.yaml
```

期待される出力:

```
NAME: csi-driver-nfs
LAST DEPLOYED: Wed May 13 ...
NAMESPACE: kube-system
STATUS: deployed
REVISION: 1
TEST SUITE: None
NOTES:
The CSI NFS Driver is getting deployed to your cluster.
...
```

### Step 5: インストールの確認

```bash
# Pod が全部 Running になるまで待つ
kubectl get pods -n kube-system -l app.kubernetes.io/instance=csi-driver-nfs -w

# 期待される出力(数十秒〜数分後):
# NAME                                  READY   STATUS    RESTARTS   AGE
# csi-nfs-controller-7d5b...-xxxxx     4/4     Running   0          1m
# csi-nfs-controller-7d5b...-yyyyy     4/4     Running   0          1m
# csi-nfs-node-aaaaa                    3/3     Running   0          1m
# csi-nfs-node-bbbbb                    3/3     Running   0          1m
# csi-nfs-node-ccccc                    3/3     Running   0          1m
```

Controller は 2 レプリカ、Node は各ワーカー上で 1 つずつ(DaemonSet)。Ctrl+C で `-w` を抜けます。

### Step 6: CSIDriver オブジェクトの確認

```bash
kubectl get csidriver
# NAME             ATTACHREQUIRED   PODINFOONMOUNT   STORAGECAPACITY   ...
# nfs.csi.k8s.io   false            false            false             ...

kubectl describe csidriver nfs.csi.k8s.io
```

`ATTACHREQUIRED: false` がポイント。NFS は **アタッチ(VolumeAttachment 経由のブロックデバイス接続)が不要** なため、`AttachRequired: false` でスキップしています。これがブロックストレージとの大きな違いです。

### Step 7: 各サイドカーコンテナのログを見てみる

```bash
# Controller の本体ログ
kubectl logs -n kube-system -l app=csi-nfs-controller -c nfs --tail=20

# csi-provisioner のログ
kubectl logs -n kube-system -l app=csi-nfs-controller -c csi-provisioner --tail=20

# Node の本体ログ
kubectl logs -n kube-system -l app=csi-nfs-node -c nfs --tail=20

# node-driver-registrar のログ
kubectl logs -n kube-system -l app=csi-nfs-node -c node-driver-registrar --tail=20
```

トラブル時に **どのコンテナを見るか** を覚えておくのが第一歩です。

---

## 4.3 ハンズオン: 素の YAML でインストール(参考)

エアギャップ環境(インターネット未接続)や Helm が使えない環境では、YAML 直接適用も可能です。

```bash
# 完全なマニフェストを取得
CSI_VERSION=v4.7.0
curl -O https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/${CSI_VERSION}/deploy/install-driver.sh
chmod +x install-driver.sh

# 中身を見る
less install-driver.sh
# 各 YAML を順番に kubectl apply している様子がわかる

# 実行
./install-driver.sh v4.7.0 local
```

または個別の YAML を直接 apply:

```bash
BASE="https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/${CSI_VERSION}/deploy/${CSI_VERSION}"

kubectl apply -f ${BASE}/rbac-csi-nfs.yaml
kubectl apply -f ${BASE}/csi-nfs-driverinfo.yaml
kubectl apply -f ${BASE}/csi-nfs-controller.yaml
kubectl apply -f ${BASE}/csi-nfs-node.yaml
```

エアギャップでは、これらの YAML を **手元のレジストリ参照に書き換える** 必要があります。

```bash
# イメージ参照を抜き出す
grep image: csi-nfs-controller.yaml csi-nfs-node.yaml

# 出てくるイメージ:
# registry.k8s.io/sig-storage/csi-provisioner:v5.0.1
# registry.k8s.io/sig-storage/csi-snapshotter:v8.0.1
# registry.k8s.io/sig-storage/csi-resizer:v1.11.1
# registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.11.1
# registry.k8s.io/sig-storage/livenessprobe:v2.13.1
# registry.k8s.io/sig-storage/nfsplugin:v4.7.0

# 本教材の k8s-lb:5000 レジストリにミラーする想定
for img in csi-provisioner:v5.0.1 csi-snapshotter:v8.0.1 csi-resizer:v1.11.1 \
           csi-node-driver-registrar:v2.11.1 livenessprobe:v2.13.1 nfsplugin:v4.7.0; do
  docker pull registry.k8s.io/sig-storage/${img}
  docker tag  registry.k8s.io/sig-storage/${img} 192.168.56.10:5000/sig-storage/${img}
  docker push 192.168.56.10:5000/sig-storage/${img}
done

# YAML の image: をすべて sed で書き換え
sed -i 's|registry.k8s.io/sig-storage/|192.168.56.10:5000/sig-storage/|g' \
  csi-nfs-controller.yaml csi-nfs-node.yaml
```

---

## 4.4 ハンズオン: テスト用 StorageClass で動作確認

最終確認として、PVC が動的プロビジョニングで作られることを確認します。

### Step 1: 最小限の StorageClass

```yaml
# nfs-sc-test.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-test
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
mountOptions:
- nfsvers=4.1
- hard
- noatime
```

```bash
kubectl apply -f nfs-sc-test.yaml
kubectl get sc
# NAME       PROVISIONER       RECLAIMPOLICY   VOLUMEBINDINGMODE   ...
# nfs-test   nfs.csi.k8s.io    Delete          Immediate           ...
```

### Step 2: テスト用 PVC

```yaml
# nfs-pvc-test.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nfs-test-pvc
spec:
  accessModes: [ReadWriteMany]
  storageClassName: nfs-test
  resources:
    requests:
      storage: 1Gi
```

```bash
kubectl apply -f nfs-pvc-test.yaml

# 即座に Bound になるはず
kubectl get pvc nfs-test-pvc -w
# NAME           STATUS    VOLUME       CAPACITY   ACCESS MODES   STORAGECLASS
# nfs-test-pvc   Pending   ...                                    nfs-test
# nfs-test-pvc   Bound     pvc-xxxxx    1Gi        RWX            nfs-test
```

### Step 3: NFS サーバ側で実際に作られたディレクトリを見る

```bash
ssh k8s-nfs "ls /srv/nfs/k8s/dynamic/"
# pvc-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

NFS-CSI が PVC ごとにサブディレクトリを作っています。

### Step 4: Pod から PVC を使う

```yaml
# nfs-test-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: nfs-test-pod
spec:
  containers:
  - name: writer
    image: alpine:3.20
    command: ["sh", "-c", "while true; do echo $(date) >> /data/log.txt; sleep 5; done"]
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: nfs-test-pvc
```

```bash
kubectl apply -f nfs-test-pod.yaml
kubectl wait --for=condition=Ready pod/nfs-test-pod --timeout=60s
kubectl exec -it nfs-test-pod -- tail -f /data/log.txt &

# 一定時間待ったあと
ssh k8s-nfs "ls -la /srv/nfs/k8s/dynamic/pvc-*/"
ssh k8s-nfs "cat /srv/nfs/k8s/dynamic/pvc-*/log.txt | tail -5"
```

Pod 内で書いたファイルが NFS サーバ側で見えれば、CSI の全フローが正常です。

### Step 5: クリーンアップ

```bash
kubectl delete pod nfs-test-pod
kubectl delete pvc nfs-test-pvc

# reclaimPolicy: Delete なので PV も自動削除される
kubectl get pv
# pvc-xxxxxxxx が消えていることを確認

ssh k8s-nfs "ls /srv/nfs/k8s/dynamic/"
# サーバ側のディレクトリも消えている

kubectl delete sc nfs-test
```

---

## 4.5 アップグレード手順

NFS-CSI のアップグレードは Helm なら簡単です。

```bash
# 現状確認
helm list -n kube-system

# 利用可能な新バージョン確認
helm search repo csi-driver-nfs --versions | head -5

# アップグレード
helm repo update
helm upgrade csi-driver-nfs csi-driver-nfs/csi-driver-nfs \
  --namespace kube-system \
  --version v4.8.0 \
  -f nfs-csi-values.yaml

# 各 Pod が rolling update される
kubectl get pods -n kube-system -l app.kubernetes.io/instance=csi-driver-nfs -w

# 検証
kubectl exec -it -n kube-system csi-nfs-controller-xxx -c nfs -- /nfsplugin --version
```

### アップグレード前のチェックリスト

- [ ] リリースノートを読んで破壊的変更がないか確認
- [ ] PVC の利用状況スナップショット(`kubectl get pvc -A` を保存)
- [ ] 既存 PV の `volumeAttributes` が新バージョンと互換か確認
- [ ] Snapshot CRD のバージョン(v1 / v1beta1)整合

### ロールバック

```bash
helm rollback csi-driver-nfs 1 -n kube-system
```

---

## 4.6 アンインストール

```bash
# 注意: 既存 PVC を使う Pod が動いていると、PVC の Detach に失敗する
# 先に全 PVC を削除してから

helm uninstall csi-driver-nfs -n kube-system

# CRD は手動削除(任意)
kubectl delete crd volumesnapshots.snapshot.storage.k8s.io \
                   volumesnapshotcontents.snapshot.storage.k8s.io \
                   volumesnapshotclasses.snapshot.storage.k8s.io
```

---

## 4.7 第 4 部のまとめ

- Controller(Deployment)= プロビジョニング担当、Node(DaemonSet)= マウント担当
- 各サイドカー(provisioner / snapshotter / resizer / registrar)の役割を理解
- Helm でのインストールが標準。YAML 直適用は学習・エアギャップ向け
- インストール後の検証:CSIDriver の存在、テスト PVC が Bound、Pod から書き込み可
- アップグレード・ロールバック・アンインストールも Helm で完結

第 5 部からはこの CSI を使った具体的な PV / PVC 運用に入ります。

---

# 第 5 部: 静的 PV としての NFS

NFS は **静的 PV** との相性が非常に良いストレージです。「事前に NFS サーバ上にディレクトリを切っておく → それを PV として登録 → PVC で bind する」というシンプルなフローで、本番でもよく使われます。

## 5.1 静的 PV を使うべきケース

```mermaid
flowchart TB
    A[何を保存する?] --> B{ボリュームの<br>個数は?}
    B -- 数個固定 --> S[静的 PV ◎]
    B -- 多数・動的 --> D[動的プロビジョニング ◎]
    A --> C{既存データを<br>引き継ぐ?}
    C -- Yes --> S
    C -- No --> D2[どちらでも可]
    A --> E{PV ごとに<br>違う設定?}
    E -- Yes --> S
    E -- 統一 --> D3[動的プロビジョニング ◎]
```

| ユースケース | 静的 / 動的 | 理由 |
|------------|-------------|------|
| マイグレーション前データ引き継ぎ | 静的 | 既存ディレクトリを PV にする |
| 大規模 ML データセット(数十 TB) | 静的 | 1 個の巨大 PV を多 Pod で共有 |
| 多数の独立 PVC(マイクロサービス各 1 個) | 動的 | 自動生成が便利 |
| バックアップ集約先 | 静的 | 1 個の RWX PV を多数 Pod で共有 |
| 個別の権限・容量設定 | 静的 | PV ごとに別設定が可能 |

---

## 5.2 ハンズオン: 単一の静的 PV を作る

### Step 1: NFS サーバ側で対象ディレクトリを準備

```bash
ssh k8s-nfs << 'EOF'
sudo mkdir -p /srv/nfs/k8s/static/manual-pv-01
sudo chown 999:999 /srv/nfs/k8s/static/manual-pv-01   # PostgreSQL 用に
sudo chmod 0750 /srv/nfs/k8s/static/manual-pv-01

ls -ld /srv/nfs/k8s/static/manual-pv-01
EOF
```

### Step 2: PV マニフェスト

```yaml
# manual-pv-01.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-manual-01
  labels:
    type: nfs-manual
    purpose: postgres
spec:
  capacity:
    storage: 5Gi
  accessModes:
  - ReadWriteOnce        # PostgreSQL なので RWO
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""   # 動的プロビジョニング対象外を明示
  mountOptions:
  - nfsvers=4.1
  - hard
  - timeo=600
  - noatime
  - nconnect=4
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-manual-01    # クラスタ内ユニーク
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/static/manual-pv-01
```

ポイント:

- `storageClassName: ""` ─ 動的プロビジョニング除外
- `csi.driver: nfs.csi.k8s.io` ─ NFS-CSI 経由でマウント
- `volumeHandle` ─ クラスタ全体でユニークな ID(他の PV と衝突しない名前)
- `share` ─ サーバ側の実パス

### Step 3: PVC マニフェスト

```yaml
# manual-pvc-01.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-manual-01
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources:
    requests:
      storage: 5Gi
  selector:
    matchLabels:
      type: nfs-manual
      purpose: postgres
```

`selector` で **どの PV を bind するか** を明示。これがないと「どの PV にもバインドできる」状態になり、意図しない PV を取られる可能性があります。

### Step 4: 適用と確認

```bash
kubectl create namespace todo

kubectl apply -f manual-pv-01.yaml
kubectl apply -f manual-pvc-01.yaml

# 状態確認
kubectl get pv,pvc -n todo
# NAME                            CAPACITY   ACCESS MODES   ...
# persistentvolume/pv-manual-01   5Gi        RWO            Retain    Bound    todo/pvc-manual-01

# NAME                                  STATUS   VOLUME         CAPACITY   ...
# persistentvolumeclaim/pvc-manual-01   Bound    pv-manual-01   5Gi
```

すぐに Bound になるはずです。Pending のまま動かないときは:

```bash
kubectl describe pvc -n todo pvc-manual-01
# Events に "no persistent volumes available for this claim" など出る
```

### Step 5: Pod から使う

```yaml
# postgres-static.yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres-static
  namespace: todo
spec:
  securityContext:
    fsGroup: 999
  containers:
  - name: postgres
    image: postgres:16
    env:
    - name: POSTGRES_PASSWORD
      value: changeme123
    - name: POSTGRES_DB
      value: todo
    - name: PGDATA
      value: /var/lib/postgresql/data/pgdata
    volumeMounts:
    - name: data
      mountPath: /var/lib/postgresql/data
    ports:
    - containerPort: 5432
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-manual-01
```

```bash
kubectl apply -f postgres-static.yaml
kubectl wait --for=condition=Ready pod/postgres-static -n todo --timeout=120s

# 接続して動作確認
kubectl exec -it -n todo postgres-static -- psql -U postgres -d todo \
  -c "CREATE TABLE t(id serial, val text); INSERT INTO t(val) VALUES('hello'); SELECT * FROM t;"

# サーバ側でファイルが書かれているか
ssh k8s-nfs "ls -la /srv/nfs/k8s/static/manual-pv-01/pgdata/"
# postgres のデータディレクトリ構造が見える
```

### Step 6: Pod を削除して再作成 → データが残っているか

```bash
kubectl delete pod -n todo postgres-static

# 再度作成
kubectl apply -f postgres-static.yaml
kubectl wait --for=condition=Ready pod/postgres-static -n todo --timeout=120s

# 前回のデータが残っているか
kubectl exec -it -n todo postgres-static -- psql -U postgres -d todo \
  -c "SELECT * FROM t;"
# id | val
# ---+-------
#  1 | hello
```

これが **「永続化」** の本質です。Pod は揮発しますが、PVC と PV が NFS サーバ上のデータを保持し続けます。

---

## 5.3 ハンズオン: 複数 PV を一括作成するスクリプト

学習環境や大量の PV を切る運用では、シェルスクリプトでまとめて作るのが楽です。

### スクリプト本体

```bash
#!/bin/bash
# create-static-pvs.sh
# 静的 PV を一括作成するスクリプト
set -eu

NFS_SERVER=192.168.56.30
NFS_BASE=/srv/nfs/k8s/static
COUNT=10
CAPACITY=5Gi
NAMESPACE=todo

# Step 1: NFS サーバ側でディレクトリを作る(SSH 実行)
echo "===== NFS サーバ側ディレクトリ作成 ====="
ssh ${NFS_SERVER} bash -s <<EOF
for i in \$(seq -w 01 ${COUNT}); do
  sudo mkdir -p ${NFS_BASE}/pool-\${i}
  sudo chown nobody:nogroup ${NFS_BASE}/pool-\${i}
  sudo chmod 0777 ${NFS_BASE}/pool-\${i}
done
ls -la ${NFS_BASE} | grep pool-
EOF

# Step 2: PV マニフェストを生成して apply
echo "===== PV マニフェスト生成 ====="
for i in $(seq -w 01 ${COUNT}); do
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-pool-${i}
  labels:
    pool: shared
    index: "${i}"
spec:
  capacity:
    storage: ${CAPACITY}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions:
  - nfsvers=4.1
  - hard
  - noatime
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-pool-${i}
    volumeAttributes:
      server: ${NFS_SERVER}
      share: ${NFS_BASE}/pool-${i}
EOF
done

echo "===== 結果 ====="
kubectl get pv | grep pv-pool-
```

### 実行

```bash
chmod +x create-static-pvs.sh
./create-static-pvs.sh

# 確認
kubectl get pv
# NAME          CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS      CLAIM
# pv-pool-01    5Gi        RWO            Retain           Available
# pv-pool-02    5Gi        RWO            Retain           Available
# ...
# pv-pool-10    5Gi        RWO            Retain           Available
```

10 個の PV が **Available**(まだ bind されていない)で並びます。

### PVC を作って好きな PV を取る

```yaml
# pvc-from-pool.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-need-storage
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources:
    requests:
      storage: 3Gi
  selector:
    matchLabels:
      pool: shared
```

```bash
kubectl apply -f pvc-from-pool.yaml
kubectl get pvc -n todo
# pvc-need-storage   Bound   pv-pool-01    5Gi    RWO
```

10 個の中から **空いている適合 PV** が自動で割り当てられます。

### PVC を削除しても PV は残る(Retain ポリシー)

```bash
kubectl delete pvc -n todo pvc-need-storage

# PV の状態を見る
kubectl get pv pv-pool-01
# STATUS: Released   (Available ではない)
```

`reclaimPolicy: Retain` なので、PV は **Released 状態** で残ります。再利用するには手動操作が必要です(第 5.5 節参照)。

---

## 5.4 ハンズオン: ラベル付き PV による細やかな制御

ストレージを **「速い SSD バックエンド」と「低速 HDD バックエンド」** に分けたいシナリオを想定します。

### NFS サーバ側に 2 系統の領域を作る

```bash
ssh k8s-nfs << 'EOF'
# 仮想的に分けるだけ(本物の HW 分離は別)
sudo mkdir -p /srv/nfs/k8s/static/fast-pool/{a,b,c}
sudo mkdir -p /srv/nfs/k8s/static/slow-pool/{a,b,c}
sudo chown -R nobody:nogroup /srv/nfs/k8s/static/{fast,slow}-pool
sudo chmod -R 0777 /srv/nfs/k8s/static/{fast,slow}-pool
EOF
```

### ラベル付き PV を作る

```yaml
# labeled-pvs.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-fast-a
  labels:
    tier: fast
    zone: a
spec:
  capacity: {storage: 10Gi}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions: [nfsvers=4.1, hard, noatime, nconnect=4]
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-fast-a
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/static/fast-pool/a
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-slow-a
  labels:
    tier: slow
    zone: a
spec:
  capacity: {storage: 50Gi}
  accessModes: [ReadWriteMany]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions: [nfsvers=4.1, hard, noatime]
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-slow-a
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/static/slow-pool/a
```

### PVC で適切な階層を取る

```yaml
# pvc-need-fast.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-postgres
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources:
    requests:
      storage: 5Gi
  selector:
    matchLabels:
      tier: fast       # ← 速い領域を要求
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-archive
  namespace: todo
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  resources:
    requests:
      storage: 30Gi
  selector:
    matchLabels:
      tier: slow       # ← 遅くて大容量
```

```bash
kubectl apply -f labeled-pvs.yaml
kubectl apply -f pvc-need-fast.yaml

kubectl get pvc -n todo
# pvc-postgres   Bound   pv-fast-a    10Gi    RWO     5m
# pvc-archive    Bound   pv-slow-a    50Gi    RWX     5m
```

---

## 5.5 ハンズオン: Released PV を再利用する

`reclaimPolicy: Retain` の PV を再利用したいケースを想定します。

### Released 状態の PV を作る

```bash
# 上の Step 6 と同じ流れ
kubectl delete pvc -n todo pvc-postgres
kubectl get pv pv-fast-a -o yaml | grep status -A 5
# status:
#   phase: Released
```

### 復旧手順

```bash
# 1. PV の claimRef をクリア
kubectl patch pv pv-fast-a -p '{"spec":{"claimRef":null}}'

# 2. 確認
kubectl get pv pv-fast-a
# STATUS: Available

# 3. 新しい PVC が bind できる
```

### スクリプト化

```bash
#!/bin/bash
# release-pv.sh - Released PV を Available に戻す
for pv in $(kubectl get pv --no-headers | awk '$5=="Released" {print $1}'); do
  echo "Releasing $pv"
  kubectl patch pv $pv -p '{"spec":{"claimRef":null}}'
done

kubectl get pv
```

{: .warning }
> **データを消すか残すかを意識する**
>
> `claimRef` をクリアしても **NFS サーバ上の実データは消えません**。前のテナントのデータが残ったまま新しい PVC が bind されます。本番では、再利用の前に必ず **データを退避 or 消去** してから claimRef をクリアします。

```bash
# データ消去の例
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/static/fast-pool/a/*"
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/static/fast-pool/a/.??*"
```

---

## 5.6 ハンズオン: 別 Namespace の PVC に bind されないようにする

`claimRef` を **事前に固定** すると、特定 Namespace の特定 PVC 名のみが bind できる PV になります。

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-prod-postgres
spec:
  capacity: {storage: 50Gi}
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  claimRef:
    namespace: production
    name: pvc-postgres-main
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-prod-postgres
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/static/prod-postgres
```

これで `production` Namespace の `pvc-postgres-main` 以外は bind できなくなります。**マルチテナント環境で本番データを守る** ためのテクニックです。

---

## 5.7 ハンズオン: RWX による複数 Pod 共有

NFS の真骨頂、RWX で複数 Pod 間ファイル共有を実演します。

### 共有用ディレクトリと PV

```bash
ssh k8s-nfs << 'EOF'
sudo mkdir -p /srv/nfs/k8s/static/shared-uploads
sudo chown 1000:1000 /srv/nfs/k8s/static/shared-uploads
sudo chmod 0775 /srv/nfs/k8s/static/shared-uploads
EOF
```

```yaml
# shared-uploads.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-shared-uploads
  labels:
    purpose: uploads
spec:
  capacity: {storage: 20Gi}
  accessModes: [ReadWriteMany]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions: [nfsvers=4.1, hard, noatime, nconnect=4]
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-shared-uploads
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/static/shared-uploads
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-shared-uploads
  namespace: todo
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  resources:
    requests:
      storage: 20Gi
  selector:
    matchLabels:
      purpose: uploads
```

### 3 つの Writer Pod を並列で動かす

```yaml
# writers.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shared-writers
  namespace: todo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: shared-writer
  template:
    metadata:
      labels:
        app: shared-writer
    spec:
      securityContext:
        fsGroup: 1000
      containers:
      - name: writer
        image: alpine:3.20
        command:
        - /bin/sh
        - -c
        - |
          while true; do
            echo "$(hostname) at $(date)" >> /shared/writes.log
            sleep 2
          done
        volumeMounts:
        - name: shared
          mountPath: /shared
      volumes:
      - name: shared
        persistentVolumeClaim:
          claimName: pvc-shared-uploads
```

```bash
kubectl apply -f shared-uploads.yaml
kubectl apply -f writers.yaml

kubectl wait --for=condition=Available deployment/shared-writers -n todo --timeout=120s
kubectl get pods -n todo -l app=shared-writer
# 3 つの Pod が Running

# 数秒待ってからログを見る
sleep 30
kubectl exec -it -n todo deploy/shared-writers -- tail -20 /shared/writes.log
# 異なる Pod 名(shared-writers-xxx)から書き込まれた行が混ざる
```

3 つの Pod が **異なるノード** に分散していることも確認しましょう。

```bash
kubectl get pods -n todo -l app=shared-writer -o wide
# NAME                                NODE
# shared-writers-xxx                  k8s-w1
# shared-writers-yyy                  k8s-w2
# shared-writers-zzz                  k8s-w3
```

3 つの異なるワーカーから同じファイルに同時書き込みできているのが、RWX の威力です。

### NFS サーバ側で確認

```bash
ssh k8s-nfs "wc -l /srv/nfs/k8s/static/shared-uploads/writes.log"
# 増え続ける
ssh k8s-nfs "sort /srv/nfs/k8s/static/shared-uploads/writes.log | uniq -c -w12 | sort -rn | head"
# どの Pod がどのくらい書いたかが集計される
```

---

## 5.8 第 5 部のまとめ

- 静的 PV は **「事前に切ったストレージを Kubernetes に登録する」** モデル
- 単一 PV、一括スクリプトでの多数 PV、ラベル + selector による階層、claimRef 固定、RWX 共有のパターンを実践
- `reclaimPolicy: Retain` が静的 PV のデフォルトの考え方
- Released PV は `claimRef` クリアで Available に戻せる(データ消去は別途)

第 6 部では **動的プロビジョニング** ─ PVC を作るだけで PV が自動生成されるパターンを掘り下げます。

---

# 第 6 部: 動的プロビジョニング(NFS-CSI StorageClass)

第 5 部の静的 PV は強力ですが、PVC を作るたびに手作業で PV と NFS ディレクトリを用意するのは煩雑です。動的プロビジョニングは **「PVC を作ったら裏で全部自動でやってくれる」** モデルで、本教材の `nfs` StorageClass のメイン使用パターンです。

## 6.1 StorageClass の全 parameters

NFS-CSI ドライバが理解するパラメータを一通り見ていきます。

### 完全な StorageClass 例

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: nfs.csi.k8s.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
mountOptions:
- nfsvers=4.1
- hard
- timeo=600
- retrans=2
- noatime
- nconnect=4
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: ${pvc.metadata.namespace}/${pvc.metadata.name}
  mountPermissions: "0770"
  csi.storage.k8s.io/provisioner-secret-name: ""
  csi.storage.k8s.io/provisioner-secret-namespace: ""
```

### 各パラメータの解説

| パラメータ | 意味 | 例 |
|----------|------|----|
| `server` | NFS サーバ IP/FQDN | `192.168.56.30` |
| `share` | エクスポートのルートパス | `/srv/nfs/k8s/dynamic` |
| `subDir` | PVC ごとに自動生成するサブディレクトリのテンプレート | `${pvc.metadata.namespace}/${pvc.metadata.name}` |
| `mountPermissions` | サブディレクトリ作成時の chmod 値 | `"0770"` |
| `csi.storage.k8s.io/provisioner-secret-*` | プロビジョナが使う Secret(高度なケース) | ─ |

### subDir のテンプレート変数完全リスト

`subDir` で使えるテンプレート変数:

| 変数 | 意味 | 例 |
|------|------|----|
| `${pvc.metadata.namespace}` | PVC の Namespace | `todo` |
| `${pvc.metadata.name}` | PVC 名 | `postgres-data` |
| `${pv.metadata.name}` | 自動生成される PV 名 | `pvc-xxxxxxxx-...` |

これらを組み合わせて、NFS サーバ上のディレクトリ構造を整理できます。

```yaml
# パターン 1: PV 名そのまま(NFS-CSI デフォルト)
subDir: "${pv.metadata.name}"
# → /srv/nfs/k8s/dynamic/pvc-xxxxxxxx-yyyy-zzzz/

# パターン 2: Namespace/PVC 名(可読性高い、本教材推奨)
subDir: "${pvc.metadata.namespace}/${pvc.metadata.name}"
# → /srv/nfs/k8s/dynamic/todo/postgres-data/

# パターン 3: Namespace + PVC + PV 名(完全ユニーク)
subDir: "${pvc.metadata.namespace}-${pvc.metadata.name}-${pv.metadata.name}"
# → /srv/nfs/k8s/dynamic/todo-postgres-data-pvc-xxxxx/
```

{: .important }
> **パターン 2 の落とし穴**
>
> 同じ Namespace で **同じ名前の PVC を削除して再作成** すると、テンプレートが指すパスが同じになります。`reclaimPolicy: Delete` でも前回のデータが残っていれば再利用されますが、`reclaimPolicy: Retain` で物理ディレクトリが残っている場合、新しい PVC が古いデータを掴むことがあります。これを許容するかは設計判断です。

---

## 6.2 ハンズオン: 動的プロビジョニング用 StorageClass を作る

### Step 1: デフォルトの SC を作成

```yaml
# nfs-default-sc.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: "${pvc.metadata.namespace}/${pvc.metadata.name}"
  mountPermissions: "0770"
mountOptions:
- nfsvers=4.1
- hard
- timeo=600
- retrans=2
- noatime
- nconnect=4
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
```

```bash
# 既存のデフォルト SC があれば外す
kubectl annotate sc --all storageclass.kubernetes.io/is-default-class- 2>/dev/null

kubectl apply -f nfs-default-sc.yaml

# 確認
kubectl get sc
# NAME            PROVISIONER      RECLAIMPOLICY   VOLUMEBINDINGMODE   ...
# nfs (default)   nfs.csi.k8s.io   Delete          Immediate           true   2s
```

`(default)` マークが付いていれば成功です。

### Step 2: 最小限の PVC で試す

```yaml
# pvc-dyn.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 2Gi
  # storageClassName を省略 → デフォルト SC が使われる
```

```bash
kubectl apply -f pvc-dyn.yaml
kubectl get pvc -n todo my-app-data
# my-app-data   Bound   pvc-xxxx    2Gi    RWO    nfs

kubectl get pv | grep todo
# pvc-xxxxx    2Gi   RWO   Delete   Bound    todo/my-app-data
```

### Step 3: サーバ側で何が作られたか見る

```bash
ssh k8s-nfs "ls -la /srv/nfs/k8s/dynamic/todo/"
# drwxrwx--- 2 root root 4096 ... my-app-data

# 中身は空
ssh k8s-nfs "ls -la /srv/nfs/k8s/dynamic/todo/my-app-data/"
# 空ディレクトリ
```

subDir テンプレート通り `todo/my-app-data` ができています。

### Step 4: Pod から書き込む

```yaml
# test-writer.yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-writer
  namespace: todo
spec:
  containers:
  - name: app
    image: alpine:3.20
    command: ["sh", "-c", "echo $(date) > /data/hello.txt; sleep 3600"]
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: my-app-data
```

```bash
kubectl apply -f test-writer.yaml
kubectl wait --for=condition=Ready pod/test-writer -n todo --timeout=60s

kubectl exec -n todo test-writer -- cat /data/hello.txt
ssh k8s-nfs "cat /srv/nfs/k8s/dynamic/todo/my-app-data/hello.txt"
# 両方で同じ内容が見える
```

### Step 5: 削除して reclaimPolicy: Delete を確認

```bash
kubectl delete pod test-writer -n todo
kubectl delete pvc my-app-data -n todo

# 自動で PV も消える
kubectl get pv | grep todo
# 何も出ない

# NFS サーバ側のディレクトリも消える
ssh k8s-nfs "ls /srv/nfs/k8s/dynamic/todo/ 2>/dev/null"
# 空(ディレクトリ自体は残る)
```

---

## 6.3 ハンズオン: 複数の StorageClass を使い分ける

実運用では **「DB 用」「アーカイブ用」「キャッシュ用」** など、用途に応じて複数の StorageClass を提供します。

### 高速・保護用(reclaimPolicy: Retain)

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-retain
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: retain/${pvc.metadata.namespace}/${pvc.metadata.name}
mountOptions: [nfsvers=4.1, hard, noatime, nconnect=4]
reclaimPolicy: Retain        # ← 重要
volumeBindingMode: Immediate
allowVolumeExpansion: true
```

PVC を間違って消してもデータは NFS サーバに残る。**本番 DB はこれ**。

### 使い捨て用(reclaimPolicy: Delete)

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-disposable
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: disposable/${pvc.metadata.namespace}/${pvc.metadata.name}
mountOptions: [nfsvers=4.1, hard, noatime]
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
```

CI/CD やテストデータ用。

### ハンズオン: 用途別に PVC を作る

```yaml
# pvc-prod.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-prod
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-retain
  resources: {requests: {storage: 10Gi}}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ci-build-cache
  namespace: todo
spec:
  accessModes: [ReadWriteMany]
  storageClassName: nfs-disposable
  resources: {requests: {storage: 5Gi}}
```

```bash
kubectl apply -f nfs-retain-sc.yaml
kubectl apply -f nfs-disposable-sc.yaml
kubectl apply -f pvc-prod.yaml

kubectl get pvc -n todo
ssh k8s-nfs "ls -R /srv/nfs/k8s/dynamic/{retain,disposable}/"
```

サーバ側で **用途別にディレクトリが分離** されているのが確認できます。

---

## 6.4 ハンズオン: mountOptions のチューニング

SC ごとに mount オプションを変えることで、用途に応じた性能特性を提供できます。

### DB ワークロード向け

```yaml
mountOptions:
- nfsvers=4.1
- hard
- timeo=600
- retrans=2
- noatime
- nconnect=4
- rsize=1048576
- wsize=1048576
```

特徴: 最大ブロックサイズ、多コネクション、`hard` で信頼性優先。

### 多数小ファイル向け(ML データ、共有設定)

```yaml
mountOptions:
- nfsvers=4.1
- hard
- timeo=600
- noatime
- actimeo=60          # 属性キャッシュを長め
- lookupcache=all
- nconnect=4
```

特徴: 属性キャッシュ長め、ルックアップキャッシュ ON。

### バックアップ書き込み向け

```yaml
mountOptions:
- nfsvers=4.1
- hard
- timeo=600
- noatime
- wsize=1048576
- nconnect=8           # スループット重視
```

特徴: 書き込みブロック最大、コネクション多数。

### 比較ハンズオン

3 つの SC を作り、同じ fio コマンドで性能を比較してみてください。

```bash
# 各 SC に対応する PVC を作って Pod を起動、fio 実行
for sc in db-tuned multi-small backup-throughput; do
  cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: bench-${sc}
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-${sc}
  resources: {requests: {storage: 5Gi}}
EOF
done
```

Pod 内から fio を実行して比較するスクリプト例は第 9 部で詳述します。

---

## 6.5 ハンズオン: PVC のリサイズ(動的拡張)

NFS-CSI は `allowVolumeExpansion: true` の SC で **オンライン拡張** に対応しています。

### Step 1: 最初は 1Gi で PVC を作る

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: resize-test
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs
  resources: {requests: {storage: 1Gi}}
```

```bash
kubectl apply -f resize-test.yaml
kubectl get pvc -n todo resize-test
# resize-test   Bound   pvc-xxx   1Gi
```

### Step 2: 5Gi に拡張

```bash
kubectl patch pvc -n todo resize-test \
  -p '{"spec":{"resources":{"requests":{"storage":"5Gi"}}}}'

# 即時反映
kubectl get pvc -n todo resize-test
# resize-test   Bound   pvc-xxx   5Gi   ...
```

NFS は **ブロックストレージと違ってファイルシステム拡張が不要** なので、Pod 再起動も不要です。これが NFS の良いところでもあります。

{: .note }
> **NFS の容量は本質的に「サーバ側ディスク容量」**
>
> PVC の容量を 5Gi にしても、NFS サーバが実際にそのサイズを保証してくれるわけではありません。NFS の export には quota が無いのがデフォルトです(`xfs_quota`、`projid` で個別実装可能)。「PVC が 5Gi」は **クォータではなく、 Kubernetes 側のメタデータ** です。実際の使用量が 5Gi を超えても Pod 側ではエラーは出ません(NFS サーバの全容量を使い切るまで)。

### Step 3: サーバ側に LVM 拡張

NFS サーバのデータ LV を後から拡張するハンズオン。

```bash
ssh k8s-nfs << 'EOF'
# 現状確認
sudo lvs
df -hT /srv/nfs

# /dev/sdb のサイズが大きくなったと仮定(VMware で disk 拡張)
# まず PV を拡張
sudo pvresize /dev/sdb

# VG の空きを確認
sudo vgs

# LV を空き分まで拡張
sudo lvextend -l +100%FREE /dev/nfs_vg/nfs_lv

# ファイルシステム拡張(ext4 はオンラインで可能)
sudo resize2fs /dev/nfs_vg/nfs_lv

# 確認
df -hT /srv/nfs
EOF
```

これで NFS サーバ側の容量が増えました。

---

## 6.6 第 6 部のまとめ

- 動的プロビジョニング = PVC を作るだけで PV と NFS サーバ上のディレクトリが自動生成
- `subDir` テンプレート変数で NFS 上のディレクトリ階層を整理
- 用途ごとに複数 SC を作って `reclaimPolicy`、`mountOptions` を使い分け
- PVC のオンライン拡張は NFS なら Pod 再起動不要
- NFS サーバ側の容量は LVM + ext4 で柔軟に拡張可能

ここから第 7 部はセキュリティ、第 8 部は権限問題の深堀りに入ります。

---

# 第 7 部: NFS のセキュリティ

NFS は「LAN 内の信頼できるホスト同士」を前提に設計されたプロトコルで、デフォルトのままだとセキュリティはかなり緩いです。Kubernetes クラスタで運用する場合、以下の観点を必ず検討します。

## 7.1 NFS の認証モード

NFS には `sec=` というオプションで指定する認証モードがあります。

```mermaid
flowchart LR
    A[NFS 認証モード] --> S1[sec=sys<br>UID/GID ベース]
    A --> S2[sec=krb5<br>Kerberos 認証]
    A --> S3[sec=krb5i<br>+ 改ざん検出]
    A --> S4[sec=krb5p<br>+ 通信暗号化]
    S1 -->|簡単・脆弱| Use1[学習・LAN 内]
    S2 -->|中| Use2[企業 LAN]
    S3 -->|高| Use3[セキュリティ要件]
    S4 -->|最高・低速| Use4[クラウド経由]
```

### sec=sys(デフォルト)

クライアントが送ってきた UID/GID をそのまま信用します。**「ネットワーク内のホストは信頼できる」** を前提にした設計です。

```
クライアント Pod (UID=999) → 192.168.56.30:2049 → サーバが UID=999 として書き込み
```

弱点:

- クライアントが UID を **詐称し放題**(root で動く悪意ある Pod は誰にでもなれる)
- ネットワーク傍受で平文がそのまま見える
- 中間者攻撃に弱い

本教材のような閉じた学習環境では十分ですが、本番では考慮が必要です。

### sec=krb5 / krb5i / krb5p

Kerberos を使った強い認証。`krb5p` は通信内容も暗号化します(性能は 30〜50% 低下することも)。

セットアップは複雑で、KDC(Key Distribution Center)、principal の発行、keytab の配布などが必要です。本書のスコープを超えますが、興味があるなら以下のキーワードで調べてみてください。

- `MIT Kerberos / Heimdal`
- `rpc.gssd` クライアントデーモン
- `rpc.svcgssd` サーバデーモン
- `/etc/krb5.conf`, `/etc/krb5.keytab`

クラウドサービスで提供される NFS(AWS EFS、Azure NetApp Files など)は、TLS や IAM ベース認証など独自の代替メカニズムを持っています。

---

## 7.2 root_squash の本気の挙動

root_squash は **NFS で最重要のセキュリティ機能** です。Kubernetes クラスタでどう機能するかをハンズオンで確認します。

### Step 1: サーバ側で root_squash 設定

```bash
ssh k8s-nfs << 'EOF'
# テスト用に新エクスポートを作る
sudo mkdir -p /srv/nfs/k8s/test-squash
sudo chmod 0777 /srv/nfs/k8s/test-squash

# /etc/exports に root_squash 版を追加
sudo tee -a /etc/exports <<EXPORTS

# root_squash テスト用
/srv/nfs/k8s/test-squash  192.168.56.0/24(rw,sync,no_subtree_check,root_squash,anonuid=65534,anongid=65534,fsid=99)
EXPORTS

sudo exportfs -ra
sudo exportfs -v | grep test-squash
EOF
```

### Step 2: root として動く Pod を作る

```yaml
# pod-as-root.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-test-squash
spec:
  capacity: {storage: 1Gi}
  accessModes: [ReadWriteMany]
  storageClassName: ""
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-test-squash
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/test-squash
  mountOptions: [nfsvers=4.1, hard]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-test-squash
  namespace: default
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  resources: {requests: {storage: 1Gi}}
  volumeName: pv-test-squash
---
apiVersion: v1
kind: Pod
metadata:
  name: pod-as-root
spec:
  securityContext:
    runAsUser: 0     # ← root として動く
  containers:
  - name: app
    image: alpine:3.20
    command: ["sleep", "infinity"]
    volumeMounts:
    - {name: data, mountPath: /data}
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-test-squash
```

```bash
kubectl apply -f pod-as-root.yaml
kubectl wait --for=condition=Ready pod/pod-as-root --timeout=60s
```

### Step 3: root で書き込んでみる

```bash
# Pod 内で root として動作確認
kubectl exec -it pod-as-root -- sh
# / # id
# uid=0(root) gid=0(root)
# / # touch /data/from-root
# / # ls -la /data/from-root
# -rw-r--r--    1 nobody   nobody           0 ... /data/from-root
# ★所有者が nobody:nobody になっている!
# / # exit
```

サーバ側で確認:

```bash
ssh k8s-nfs "ls -la /srv/nfs/k8s/test-squash"
# -rw-r--r-- 1 nobody nogroup 0 ... from-root
```

これが `root_squash` の効果です。Pod が **root として動作していても、NFS サーバ側では UID=65534 (nobody)** にマップされて書き込まれます。

### Step 4: no_root_squash と比べる

サーバ側の設定を一時的に変更:

```bash
ssh k8s-nfs << 'EOF'
sudo sed -i 's/root_squash,anonuid=65534,anongid=65534/no_root_squash/' /etc/exports
sudo exportfs -ra
EOF

# Pod の中で再度書き込み
kubectl exec -it pod-as-root -- touch /data/from-root-no-squash
kubectl exec -it pod-as-root -- ls -la /data/
# -rw-r--r--    1 root     root             0 ... from-root-no-squash
# 今度は root:root で書かれた
```

**`no_root_squash` の場合、Pod 内 root はサーバの root として完全な権限** を持ちます。これがあると `chown` でファイル所有者を変えられたり、setuid バイナリを置けたりするので、本来は厳しく制限すべきです。

### クリーンアップ

```bash
kubectl delete pod pod-as-root
kubectl delete pvc pvc-test-squash
kubectl delete pv pv-test-squash

ssh k8s-nfs << 'EOF'
sudo sed -i '/test-squash/d' /etc/exports
sudo exportfs -ra
sudo rm -rf /srv/nfs/k8s/test-squash
EOF
```

---

## 7.3 ハンズオン: NetworkPolicy で NFS への通信を絞る

Pod から NFS サーバへの 2049/TCP を、**特定の Namespace の Pod のみ** に制限します。

### 前提: CNI が NetworkPolicy 対応

本教材で使う **Calico** は NetworkPolicy 完全対応。Flannel デフォルト構成では対応していないので、Calico か Cilium を想定します。

```bash
# Calico の状態確認
kubectl get pods -n kube-system -l k8s-app=calico-node
```

### Step 1: デフォルトで NFS を全 Pod から使えるか確認

```bash
# alpine Pod から NFS サーバへ接続テスト
kubectl run net-test --rm -it --restart=Never --image=alpine:3.20 -- sh
# / # nc -zv 192.168.56.30 2049
# 192.168.56.30 (192.168.56.30:2049) open
# / # exit
```

接続可能。

### Step 2: 制限する NetworkPolicy を作成

```yaml
# nfs-allow-only-todo.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-egress
  namespace: default
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress: []        # ← すべての egress を拒否
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-nfs
  namespace: todo
spec:
  podSelector:
    matchLabels:
      nfs-access: "true"
  policyTypes: [Egress]
  egress:
  - to:
    - ipBlock:
        cidr: 192.168.56.30/32
    ports:
    - protocol: TCP
      port: 2049
  - to:                          # DNS は許可しないと面倒なので例外
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
    ports:
    - protocol: UDP
      port: 53
```

### Step 3: 適用と検証

```bash
kubectl apply -f nfs-allow-only-todo.yaml

# default Namespace では拒否
kubectl run net-test --rm -it --restart=Never --image=alpine:3.20 -- sh
# / # nc -zv 192.168.56.30 2049
# nc: 192.168.56.30 (192.168.56.30:2049): No route to host (タイムアウト)
# / # exit

# todo Namespace でラベル付きの Pod なら OK
kubectl run net-test --rm -it -n todo --restart=Never \
  --labels=nfs-access=true \
  --image=alpine:3.20 -- sh
# / # nc -zv 192.168.56.30 2049
# 192.168.56.30 (192.168.56.30:2049) open
```

これで **NFS サーバへの 2049/TCP は明示的に許可した Pod のみ** に絞れました。マルチテナント環境で重要なパターンです。

### クリーンアップ

```bash
kubectl delete networkpolicy --all -n default
kubectl delete networkpolicy --all -n todo
```

---

## 7.4 NFS データの暗号化

NFS 自体は通信を平文で流します(`sec=krb5p` を除く)。本気で暗号化が必要なら以下の選択肢があります。

### 通信暗号化

- **`sec=krb5p`** ─ NFS プロトコルレベル(セットアップ複雑)
- **VPN / IPsec** ─ ホスト間で透過的に暗号化
- **stunnel / spiped** ─ ポートフォワーディング型
- **AWS EFS in-transit encryption** ─ TLS over NFS(EFS マウントヘルパー経由)

### 保管時暗号化(at-rest)

- **LUKS で NFS バックエンドディスクを暗号化**(本教材で簡単に試せる)
- **ZFS の暗号化機能**
- **アプリレベル暗号化**(PostgreSQL の pgcrypto など)

### LUKS ハンズオン(参考)

```bash
ssh k8s-nfs << 'EOF'
# 新しいディスク /dev/sdc が追加されているとする
sudo apt install -y cryptsetup

# 暗号化セットアップ
sudo cryptsetup luksFormat /dev/sdc
# Are you sure? Type 'YES'
# パスフレーズを設定

# 開く
sudo cryptsetup open /dev/sdc nfs_encrypted

# 通常のブロックデバイスとして使える
sudo mkfs.ext4 /dev/mapper/nfs_encrypted
sudo mkdir -p /srv/nfs/k8s/encrypted
sudo mount /dev/mapper/nfs_encrypted /srv/nfs/k8s/encrypted

# 起動時自動マウントは /etc/crypttab + /etc/fstab で設定
# 注: パスフレーズを起動時に入れる仕組み(TPM、keyfile)が別途必要
EOF
```

---

## 7.5 Pod Security Admission との関係

Kubernetes 1.25+ では `PodSecurity` Admission Controller がデフォルトです。NFS と組み合わせると以下の注意点があります。

### 制約レベル別

| レベル | NFS 利用への影響 |
|--------|------------------|
| `privileged` | 制限なし(本教材の `kube-system` 等) |
| `baseline` | hostPath は不可、NFS PVC は OK |
| `restricted` | runAsNonRoot 必須、UID 一致が必要 |

### restricted Namespace で NFS を使う

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: secure-app
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: v1
kind: Pod
metadata:
  name: postgres-secure
  namespace: secure-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 999
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: postgres
    image: postgres:16
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: [ALL]
      readOnlyRootFilesystem: false   # PostgreSQL は /tmp に書く
    # ... 以下省略
```

NFS マウントが `fsGroup: 999` で動作するため、NFS サーバ側の対象ディレクトリも **999:999** にしておけば、`restricted` でも動かせます。

---

## 7.6 第 7 部のまとめ

- NFS のデフォルト `sec=sys` は LAN 内信頼前提。本格運用では Kerberos か VPN/IPsec
- **`root_squash` は本番のデフォルトであるべき**。Pod の root を nobody にマップ
- NetworkPolicy で 2049/TCP を限定 Namespace に絞れる
- 通信暗号化と保管時暗号化は別物。要件に応じて選ぶ
- Pod Security Admission(`restricted`)+ NFS は `runAsNonRoot` + `fsGroup` で実現可能

第 8 部で **「NFS で起こる権限問題」の徹底攻略** に進みます。

---

# 第 8 部: NFS と Pod の権限問題完全攻略

NFS を Kubernetes で運用すると、**100% 通る道** が「Pod がボリュームに書き込めません」というエラーです。原因は UID/GID の不一致、`fsGroup` の挙動、root_squash など複数の要因が絡みます。この章で完全に解決します。

## 8.1 UID/GID の流れを正確に理解する

```mermaid
flowchart LR
    subgraph Pod[Pod 内]
        c1[コンテナプロセス<br>UID=999 GID=999]
    end
    subgraph Host[ワーカーノード OS]
        k[kubelet]
        cri[containerd]
        m[NFS マウント<br>uid=999 として書き込み要求]
    end
    subgraph NFS[NFS サーバ]
        d[(/srv/nfs/k8s/dynamic/...<br>ファイル所有者?)]
        r{root_squash?}
    end
    c1 --> cri --> m --> r
    r -- yes & uid=0 --> d_anon[(nobody として書き込み)]
    r -- no or uid != 0 --> d_real[(uid=999 として書き込み)]
```

### 重要なポイント

1. **コンテナプロセスの UID = Pod 内での id**
2. **NFS マウントは uid=Pod UID として書き込みを発行**(`sec=sys` の場合)
3. NFS サーバ側で `root_squash` のとき、**UID=0 のみ** が nobody にマップされる
4. UID=999 などはそのまま通る

つまり、**「ファイルが書けない」の根本原因はほぼ常に、Pod UID と NFS サーバ側ディレクトリ所有者の不一致** です。

---

## 8.2 ハンズオン: 権限問題のシナリオを再現

### Step 1: UID 不一致のシナリオを作る

NFS サーバで「所有者 1000:1000、パーミッション 0700」のディレクトリを作ります。

```bash
ssh k8s-nfs << 'EOF'
sudo mkdir -p /srv/nfs/k8s/test-perm
sudo chown 1000:1000 /srv/nfs/k8s/test-perm
sudo chmod 0700 /srv/nfs/k8s/test-perm
ls -ld /srv/nfs/k8s/test-perm
# drwx------ 2 1000 1000 ... /srv/nfs/k8s/test-perm
EOF
```

### Step 2: 違う UID で動く Pod を起動

```yaml
# perm-test.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-test-perm
spec:
  capacity: {storage: 1Gi}
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-test-perm
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/test-perm
  mountOptions: [nfsvers=4.1, hard]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-test-perm
  namespace: default
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources: {requests: {storage: 1Gi}}
  volumeName: pv-test-perm
---
apiVersion: v1
kind: Pod
metadata:
  name: perm-test-as-999
spec:
  securityContext:
    runAsUser: 999      # ← サーバの所有者 1000 と違う
    runAsGroup: 999
  containers:
  - name: app
    image: alpine:3.20
    command: ["sleep", "infinity"]
    volumeMounts:
    - {name: data, mountPath: /data}
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-test-perm
```

```bash
kubectl apply -f perm-test.yaml
kubectl wait --for=condition=Ready pod/perm-test-as-999 --timeout=60s
```

### Step 3: 書き込みを試みる → 失敗

```bash
kubectl exec -it perm-test-as-999 -- sh -c "id && ls -ld /data && touch /data/hello"
# uid=999 gid=999
# drwx------    2 1000     1000          4096 ... /data
# touch: /data/hello: Permission denied
```

**`Permission denied`** が出ました。これが典型的な権限問題です。

### Step 4: 原因分析

```mermaid
flowchart TB
    A[touch /data/hello] --> B{NFS サーバ<br>所有者=1000:1000<br>パーミッション=700}
    B --> C{書き込み UID=999<br>所有者でも所属グループでもない}
    C --> D[other 権限を見る<br>--- → write 不可]
    D --> E[Permission denied]
```

書き込み UID 999 は、対象ディレクトリの:
- 所有者 1000 ではない → user 権限 `rwx` を使えない
- 所属グループ 1000 ではない → group 権限 `---` を使えない
- → other 権限 `---` が適用 → 書き込み不可

### Step 5: 解決策 1 - サーバ側を 999 に揃える

```bash
ssh k8s-nfs "sudo chown 999:999 /srv/nfs/k8s/test-perm"

# Pod 内で再試行
kubectl exec -it perm-test-as-999 -- touch /data/hello
kubectl exec -it perm-test-as-999 -- ls -la /data
# -rw-r--r--    1 999      999              0 ... hello
```

**最もシンプルな解決策**: NFS サーバ側を Pod の UID に合わせる。

### Step 6: 解決策 2 - fsGroup を使う

サーバ側を一旦リセット:

```bash
ssh k8s-nfs << 'EOF'
sudo rm -f /srv/nfs/k8s/test-perm/hello
sudo chown 1000:2000 /srv/nfs/k8s/test-perm
sudo chmod 0770 /srv/nfs/k8s/test-perm        # group も書ける
ls -ld /srv/nfs/k8s/test-perm
EOF
```

Pod を `fsGroup: 2000` で再作成:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: perm-test-with-fsgroup
spec:
  securityContext:
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 2000        # ← 補助グループとして 2000 を付与
  containers:
  - name: app
    image: alpine:3.20
    command: ["sleep", "infinity"]
    volumeMounts:
    - {name: data, mountPath: /data}
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-test-perm
```

```bash
kubectl delete pod perm-test-as-999
kubectl apply -f /dev/stdin <<< "$(cat above-yaml-here)"

# 確認
kubectl exec -it perm-test-with-fsgroup -- sh -c "id && touch /data/hello"
# uid=999(999) gid=999(999) groups=999(999),2000
# OK! 書ける
```

`fsGroup: 2000` を指定すると、コンテナのプロセスに **GID 2000 が補助グループ** として追加されます。サーバ側のディレクトリも group 2000、`chmod 0770` なので、group 権限で書き込めます。

### Step 7: クリーンアップ

```bash
kubectl delete pod perm-test-with-fsgroup
kubectl delete pvc pvc-test-perm
kubectl delete pv pv-test-perm
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/test-perm"
```

---

## 8.3 fsGroup の正確な動作

`fsGroup` を指定すると、Pod 起動時に kubelet が以下の処理を行います。

```mermaid
sequenceDiagram
    participant K as kubelet
    participant V as ボリューム(NFS マウント)
    participant P as Pod プロセス
    K->>V: マウント
    K->>V: chown : fsGroup(再帰的)
    K->>V: chmod g+rwx(再帰的)
    K->>P: 起動(supplementary groups = [fsGroup])
```

つまり:

1. **マウント直後にボリューム全体を `chown :<fsGroup>` で再帰的に書き換える**
2. **`chmod g+rwx` で group 書き込み権限を立てる**
3. Pod のプロセスに `fsGroup` を補助グループとして追加

これによって、**「コンテナ内 UID が何であろうと、fsGroup を持っていれば書ける」** ようになります。

### 落とし穴 1: 再帰 chown が遅い

大量のファイルがあると、毎回のマウントで `chown -R` するので遅くなります。

```bash
# 例: PostgreSQL の datadir 配下に数万ファイル
$ time chown -R 999:999 /var/lib/postgresql/data
real    0m45.123s        # 45 秒もかかる!
```

これが kubelet → Pod 起動の経路で発生すると、Pod の Ready までに 45 秒以上かかります。

### 解決: `fsGroupChangePolicy: OnRootMismatch`

```yaml
spec:
  securityContext:
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
```

これにより、kubelet は **トップレベルの所有者だけを確認** し、すでに `fsGroup` と一致していれば再帰 chown をスキップします。

```bash
# 1 回目のマウント → 再帰 chown 実行(遅い)
# 2 回目以降 → root が 999:999 だから skip(速い)
```

PostgreSQL StatefulSet の Pod を再起動するとき、これがあるとないとで大きく変わります。

### 落とし穴 2: NFS で fsGroup が効かないことがある

Kubernetes の `fsGroup` は **CSI ドライバの設定** によって動作モードが変わります。

- `FSGroupPolicy: File` ─ kubelet が再帰 chown を実行(NFS でも効く)
- `FSGroupPolicy: None` ─ chown しない(無効)
- `FSGroupPolicy: ReadWriteOnceWithFSType` ─ RWO の特定 FS のみ chown

NFS-CSI のデフォルトは `File` ですが、values で変更できます。

```bash
kubectl get csidriver nfs.csi.k8s.io -o jsonpath='{.spec.fsGroupPolicy}'
# File   (これが正常)
```

`None` になっている場合は Helm values で `feature.enableFSGroupPolicy: true` に設定し、再インストールが必要です(第 4.2 節参照)。

---

## 8.4 主要コンテナイメージの UID/GID 表

```mermaid
flowchart LR
    A[コンテナイメージ] --> B{USER 指示}
    B -- 指定あり --> C[非 root]
    B -- 指定なし --> D[root]
    C --> E[NFS との整合性<br>を考えて UID を合わせる]
    D --> F[runAsNonRoot で<br>強制的に非 root に]
```

| アプリ | 公式イメージ UID:GID | 備考 |
|--------|---------------------|------|
| PostgreSQL | 999:999 (`postgres`) | データディレクトリ所有者 |
| MySQL | 999:999 (`mysql`) | 同 |
| MariaDB | 999:999 (`mysql`) | 同 |
| Redis | 999:999 (`redis`) | 同 |
| MongoDB | 999:999 (`mongodb`) | 同 |
| Nginx (公式) | 101:101 (`nginx`) | 別 UID |
| Apache HTTPD | 1:1 (`daemon`) | 古典的 |
| Bitnami 系全般 | 1001:1001 | 統一規約 |
| Elastic 系 | 1000:1000 (`elasticsearch`) | |
| Grafana | 472:472 (`grafana`) | |
| Prometheus | 65534:65534 (`nobody`) | |

### ハンズオン: PostgreSQL のために NFS サーバ側を整える

```bash
ssh k8s-nfs << 'EOF'
sudo mkdir -p /srv/nfs/k8s/static/postgres-prod
sudo chown -R 999:999 /srv/nfs/k8s/static/postgres-prod
sudo chmod 0700 /srv/nfs/k8s/static/postgres-prod
ls -ld /srv/nfs/k8s/static/postgres-prod
EOF
```

これで PostgreSQL Pod を `runAsUser: 999` で動かせば権限問題は起きません。

### Bitnami イメージ用に整える

```bash
ssh k8s-nfs << 'EOF'
sudo mkdir -p /srv/nfs/k8s/static/bitnami-redis
sudo chown -R 1001:1001 /srv/nfs/k8s/static/bitnami-redis
sudo chmod 0750 /srv/nfs/k8s/static/bitnami-redis
EOF
```

---

## 8.5 ハンズオン: 「すべての Pod に対応する」万能セットアップ

組織内で「どんな UID の Pod が来てもとりあえず動かせる NFS 領域が欲しい」という運用要件があるとします。以下のセットアップで実現できます。

### Step 1: 共通グループの設定

```bash
ssh k8s-nfs << 'EOF'
# 共通 GID として 50000 を割り当て
sudo groupadd -g 50000 k8s-shared 2>/dev/null || true

# 領域作成、所有者は root、グループは k8s-shared
sudo mkdir -p /srv/nfs/k8s/dynamic-shared
sudo chown root:50000 /srv/nfs/k8s/dynamic-shared

# SGID と group rwx で「中に作るものは全部 group=50000」になる
sudo chmod 2770 /srv/nfs/k8s/dynamic-shared
ls -ld /srv/nfs/k8s/dynamic-shared
# drwxrws--- 2 root k8s-shared ... /srv/nfs/k8s/dynamic-shared
#       ^s ← SGID
EOF
```

**SGID(`2`)を立てる** のがポイント。これで配下に作られるファイル・ディレクトリのグループが自動的に親のグループ(`50000`)になります。

### Step 2: 専用 StorageClass を作る

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-shared
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic-shared
  subDir: "${pvc.metadata.namespace}/${pvc.metadata.name}"
  mountPermissions: "2770"     # SGID も付ける
mountOptions: [nfsvers=4.1, hard, noatime]
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
```

### Step 3: Pod 側で fsGroup: 50000 を指定

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: any-uid-app
spec:
  securityContext:
    runAsUser: 12345        # ← 任意の UID
    runAsGroup: 12345
    fsGroup: 50000          # ← 共通グループ
    fsGroupChangePolicy: OnRootMismatch
  containers:
  - name: app
    image: alpine:3.20
    command: ["sh", "-c", "id; touch /data/test; ls -la /data; sleep 3600"]
    volumeMounts:
    - {name: data, mountPath: /data}
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-shared-app
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-shared-app
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-shared
  resources: {requests: {storage: 1Gi}}
```

これで **UID が何であっても** GID 50000 を共有するので書き込みできます。

```bash
kubectl exec -it any-uid-app -- ls -la /data
# drwxrwsr-x    2 root     50000   ...
# -rw-r--r--    1 12345    50000   ... test
```

ちゃんと書けています。

---

## 8.6 トラブルシューティング: 権限問題チェックリスト

権限問題に当たったら、以下の順で確認します。

```mermaid
flowchart TB
    A[Permission denied] --> B[kubectl exec で id 確認]
    B --> C[NFS マウント所有者を確認<br>ls -ld /data]
    C --> D{UID 一致?}
    D -- No --> E[fsGroup 確認]
    E -- 設定なし --> F[fsGroup 追加]
    E -- あるが効いてない --> G[CSI Driver の<br>fsGroupPolicy 確認]
    D -- Yes --> H[ファイルパーミッション<br>確認 0700 など]
    H --> I[NFS サーバ側で<br>chmod 修正]
```

### 調査コマンド集

```bash
# 1. Pod の UID
kubectl exec -it $POD -- id
# uid=999(postgres) gid=999(postgres) groups=999(postgres)

# 2. マウント先のディレクトリ所有者・権限
kubectl exec -it $POD -- ls -la /data
# drwx------ 2 1000 1000 ...

# 3. CSI Driver の fsGroupPolicy
kubectl get csidriver nfs.csi.k8s.io -o yaml | grep fsGroupPolicy

# 4. Pod の securityContext
kubectl get pod $POD -o yaml | yq '.spec.securityContext'

# 5. NFS サーバ側の所有者
ssh k8s-nfs "sudo ls -la /srv/nfs/k8s/dynamic/<namespace>/<pvc>"
```

### 典型パターンと対処

| 症状 | 原因 | 対処 |
|------|------|------|
| `Permission denied` で Pod 起動失敗 | UID 不一致 | fsGroup を設定 or サーバ側 chown |
| `chown: Operation not permitted` | root_squash で root 権限なし | no_root_squash か、Pod を非 root に |
| マウントは成功するが書けない | fsGroup 未設定 | securityContext.fsGroup を追加 |
| 起動に数十秒かかる | fsGroupChangePolicy: Always で再帰 chown | OnRootMismatch に変更 |
| 別 Pod が書いたファイルが読めない | UID が違う & group 共有なし | 共通 GID 戦略 |
| `mkdir: cannot create directory` | 親ディレクトリの権限不足 | parent の chmod / fsGroup |

---

## 8.7 ハンズオン: PostgreSQL を NFS で本気で動かす

ここまでの内容を組み合わせ、PostgreSQL StatefulSet を NFS で安定動作させます。

### Step 1: NFS サーバ側を整える

```bash
ssh k8s-nfs << 'EOF'
# postgres 専用ディレクトリ
sudo mkdir -p /srv/nfs/k8s/static/postgres-prod
sudo chown -R 999:999 /srv/nfs/k8s/static/postgres-prod
sudo chmod 0700 /srv/nfs/k8s/static/postgres-prod

# /etc/exports に追加(NFSv4.1 で sync, fsid 設定)
sudo tee -a /etc/exports <<EXPORTS

# PostgreSQL 専用ストレージ
/srv/nfs/k8s/static/postgres-prod  192.168.56.0/24(rw,sync,no_subtree_check,root_squash,fsid=100)
EXPORTS

sudo exportfs -ra
EOF
```

### Step 2: PV と PVC

```yaml
# postgres-prod-storage.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-postgres-prod
  labels:
    purpose: postgres-prod
spec:
  capacity: {storage: 20Gi}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: pv-postgres-prod
    volumeAttributes:
      server: 192.168.56.30
      share: /srv/nfs/k8s/static/postgres-prod
  mountOptions:
  - nfsvers=4.1
  - hard
  - timeo=600
  - retrans=2
  - noatime
  - nconnect=4
  - sync                # PostgreSQL の WAL 整合性のため強制 sync
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-postgres-prod
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources: {requests: {storage: 20Gi}}
  selector:
    matchLabels:
      purpose: postgres-prod
```

### Step 3: PostgreSQL StatefulSet

```yaml
# postgres-prod-sts.yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-prod-secret
  namespace: todo
type: Opaque
stringData:
  password: changeme123
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-prod
  namespace: todo
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: postgres-prod
  ports:
  - port: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres-prod
  namespace: todo
spec:
  serviceName: postgres-prod
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: postgres-prod
  template:
    metadata:
      labels:
        app.kubernetes.io/name: postgres-prod
        app.kubernetes.io/part-of: todo
    spec:
      securityContext:
        runAsUser: 999
        runAsGroup: 999
        fsGroup: 999
        fsGroupChangePolicy: OnRootMismatch
      containers:
      - name: postgres
        image: postgres:16
        env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-prod-secret
              key: password
        - name: POSTGRES_DB
          value: todo
        - name: POSTGRES_USER
          value: todo
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
        readinessProbe:
          exec:
            command: [pg_isready, -U, todo]
          initialDelaySeconds: 5
          periodSeconds: 5
        livenessProbe:
          exec:
            command: [pg_isready, -U, todo]
          initialDelaySeconds: 60
          periodSeconds: 10
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 1
            memory: 1Gi
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: pvc-postgres-prod
```

### Step 4: 適用と動作確認

```bash
kubectl apply -f postgres-prod-storage.yaml
kubectl apply -f postgres-prod-sts.yaml

# Ready 待ち
kubectl wait --for=condition=Ready pod/postgres-prod-0 -n todo --timeout=180s

# 接続テスト
kubectl exec -it -n todo postgres-prod-0 -- psql -U todo -d todo -c "
CREATE TABLE tasks (id SERIAL, title TEXT, done BOOLEAN, created TIMESTAMPTZ DEFAULT NOW());
INSERT INTO tasks(title, done) VALUES('NFS で PostgreSQL', true), ('権限問題マスター', true);
SELECT * FROM tasks;
"
```

### Step 5: サーバ側で構造確認

```bash
ssh k8s-nfs "sudo ls -la /srv/nfs/k8s/static/postgres-prod/"
# drwx------ 19 999 999 4096 ... pgdata

ssh k8s-nfs "sudo ls /srv/nfs/k8s/static/postgres-prod/pgdata/ | head"
# PG_VERSION
# base
# global
# pg_commit_ts
# ...

ssh k8s-nfs "sudo cat /srv/nfs/k8s/static/postgres-prod/pgdata/PG_VERSION"
# 16
```

PostgreSQL のデータディレクトリ構造が、NFS サーバ側で **999:999、0700** という適切な権限で展開されています。

### Step 6: Pod 再起動でデータ永続化を確認

```bash
kubectl delete pod -n todo postgres-prod-0
kubectl wait --for=condition=Ready pod/postgres-prod-0 -n todo --timeout=120s

kubectl exec -it -n todo postgres-prod-0 -- psql -U todo -d todo -c "SELECT * FROM tasks;"
# データは残っている
```

完璧に動作します。

---

## 8.8 第 8 部のまとめ

- 権限問題の根本は **Pod UID と NFS サーバ側ディレクトリ所有者の不一致**
- 解決の三本柱: ① サーバ側で chown、② Pod に fsGroup を指定、③ 共通 GID + SGID
- `fsGroupChangePolicy: OnRootMismatch` で再帰 chown 遅延を避ける
- 主要イメージの UID:GID を覚える(postgres/mysql/redis=999、bitnami=1001)
- トラブルシュートは `kubectl exec id` → `ls -la` → fsGroup 確認 → CSI Policy 確認の順

第 9 部からは **パフォーマンス** の世界に踏み込みます。

---

# 第 9 部: NFS のパフォーマンスチューニング

NFS は「動かす」までは簡単ですが、「速くする」のは奥が深いです。本部では実測と理論の両面からチューニングを学びます。

## 9.1 NFS 性能の理論

NFS の性能は以下の要素の積で決まります。

```
スループット = min( NW帯域, サーバ FS スループット ) × 並列度
```

- **NW 帯域** ─ 1 GbE では理論値 125 MB/s、現実 100 MB/s 前後
- **サーバ FS スループット** ─ SSD なら 500 MB/s+、HDD なら 100 MB/s
- **並列度** ─ `nconnect`、`threads`(nfsd)、サーバ FS の並列性

### レイテンシ要素

```
ラウンドトリップ = ネットワーク RTT + サーバ処理時間 + ディスク I/O 時間
                ≈ 0.1ms (1GbE LAN) + 0.1ms + 1ms (SSD) ≈ 1.2ms 程度
```

DB の `fsync` 1 回が 1.2ms というのは、ローカル SSD の 0.05ms より **24 倍遅い** です。これが NFS が高頻度トランザクション DB に向かない最大の理由です。

### 性能改善の方針

```mermaid
flowchart TB
    A[NFS が遅い] --> B{ボトルネックは?}
    B --> C[NW 帯域]
    B --> D[NW レイテンシ]
    B --> E[サーバ I/O]
    B --> F[並列度不足]
    C --> C1[10GbE 導入]
    C --> C2[nconnect 増加]
    D --> D1[同一スイッチに置く]
    D --> D2[wsize/rsize 増加]
    E --> E1[SSD/NVMe]
    E --> E2[XFS/ZFS チューニング]
    F --> F1[nfsd threads 増加]
    F --> F2[nconnect 増加]
```

---

## 9.2 ハンズオン: ベースラインを測る

何も最適化していない状態の性能を測ります。`fio` を使います。

### Step 1: fio を準備

```bash
# k8s-w1 でテスト
ssh k8s-w1 "sudo apt install -y fio"

# テスト用 Pod を作る
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: bench-pvc
  namespace: default
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs
  resources: {requests: {storage: 5Gi}}
---
apiVersion: v1
kind: Pod
metadata:
  name: fio-bench
spec:
  nodeSelector:
    kubernetes.io/hostname: k8s-w1
  containers:
  - name: fio
    image: ljishen/fio
    command: ["sleep", "3600"]
    volumeMounts:
    - {name: data, mountPath: /data}
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: bench-pvc
EOF

kubectl wait --for=condition=Ready pod/fio-bench --timeout=60s
```

### Step 2: 各種ワークロードでベンチマーク

```bash
# 1. Sequential Write 1MB
kubectl exec fio-bench -- fio \
  --name=seqwrite --rw=write --bs=1M --size=2G \
  --numjobs=1 --runtime=30 --time_based \
  --direct=1 --filename=/data/fio-seqwrite \
  --output-format=normal 2>&1 | grep -E "(WRITE|bw=|IOPS=)"

# 2. Random Write 4K
kubectl exec fio-bench -- fio \
  --name=randwrite --rw=randwrite --bs=4k --size=1G \
  --numjobs=4 --runtime=30 --time_based \
  --direct=1 --filename=/data/fio-randwrite \
  --output-format=normal 2>&1 | grep -E "(WRITE|bw=|IOPS=)"

# 3. Random Read 4K
kubectl exec fio-bench -- fio \
  --name=randread --rw=randread --bs=4k --size=1G \
  --numjobs=4 --runtime=30 --time_based \
  --direct=1 --filename=/data/fio-randread \
  --output-format=normal 2>&1 | grep -E "(READ|bw=|IOPS=)"

# 4. Sequential Read 1MB
kubectl exec fio-bench -- fio \
  --name=seqread --rw=read --bs=1M --size=2G \
  --numjobs=1 --runtime=30 --time_based \
  --direct=1 --filename=/data/fio-seqread \
  --output-format=normal 2>&1 | grep -E "(READ|bw=|IOPS=)"

# クリーンアップ
kubectl exec fio-bench -- rm /data/fio-*
```

### 期待される結果(1GbE 環境)

```
Sequential Write 1M:  bw=~100MB/s, IOPS=~100
Random Write 4K:      bw=~5MB/s,   IOPS=~1200
Random Read 4K:       bw=~30MB/s,  IOPS=~7500
Sequential Read 1M:   bw=~110MB/s, IOPS=~110
```

数値はストレージバックエンドとネットワークに大きく依存します。**自分の環境でのベースラインを記録** しておくのが大事です。

---

## 9.3 ハンズオン: nconnect で性能を伸ばす

`nconnect=4` の効果を測定します。

### Step 1: 新しい StorageClass を作る

```yaml
# nfs-sc-n4.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-n4
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: "${pvc.metadata.namespace}/${pvc.metadata.name}"
mountOptions:
- nfsvers=4.1
- hard
- noatime
- nconnect=4         # ← 4 本コネクション
reclaimPolicy: Delete
volumeBindingMode: Immediate
```

### Step 2: 同じベンチを実行

```bash
kubectl apply -f nfs-sc-n4.yaml

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: bench-n4-pvc
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-n4
  resources: {requests: {storage: 5Gi}}
EOF

# fio Pod を nfs-n4 で起動して同じテスト
# (上の Step 2 を繰り返す)
```

### Step 3: 結果比較

| ワークロード | nconnect=1 | nconnect=4 | 改善率 |
|------------|-----------|-----------|--------|
| Seq Write 1M | 100 MB/s | 110 MB/s | 1.1x |
| Random Write 4K | 5 MB/s | 12 MB/s | 2.4x |
| Random Read 4K | 30 MB/s | 80 MB/s | 2.7x |
| Seq Read 1M | 110 MB/s | 115 MB/s | 1.0x |

**並列性の高いワークロード(ランダム I/O、複数 Pod)では nconnect が顕著に効きます**。シーケンシャル単一はネットワーク帯域がボトルネックなので変わりません。

---

## 9.4 ハンズオン: nfsd threads を増やす

サーバ側で同時に処理できるリクエスト数を増やします。

```bash
ssh k8s-nfs << 'EOF'
# 現状確認
ps -ef | grep nfsd | grep -v grep | wc -l
# 8(デフォルト)

# threads を 64 に
sudo sed -i 's/^threads=.*/threads=64/' /etc/nfs.conf
sudo grep threads /etc/nfs.conf

# 再起動
sudo systemctl restart nfs-server

# 確認
ps -ef | grep nfsd | grep -v grep | wc -l
# 64
EOF
```

### 適切な値の決め方

```
threads ≈ 同時 RPC リクエスト数の最大値
       = 平均同時接続クライアント数 × クライアントごとの並列度
```

たとえば 3 ワーカー × 10 Pod × `nconnect=4` × 同時 RPC 平均 2 = 240 程度。

経験則:

- 小規模(〜10 Pod): 16〜32
- 中規模(〜50 Pod): 32〜64
- 大規模(50+ Pod): 64〜128

`nfsstat -s -Z 5` で `Server packet stats: th 0 0 ...` を見て、後ろのほうの数値が大きいなら threads 不足です。

---

## 9.5 ハンズオン: rsize / wsize の影響

```bash
# 小さい rsize/wsize の SC
cat <<EOF | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-small-rsize
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: "small-rsize/${pvc.metadata.namespace}/${pvc.metadata.name}"
mountOptions:
- nfsvers=4.1
- hard
- rsize=32768       # 32KiB
- wsize=32768
reclaimPolicy: Delete
EOF
```

同じベンチを `rsize/wsize=32768` と `rsize/wsize=1048576` で比較すると、**大ブロックサイズ(1MB)が顕著に速い** ことが確認できます。

### NFSv4.1+ の最大値

最近のカーネルは **`rsize=wsize=1048576`(1 MiB)** が上限。それ以上指定しても自動的に 1 MiB に切り詰められます。

```bash
# 実際にネゴシエートされた値を確認
ssh k8s-w1 "mount | grep nfs"
# ...,rsize=1048576,wsize=1048576,...
```

---

## 9.6 サーバ側のファイルシステム最適化

### ext4 のチューニング

```bash
# noatime,nodiratime をマウントオプションに
sudo tune2fs -o journal_data_writeback /dev/nfs_vg/nfs_lv

# data=writeback で書き込み性能向上(クラッシュ時データ少し失う代わり)
```

### XFS への移行(参考)

大規模・並列書き込み中心なら XFS のほうが速い傾向があります。

```bash
# 既存 ext4 から XFS への移行(データバックアップが必要)
sudo umount /srv/nfs
sudo mkfs.xfs -f -L nfs_data /dev/nfs_vg/nfs_lv
sudo mount /dev/nfs_vg/nfs_lv /srv/nfs
# /etc/fstab も書き換え
```

### ZFS バックエンド

ZFS は **圧縮・スナップショット・チェックサム** が組み込みで強力です。

```bash
sudo apt install -y zfsutils-linux
sudo zpool create nfs_pool /dev/sdb
sudo zfs create -o compression=lz4 -o atime=off nfs_pool/k8s
sudo zfs set mountpoint=/srv/nfs nfs_pool/k8s
```

NFS で読み取り中心のワークロード(ML データセット等)なら、ZFS の透過的圧縮で **実効容量が 2〜5 倍** になることもあります。

---

## 9.7 ハンズオン: PostgreSQL の性能を測る

実アプリでの性能を見るために、`pgbench` を回します。

```bash
# 第 8 部で作った postgres-prod に対して
kubectl exec -it -n todo postgres-prod-0 -- bash -c "
  createdb -U todo bench
  pgbench -i -s 10 -U todo bench
"

# tpmC を測定
kubectl exec -it -n todo postgres-prod-0 -- pgbench \
  -c 8 -j 2 -T 60 -U todo bench
```

期待される出力:

```
scaling factor: 10
query mode: simple
number of clients: 8
number of threads: 2
duration: 60 s
number of transactions actually processed: 18234
latency average = 26.34 ms
tps = 303.83 (including connections establishing)
```

ローカル SSD なら **5000+ TPS** 出るところが、NFS 越しだと **300 程度**。これが NFS の上の DB 性能です。学習や軽い使い方なら十分ですが、本番 OLTP では別途検討すべきと納得できます。

---

## 9.8 ハンズオン: ネットワーク帯域の確認

iperf3 でクラスタ内の帯域を測ります。

```bash
# サーバ側
ssh k8s-nfs "sudo apt install -y iperf3"
ssh k8s-nfs "iperf3 -s &" &

# クライアント側で測定
ssh k8s-w1 "sudo apt install -y iperf3"
ssh k8s-w1 "iperf3 -c 192.168.56.30 -t 30"
```

期待される出力(1GbE):

```
[ ID] Interval           Transfer     Bitrate         Retr
[  5]   0.00-30.00  sec  3.30 GBytes   944 Mbits/sec    0
```

≒ 118 MB/s。これが理論上限なので、NFS スループットがこれを超えることはありません。

---

## 9.9 性能チューニングのチェックリスト

```mermaid
flowchart LR
    A[遅い] --> B[iperf で NW 確認]
    B --> C[fio でローカル FS 確認]
    C --> D[fio で NFS マウント確認]
    D --> E[nconnect で並列化]
    E --> F[nfsd threads 増加]
    F --> G[FS をチューニング]
    G --> H[アプリ側<br>fsync 削減<br>バッチ書き込み]
```

順番に対応していきます。

| 確認項目 | コマンド | 期待値 |
|---------|---------|--------|
| NW 帯域 | `iperf3 -c <nfs-ip>` | 1GbE: 940Mbps+ |
| サーバローカル FS | サーバで `fio --rw=write --bs=1M ...` | SSD: 300MB/s+ |
| NFS over NW | クライアントで `fio` | NW 帯域の 80%+ |
| nfsd 使用率 | `nfsstat -s -Z 5` の `th` | 後半が 0 |
| nconnect | `mount` 出力 | `nconnect=4` |

---

## 9.10 第 9 部のまとめ

- NFS 性能は `min(NW帯域, サーバFS) × 並列度` で大まかに決まる
- `nconnect=4` でランダム I/O 2〜3 倍、`nfsd threads=64` で並列処理が改善
- `rsize=wsize=1048576` は現代の標準上限
- サーバ側 FS は ext4 → XFS / ZFS で用途別チューニング可能
- PostgreSQL 越しの TPS は NFS で大幅に下がる(本番 OLTP は別途検討)
- 測定は `fio`、`iperf3`、`nfsstat`、`nfsiostat`、`pgbench` を駆使

第 10 部では **HA NFS** の構築アプローチを見ていきます。

---

# 第 10 部: HA NFS の構築アプローチ

NFS サーバ 1 台構成は学習・小規模では十分ですが、**SPOF(Single Point of Failure)** です。NFS サーバが落ちると、依存している全 Pod のストレージ I/O が停止します。本番では「**NFS の HA 化**」を必ず検討します。

このセクションでは、HA NFS の代表的アプローチを比較しつつ、実機構築可能な 2 つのパターン(keepalived + DRBD、Pacemaker + Corosync + DRBD)をハンズオンで動かします。

## 10.1 HA NFS の難しさ

```mermaid
flowchart TB
    A[HA NFS にしたい] --> B{何を冗長化?}
    B --> C[NFS サーバプロセス<br>= ノード冗長化]
    B --> D[NFS データ<br>= ストレージ冗長化]
    B --> E[クライアントの接続<br>= ネットワーク冗長化]
    C --> F[Pacemaker / keepalived]
    D --> G[DRBD / GlusterFS / Ceph]
    E --> H[VIP / DNS フェイルオーバ]
```

NFS の HA には **3 つの軸** があります。

| 軸 | 解決策の例 |
|----|-----------|
| プロセス冗長化 | keepalived(VIP のみ)、Pacemaker(NFS サービスごと) |
| データ冗長化 | DRBD(ブロック)、GlusterFS / CephFS(分散 FS) |
| ネットワーク冗長化 | 仮想 IP(VIP)、bonded NIC、DNS RR |

困難な点は **NFSv4 のステートフル性** との折り合いです。サーバが切り替わると、クライアントが持つロック・delegation・OPEN 状態が無効になります。`grace-time`(NFS サーバの猶予期間、デフォルト 90 秒)の間にクライアントが状態を再確立できれば回復しますが、その間 I/O は止まります。

実用上は **「数十秒〜数分の I/O 停止は許容、最後の数秒の書き込みも保護したい」** という要件を満たすのが目標になります。

## 10.2 構成パターンの比較

| パターン | データ | プロセス | フェイルオーバ時間 | 運用 | コスト |
|---------|--------|----------|-------------------|------|--------|
| **keepalived + 共有 SAN** | SAN(iSCSI 等) | VIP 切替のみ | 数秒 | 低 | SAN 別途 |
| **keepalived + DRBD** | DRBD 同期 | VIP 切替 + 手動マウント | 30〜60 秒 | 中 | 安価 |
| **Pacemaker + Corosync + DRBD** | DRBD 同期 | リソース自動切替 | 10〜30 秒 | 中〜高 | 安価 |
| **GlusterFS NFS-Ganesha** | Gluster 分散 | Ganesha プロセス群 | 5〜30 秒 | 高 | 中 |
| **CephFS NFS-Ganesha** | Ceph 分散 | Ganesha + Ceph | 5〜30 秒 | 高 | 中〜高 |
| **NetApp / EMC アプライアンス** | 製品の内部 | 製品の内部 | 数秒 | 低(運用は楽) | 高 |
| **AWS EFS / Azure NetApp Files** | クラウド側 | クラウド側 | ─(常時 HA) | 最低 | 従量課金 |

本セクションでは「**keepalived + DRBD**」と「**Pacemaker + Corosync + DRBD**」をハンズオンで構築します。

## 10.3 ハンズオン Step 1: HA 検証用 VM を 2 台追加

VMware で新規 VM を 2 台作成します。

| ホスト名 | IP | 役割 |
|---------|----|----|
| `nfs-ha1` | 192.168.56.40 | プライマリ |
| `nfs-ha2` | 192.168.56.41 | セカンダリ |
| VIP | 192.168.56.45 | 浮動 IP(クライアントが接続する先) |

スペック: 各 VM とも vCPU 2、RAM 2 GiB、OS ディスク 20 GiB、データディスク 20 GiB(`/dev/sdb`)を追加。

両 VM で第 2.2 節の OS 初期設定(時刻同期、ホスト名、`/etc/hosts`)を済ませておきます。

両ノードの `/etc/hosts` に以下を追加:

```bash
sudo tee -a /etc/hosts <<EOF
192.168.56.40 nfs-ha1
192.168.56.41 nfs-ha2
192.168.56.45 nfs-vip
EOF
```

## 10.4 ハンズオン Step 2: DRBD のセットアップ(両ノード共通)

**DRBD(Distributed Replicated Block Device)** は「ネットワークを使ったブロックレベルの RAID 1」とよく説明される技術です。2 台のノードの `/dev/sdb` を同期して、片方をプライマリとして使うことで、データが常に両方のディスクに書かれている状態になります。

```mermaid
flowchart LR
    subgraph Pri[Primary: nfs-ha1]
        App[NFS サーバ]
        DRBD1[/dev/drbd0/]
        Disk1[/dev/sdb]
        App --> DRBD1 --> Disk1
    end
    subgraph Sec[Secondary: nfs-ha2]
        DRBD2[/dev/drbd0]
        Disk2[/dev/sdb]
        DRBD2 --> Disk2
    end
    DRBD1 <==同期==> DRBD2
```

### パッケージインストール(両ノード)

```bash
sudo apt update
sudo apt install -y drbd-utils
```

### DRBD リソース定義(両ノードで同じ内容)

```bash
sudo tee /etc/drbd.d/nfs-data.res <<'EOF'
resource nfs-data {
    protocol C;                     # 同期レプリケーション
    device    /dev/drbd0;
    disk      /dev/sdb;
    meta-disk internal;

    net {
        verify-alg sha256;
        cram-hmac-alg sha256;
        shared-secret "drbd-secret-2026";
    }

    syncer {
        rate 100M;
    }

    on nfs-ha1 {
        address 192.168.56.40:7788;
    }
    on nfs-ha2 {
        address 192.168.56.41:7788;
    }
}
EOF
```

**Protocol C(同期)** は「両ノードの DRBD レイヤがディスクに書き込んで ACK したら、アプリ側に ACK を返す」モードで、HA NFS で **必須** です。Protocol A や B は性能優先で、データ整合性が落ちます。

### メタデータ作成と起動(両ノード)

```bash
# 両ノードで実行
sudo drbdadm create-md nfs-data
# v09 Magic number not found
# Writing meta data...
# New drbd meta data block successfully created.

sudo drbdadm up nfs-data

# 両ノードで状態確認
sudo drbdadm status
# nfs-data role:Secondary
#   disk:Inconsistent
#   nfs-ha2 connection:Connecting
#         peer-disk:DUnknown
```

最初は両側とも Secondary + Inconsistent です。

### 片方を Primary に昇格して同期開始(プライマリ側のみ)

```bash
# nfs-ha1 で
sudo drbdadm primary --force nfs-data

# 同期の進捗を見る
watch sudo drbdadm status
# nfs-data role:Primary
#   disk:UpToDate
#   nfs-ha2 role:Secondary
#         replication:SyncSource peer-disk:Inconsistent done:35.8%
```

100% になるまで待ちます。20GiB なら 1GbE で 3〜5 分くらい。

### ファイルシステム作成(プライマリ側のみ)

```bash
# nfs-ha1 で
sudo mkfs.ext4 -L nfs-ha-data /dev/drbd0
sudo mkdir -p /srv/nfs-ha
sudo mount /dev/drbd0 /srv/nfs-ha
sudo mkdir -p /srv/nfs-ha/k8s
sudo chown -R nobody:nogroup /srv/nfs-ha/k8s
sudo chmod -R 0777 /srv/nfs-ha/k8s

# テストファイルを書く
echo "Hello from $(hostname) at $(date)" | sudo tee /srv/nfs-ha/k8s/hello.txt
```

### 切替テスト(手動)

```bash
# nfs-ha1 で
sudo umount /srv/nfs-ha
sudo drbdadm secondary nfs-data

# nfs-ha2 で
sudo drbdadm primary nfs-data
sudo mkdir -p /srv/nfs-ha
sudo mount /dev/drbd0 /srv/nfs-ha
cat /srv/nfs-ha/k8s/hello.txt
# Hello from nfs-ha1 at ...     <- 同期されている!
```

これで「**データの冗長化**」ができました。次に NFS サーバプロセスと VIP を自動切替する仕組みを作ります。

## 10.5 ハンズオン Step 3: 簡易構成 ─ keepalived + 手動 NFS

最もシンプルな HA: **keepalived だけで VIP を切り替え、NFS とマウントは scripts で動かす** 構成です。完全自動化はしませんが、HA の本質を理解するハンズオンとして優秀です。

### keepalived インストール(両ノード)

```bash
sudo apt install -y keepalived nfs-kernel-server
```

### `/etc/keepalived/keepalived.conf`(nfs-ha1)

```bash
sudo tee /etc/keepalived/keepalived.conf <<'EOF'
vrrp_script chk_nfs {
    script "/usr/local/bin/check_nfs.sh"
    interval 5
    weight -20
}

vrrp_instance VI_NFS {
    state MASTER
    interface enp0s8                      # 環境に応じて
    virtual_router_id 51
    priority 110
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass nfs-ha-secret
    }
    virtual_ipaddress {
        192.168.56.45/24
    }
    track_script {
        chk_nfs
    }
    notify_master "/usr/local/bin/nfs-master.sh"
    notify_backup "/usr/local/bin/nfs-backup.sh"
    notify_fault  "/usr/local/bin/nfs-fault.sh"
}
EOF
```

### `/etc/keepalived/keepalived.conf`(nfs-ha2)

`nfs-ha1` と同じ内容ですが、`state BACKUP`、`priority 100` に変えます。

```bash
sudo sed -i \
  -e 's/state MASTER/state BACKUP/' \
  -e 's/priority 110/priority 100/' \
  /etc/keepalived/keepalived.conf
```

### 切替スクリプト群(両ノード)

```bash
# /usr/local/bin/nfs-master.sh
sudo tee /usr/local/bin/nfs-master.sh <<'EOF'
#!/bin/bash
set -eu
logger -t keepalived-nfs "Promoting to MASTER"
/sbin/drbdadm primary nfs-data
mkdir -p /srv/nfs-ha
mount /dev/drbd0 /srv/nfs-ha
systemctl start nfs-server
EOF

# /usr/local/bin/nfs-backup.sh
sudo tee /usr/local/bin/nfs-backup.sh <<'EOF'
#!/bin/bash
set -eu
logger -t keepalived-nfs "Demoting to BACKUP"
systemctl stop nfs-server || true
umount /srv/nfs-ha 2>/dev/null || true
/sbin/drbdadm secondary nfs-data || true
EOF

# /usr/local/bin/nfs-fault.sh
sudo cp /usr/local/bin/nfs-backup.sh /usr/local/bin/nfs-fault.sh

# /usr/local/bin/check_nfs.sh
sudo tee /usr/local/bin/check_nfs.sh <<'EOF'
#!/bin/bash
systemctl is-active --quiet nfs-server || exit 1
mountpoint -q /srv/nfs-ha || exit 1
exit 0
EOF

sudo chmod +x /usr/local/bin/{nfs-master,nfs-backup,nfs-fault,check_nfs}.sh
```

### `/etc/exports`(両ノードで同じ)

```bash
sudo tee /etc/exports <<'EOF'
/srv/nfs-ha/k8s  192.168.56.0/24(rw,sync,no_subtree_check,no_root_squash,fsid=10)
EOF
```

### 起動

```bash
# 両ノードで
sudo systemctl disable --now nfs-server      # keepalived 経由で起動するため
sudo systemctl enable --now keepalived

# 状態確認
sudo systemctl status keepalived
ip addr show enp0s8 | grep 192.168.56.45
# nfs-ha1 で見えるはず
```

### 切替テスト

別ターミナルでクライアントから:

```bash
# クライアントで(k8s-w1 から)
sudo mount -t nfs 192.168.56.45:/srv/nfs-ha/k8s /mnt/test
ls /mnt/test
# hello.txt が見える

# 書き込み continuous
while true; do
  date >> /mnt/test/timeline.log
  sleep 1
done
```

別ターミナルから nfs-ha1 を強制停止:

```bash
# nfs-ha1 を強制再起動
ssh nfs-ha1 sudo reboot
```

クライアント側のタイムスタンプログを観察すると、**30 秒〜90 秒程度の I/O 停止後に再開** します。`tail timeline.log` で何秒のギャップがあるかが分かります。

```
2026-05-09 14:30:00 ...
2026-05-09 14:30:01 ...
        ← 切り替え中の停止
2026-05-09 14:30:45 ...
```

この停止時間が許容できれば、keepalived + DRBD HA で十分です。

## 10.6 ハンズオン Step 4: Pacemaker + Corosync で本格 HA

keepalived 構成は手動スクリプトに頼っており、scenrio の網羅性に乏しい欠点があります。本格的には **Pacemaker + Corosync** で「リソース」として NFS サーバを管理するのが正攻法です。

### パッケージ(両ノード)

```bash
# keepalived は止めておく
sudo systemctl disable --now keepalived

sudo apt install -y pacemaker corosync pcs fence-agents
```

### corosync 認証鍵(両ノード)

```bash
# nfs-ha1 で生成
sudo corosync-keygen
# 1024 bit の鍵が /etc/corosync/authkey に作られる

# nfs-ha2 にコピー
sudo scp /etc/corosync/authkey nfs-ha2:/etc/corosync/authkey
sudo ssh nfs-ha2 chown root:root /etc/corosync/authkey
sudo ssh nfs-ha2 chmod 0400 /etc/corosync/authkey
```

### corosync 設定(両ノード)

```bash
sudo tee /etc/corosync/corosync.conf <<'EOF'
totem {
    version: 2
    secauth: on
    cluster_name: nfs-ha
    transport: udpu
    interface {
        ringnumber: 0
        bindnetaddr: 192.168.56.0
        broadcast: no
        mcastport: 5405
    }
}

nodelist {
    node {
        ring0_addr: 192.168.56.40
        name: nfs-ha1
        nodeid: 1
    }
    node {
        ring0_addr: 192.168.56.41
        name: nfs-ha2
        nodeid: 2
    }
}

quorum {
    provider: corosync_votequorum
    two_node: 1
}

logging {
    to_logfile: yes
    logfile: /var/log/corosync/corosync.log
    to_syslog: yes
}
EOF
```

`two_node: 1` は 2 ノード構成専用のクォーラム設定です。

### サービス起動(両ノード)

```bash
sudo systemctl enable --now corosync pacemaker pcsd

# pcs クラスタ認証用ユーザ(hacluster)のパスワード
sudo passwd hacluster
# パスワードを設定
```

### クラスタの認証(片側で OK)

```bash
# nfs-ha1 から
sudo pcs host auth nfs-ha1 nfs-ha2 -u hacluster
# パスワードを入力

# 状態確認
sudo pcs status
# Cluster name: nfs-ha
# Stack: corosync
# Current DC: nfs-ha1 (version 2.x) - partition with quorum
# 2 nodes configured
# 0 resource instances configured
# ...
# Node List:
#   * Online: [ nfs-ha1 nfs-ha2 ]
```

### リソースの追加

5 つのリソースを作ります。実行順序を保証するために colocation と order 制約も入れます。

```bash
# 1. DRBD リソース
sudo pcs resource create drbd_nfs ocf:linbit:drbd \
  drbd_resource=nfs-data op monitor interval=20s

# 2. DRBD の master/slave 設定
sudo pcs resource promotable drbd_nfs \
  master-max=1 master-node-max=1 \
  clone-max=2 clone-node-max=1 notify=true

# 3. ファイルシステムリソース
sudo pcs resource create fs_nfs Filesystem \
  device=/dev/drbd0 directory=/srv/nfs-ha fstype=ext4 \
  op monitor interval=30s

# 4. VIP リソース
sudo pcs resource create vip_nfs IPaddr2 \
  ip=192.168.56.45 cidr_netmask=24 nic=enp0s8 \
  op monitor interval=10s

# 5. NFS サーバリソース
sudo pcs resource create nfsd nfsserver \
  nfs_shared_infodir=/srv/nfs-ha/nfsinfo \
  op monitor interval=30s

# colocation: すべて同じノードで動かす
sudo pcs constraint colocation add fs_nfs with drbd_nfs-clone INFINITY with-rsc-role=Master
sudo pcs constraint colocation add nfsd with fs_nfs INFINITY
sudo pcs constraint colocation add vip_nfs with nfsd INFINITY

# order: 起動順序
sudo pcs constraint order promote drbd_nfs-clone then start fs_nfs
sudo pcs constraint order fs_nfs then nfsd
sudo pcs constraint order nfsd then vip_nfs

# STONITH を無効化(学習目的、本番では fencing 必須)
sudo pcs property set stonith-enabled=false

# 動作確認
sudo pcs status
# ...
#   * drbd_nfs-clone   [ocf::linbit:drbd]
#     * Masters: [ nfs-ha1 ]
#     * Slaves:  [ nfs-ha2 ]
#   * fs_nfs     (ocf::heartbeat:Filesystem):    Started nfs-ha1
#   * nfsd       (ocf::heartbeat:nfsserver):     Started nfs-ha1
#   * vip_nfs    (ocf::heartbeat:IPaddr2):       Started nfs-ha1
```

### 切替テスト

```bash
# クライアントから NFS マウント(VIP 経由)
sudo mount -t nfs 192.168.56.45:/srv/nfs-ha/k8s /mnt/ha-test

# 書き込みループを起動
( while true; do date >> /mnt/ha-test/log.txt; sleep 0.5; done ) &

# nfs-ha1 を強制再起動
ssh nfs-ha1 sudo reboot

# 切替時間を tail で観察
tail -f /mnt/ha-test/log.txt
```

Pacemaker 構成なら **10〜30 秒程度** で nfs-ha2 へフェイルオーバします。

```bash
# nfs-ha2 で状態確認(nfs-ha1 復帰後)
sudo pcs status
# nfs-ha1 は Online で戻ってきている
# リソースは nfs-ha2 で稼働中
```

### 「戻し」(failback)

デフォルトでは nfs-ha1 が復帰しても自動では戻りません(余計な切替を避けるため)。手動で戻す場合:

```bash
# nfs-ha1 にすべて寄せる
sudo pcs resource move vip_nfs nfs-ha1

# 後で移動制約を消す(自動配置に戻す)
sudo pcs resource clear vip_nfs
```

## 10.7 GlusterFS NFS-Ganesha(概要)

DRBD はあくまで 2 ノードの同期です。**3 ノード以上の分散** で HA を取りたい場合は **GlusterFS + NFS-Ganesha** という選択肢があります。

```mermaid
flowchart LR
    Cli[NFS クライアント] -->|NFS| G1[gluster1<br>+ Ganesha]
    Cli -->|フェイルオーバ| G2[gluster2<br>+ Ganesha]
    Cli -->|フェイルオーバ| G3[gluster3<br>+ Ganesha]
    G1 <-.brick.-> G2
    G2 <-.brick.-> G3
    G1 <-.brick.-> G3
```

特徴:

- **3+ ノードでデータをレプリケート**
- **NFS-Ganesha** という user-space NFS サーバを経由(カーネル nfsd は不要)
- NFSv4 のみ(NFSv3 は別途設定が必要)
- 性能は DRBD より落ちるが、運用は楽

簡略な構築コマンド例(参考):

```bash
# 各ノードで
sudo apt install -y glusterfs-server nfs-ganesha-gluster

# ボリューム作成
sudo gluster volume create k8s replica 3 \
  gluster1:/data/brick1 \
  gluster2:/data/brick1 \
  gluster3:/data/brick1

sudo gluster volume start k8s

# Ganesha 経由で NFS export
# /etc/ganesha/ganesha.conf を編集
```

CSI ドライバは `gluster.org/glusterfs`(deprecated)と、NFS-Ganesha 経由の `nfs.csi.k8s.io` の両方の選択肢があります。

## 10.8 CephFS + NFS-Ganesha(概要)

Ceph は分散オブジェクト・ブロック・ファイルストレージの統合プラットフォームです。

```mermaid
flowchart TB
    subgraph Ceph[Ceph クラスタ]
        OSD1[OSD1]
        OSD2[OSD2]
        OSD3[OSD3]
        MDS1[MDS1]
        MDS2[MDS2]
    end
    G1[NFS-Ganesha 1] --> Ceph
    G2[NFS-Ganesha 2] --> Ceph
    G3[NFS-Ganesha 3] --> Ceph
    Cli[NFS Client] --> G1
    Cli --> G2
    Cli --> G3
```

- **MON / OSD / MDS** の各種デーモンが連携
- 最低 3 ノード推奨(本番は 5+ ノード)
- 自己修復・自動リバランス
- 学習目的なら **Rook**(Kubernetes Operator)で導入可能

学習コストが高いので、本教材では「NFS から始めて、要件が出たら Rook+Ceph に移行する」道筋を示すに留めます。

## 10.9 商用アプライアンスとクラウド NFS

| 製品 / サービス | 抽象 | 価格感 | 特徴 |
|---------------|------|-------|------|
| NetApp ONTAP | NFS / SMB / iSCSI | 高 | エンタープライズ標準、SnapMirror、SnapRestore |
| Dell PowerScale(旧 Isilon) | NFS / SMB | 高 | スケールアウト型、ML 用途で実績 |
| Synology / QNAP | NFS / SMB | 低 | SMB 用途、学習にも◎ |
| AWS EFS | NFS | 従量課金 | NFSv4.1、リージョナル冗長 |
| Azure NetApp Files | NFS / SMB | 高 | NetApp ONTAP のクラウド版 |
| Azure Files (NFS) | NFS v4.1 | 中 | プレミアム階層 |
| GCP Filestore | NFS v3 | 中 | エンタープライズ・ゾーナル |

「**自前で HA NFS を組むより、マネージドを買うほうが TCO は安い**」というのが本番運用での結論になることが多いです。学習目的では自前構築、本番では予算と SLO に応じて選びます。

## 10.10 HA NFS の選び方フローチャート

```mermaid
flowchart TB
    A[NFS が必要] --> B{ノード数?}
    B -- 2 --> C{予算は?}
    B -- 3+ --> D{運用工数は?}
    C -- 限定的 --> E[keepalived + DRBD]
    C -- 中 --> F[Pacemaker + DRBD]
    C -- 潤沢 --> G[商用アプライアンス]
    D -- 潤沢 --> H[GlusterFS / CephFS]
    D -- 限定的 --> I[商用 or マネージド]
    A --> J{クラウド?}
    J -- Yes --> K[EFS / Filestore / ANF]
    J -- No --> B
```

## 10.11 第 10 部のまとめ

- HA NFS は「プロセス」「データ」「ネットワーク」3 軸の冗長化
- 学習〜中規模: keepalived / Pacemaker + DRBD で十分
- スケール: GlusterFS / CephFS + NFS-Ganesha
- 本番大規模: 商用アプライアンス or マネージド NFS
- フェイルオーバ時間: keepalived 30〜90 秒、Pacemaker 10〜30 秒
- DRBD は Protocol C(同期)が必須

第 11 部では NFS の **スナップショットとバックアップ** に進みます。

---

# 第 11 部: スナップショット・バックアップ戦略

NFS サーバが HA 化されていても、**「データそのものが壊れる」** タイプの障害(誤削除、論理破損、ランサムウェア)からは守れません。スナップショットとバックアップは、これらに対する **時間軸の冗長化** です。

## 11.1 バックアップ戦略の全体像

```mermaid
flowchart TB
    A[NFS データ保護] --> B[スナップショット]
    A --> C[バックアップ]
    B --> B1[LVM スナップショット<br>同一ディスク・即時]
    B --> B2[ZFS スナップショット<br>差分のみ・効率的]
    B --> B3[CSI VolumeSnapshot<br>K8s 統合]
    C --> C1[rsync<br>シンプル・ファイル単位]
    C --> C2[Velero<br>Kubernetes 統合]
    C --> C3[restic / kopia<br>暗号化・重複排除]
```

| 手段 | 粒度 | 場所 | 速度 | 用途 |
|------|------|------|------|------|
| LVM スナップショット | ボリューム全体 | 同一ディスク | 即時 | バックアップ前の一貫性確保 |
| ZFS スナップショット | ボリューム全体 | 同一プール | 即時(差分のみ) | 短期保護 + send/recv |
| CSI VolumeSnapshot | PVC | 同一クラスタ | 即時 | K8s ネイティブ |
| rsync | ファイル単位 | 別マシン | 数分〜時間 | リモートバックアップ |
| Velero | Namespace / PV | S3 互換 | 数分 | クラスタ全体 DR |
| restic / kopia | ファイル + 重複排除 | S3 / SFTP | 高効率 | 長期保管 |

「**スナップショットだけ**」は、ディスクが壊れたら全部消えるので **バックアップではありません**。組み合わせて使うのが鉄則です。

## 11.2 ハンズオン: LVM スナップショット

第 2 部で構築した `nfs_vg/nfs_lv` を対象に、LVM スナップショットを取ってみます。

```bash
# k8s-nfs で
# 現在の VG 空き容量を確認
sudo vgs nfs_vg
#   VG     #PV #LV #SN Attr   VSize  VFree
#   nfs_vg   1   1   0 wz--n- 50.00g  0.00 ← VFree 0 だとスナップショットを取れない!
```

スナップショットは **元 LV と同じ VG に空き容量** が必要です。本教材の構成では `100%FREE` で LV を作ってしまっているので、まず縮小するか、空き容量がある状態で運用設計し直す必要があります。

### 設計のやり直し: LV を 80% に縮める or VG に空きディスクを追加

実用上は **VG に空き容量を残しておく** のが正解です。LV を作る時点で `-l 80%FREE` などにします。

```bash
# 既存環境で空きがない場合は新規ディスク追加で
sudo pvcreate /dev/sdc       # 新規 20 GiB ディスク
sudo vgextend nfs_vg /dev/sdc

sudo vgs nfs_vg
#   VG     #PV #LV #SN Attr   VSize  VFree
#   nfs_vg   2   1   0 wz--n- 70.00g 20.00g
```

### スナップショット作成

```bash
# 10 GiB のスナップショット
sudo lvcreate -L 10G -s -n nfs_lv_snap_2026_05_09 /dev/nfs_vg/nfs_lv
#   Logical volume "nfs_lv_snap_2026_05_09" created.

sudo lvs
#   LV                       VG     Attr       LSize  Pool Origin
#   nfs_lv                   nfs_vg owi-aos--- 50.00g
#   nfs_lv_snap_2026_05_09   nfs_vg swi-a-s--- 10.00g      nfs_lv      0.01
```

`-s` でスナップショット、`Origin` 欄に元 LV 名が出ます。10G は **「元 LV の変更分を最大何 GiB まで持つか」** で、これを超えるとスナップショットが「無効化」されます。

### スナップショットからの読み出し

```bash
# スナップショットをマウント(別の場所へ)
sudo mkdir -p /mnt/snap-2026-05-09
sudo mount /dev/nfs_vg/nfs_lv_snap_2026_05_09 /mnt/snap-2026-05-09

# 中身を見る
ls /mnt/snap-2026-05-09/k8s
# static  dynamic  backup

# 元の LV と区別がつかない見え方
ls /mnt/snap-2026-05-09/k8s/static
```

### バックアップとして tar で取り出す

```bash
cd /mnt/snap-2026-05-09
sudo tar czf /tmp/nfs-backup-2026-05-09.tar.gz k8s/

ls -lh /tmp/nfs-backup-2026-05-09.tar.gz
# -rw-r--r-- 1 root root  1.2G ...
```

### スナップショット削除

スナップショットは I/O オーバーヘッドを生むので、不要になったら **必ず削除** します。

```bash
sudo umount /mnt/snap-2026-05-09
sudo lvremove /dev/nfs_vg/nfs_lv_snap_2026_05_09
# Do you really want to remove active logical volume? [y/n]: y
#   Logical volume "nfs_lv_snap_2026_05_09" successfully removed.
```

### 自動スナップショット(cron)

```bash
sudo tee /etc/cron.d/nfs-lvm-snap <<'EOF'
# 毎日 2:00 にスナップショット → tar → 別ディスクへ
0 2 * * * root /usr/local/sbin/nfs-snap-backup.sh
EOF

sudo tee /usr/local/sbin/nfs-snap-backup.sh <<'EOF'
#!/bin/bash
set -eu

SNAP_NAME=nfs_lv_snap_$(date +%Y%m%d_%H%M)
SNAP_MOUNT=/mnt/$SNAP_NAME
BACKUP_DIR=/srv/nfs-backup
RETENTION=7

mkdir -p $SNAP_MOUNT $BACKUP_DIR

# スナップショット作成
lvcreate -L 10G -s -n $SNAP_NAME /dev/nfs_vg/nfs_lv

# マウント
mount /dev/nfs_vg/$SNAP_NAME $SNAP_MOUNT

# tar
tar czf $BACKUP_DIR/$(date +%Y%m%d_%H%M).tar.gz -C $SNAP_MOUNT k8s/

# アンマウント
umount $SNAP_MOUNT
rmdir $SNAP_MOUNT
lvremove -f /dev/nfs_vg/$SNAP_NAME

# 古いバックアップを削除(7 日より古い)
find $BACKUP_DIR -name '*.tar.gz' -mtime +$RETENTION -delete

logger -t nfs-backup "Backup completed"
EOF

sudo chmod +x /usr/local/sbin/nfs-snap-backup.sh
```

### 手動実行 + 動作確認

```bash
sudo /usr/local/sbin/nfs-snap-backup.sh
ls -lh /srv/nfs-backup
# 20260509_1430.tar.gz
```

## 11.3 ハンズオン: rsync によるリモートバックアップ

LVM スナップショットだけだと、サーバ自体が壊れたら終わりです。別マシンへ **rsync** で送ります。

### バックアップ先サーバの準備

仮に `k8s-lb`(192.168.56.10)をバックアップ受け先にします。

```bash
# k8s-lb 側
sudo mkdir -p /srv/nfs-rsync-backup
sudo chown -R backup-user:backup-user /srv/nfs-rsync-backup
```

### SSH キー認証(k8s-nfs → k8s-lb)

```bash
# k8s-nfs で
sudo ssh-keygen -t ed25519 -N '' -f /root/.ssh/nfs-backup-key
sudo cat /root/.ssh/nfs-backup-key.pub
# 出力された公開鍵を k8s-lb の backup-user の ~/.ssh/authorized_keys に追加

# k8s-lb で
sudo -u backup-user mkdir -p /home/backup-user/.ssh
sudo -u backup-user vim /home/backup-user/.ssh/authorized_keys
# 公開鍵を貼り付け
sudo chmod 700 /home/backup-user/.ssh
sudo chmod 600 /home/backup-user/.ssh/authorized_keys
```

### rsync スクリプト

```bash
sudo tee /usr/local/sbin/nfs-rsync-backup.sh <<'EOF'
#!/bin/bash
set -eu

SNAP_NAME=nfs_lv_snap_rsync_$(date +%Y%m%d_%H%M)
SNAP_MOUNT=/mnt/$SNAP_NAME
REMOTE_HOST=k8s-lb
REMOTE_DIR=/srv/nfs-rsync-backup
SSH_KEY=/root/.ssh/nfs-backup-key

mkdir -p $SNAP_MOUNT

# スナップショット
lvcreate -L 10G -s -n $SNAP_NAME /dev/nfs_vg/nfs_lv
mount /dev/nfs_vg/$SNAP_NAME $SNAP_MOUNT

# rsync 転送
rsync -az --delete \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
  $SNAP_MOUNT/k8s/ backup-user@$REMOTE_HOST:$REMOTE_DIR/

# クリーンアップ
umount $SNAP_MOUNT
rmdir $SNAP_MOUNT
lvremove -f /dev/nfs_vg/$SNAP_NAME

logger -t nfs-backup "rsync to $REMOTE_HOST completed"
EOF

sudo chmod +x /usr/local/sbin/nfs-rsync-backup.sh
```

### 実行 + 確認

```bash
sudo /usr/local/sbin/nfs-rsync-backup.sh

# 受け先で確認
ssh k8s-lb ls -la /srv/nfs-rsync-backup/
```

### 注意: `--delete` の罠

`rsync --delete` は **「ソースになくなったファイルを受け先からも削除」** するので、誤削除が即時に伝搬します。「**ランサムウェア対策にならない**」点に注意。これを防ぐには、受け先で **rsnapshot** のような世代管理ツールを使うのが定石です。

## 11.4 ハンズオン: rsnapshot で世代管理付きバックアップ

rsnapshot は rsync + ハードリンクで効率よく世代管理するツールです。

### インストール(バックアップ先 = k8s-lb)

```bash
sudo apt install -y rsnapshot
```

### 設定

```bash
sudo cp /etc/rsnapshot.conf /etc/rsnapshot.conf.bak

# タブ区切り注意
sudo tee /etc/rsnapshot.conf <<'EOF'
config_version    1.2
snapshot_root    /srv/nfs-rsync-backup/

cmd_cp           /bin/cp
cmd_rm           /bin/rm
cmd_rsync        /usr/bin/rsync
cmd_ssh          /usr/bin/ssh
cmd_logger       /usr/bin/logger

retain    daily    7
retain    weekly   4
retain    monthly  6

verbose         3
loglevel        3
logfile         /var/log/rsnapshot.log

ssh_args        -i /home/backup-user/.ssh/nfs-backup-key -o StrictHostKeyChecking=no

# バックアップ対象
backup    backup-user@k8s-nfs:/srv/nfs/k8s/    nfs-data/
EOF

# 構文チェック
sudo rsnapshot configtest
# Syntax OK
```

### 実行

```bash
sudo rsnapshot daily
ls /srv/nfs-rsync-backup/
# daily.0/

sudo rsnapshot daily
ls /srv/nfs-rsync-backup/
# daily.0/  daily.1/    ← 1 世代前
```

ハードリンクのため、変更されていないファイルは **ディスクを 1 つしか消費しません**。

```bash
# 実消費量を確認
sudo du -sh /srv/nfs-rsync-backup/daily.*
# 1.2G    /srv/nfs-rsync-backup/daily.0
# 50M     /srv/nfs-rsync-backup/daily.1  ← 差分のみ
```

### cron 化

```bash
sudo tee /etc/cron.d/rsnapshot <<'EOF'
0 2 * * *   root  /usr/bin/rsnapshot daily
0 3 * * 1   root  /usr/bin/rsnapshot weekly
0 4 1 * *   root  /usr/bin/rsnapshot monthly
EOF
```

## 11.5 ハンズオン: ZFS スナップショット(参考)

ZFS を使うと、スナップショットがはるかに効率的になります。本教材では ext4 を使っていますが、参考としてポイントだけ。

### ZFS への移行(参考の操作のみ)

```bash
# zfsutils-linux インストール
sudo apt install -y zfsutils-linux

# プール作成(/dev/sdb を使用、データは消えます)
sudo zpool create tank /dev/sdb

# データセット作成
sudo zfs create tank/nfs

# /etc/exports.d/ に追加
echo "/tank/nfs  192.168.56.0/24(rw,sync,no_subtree_check,fsid=10)" \
  | sudo tee /etc/exports.d/zfs-nfs.exports
sudo exportfs -ra
```

### ZFS スナップショット

```bash
# 即時、効率的(変更分のみ消費)
sudo zfs snapshot tank/nfs@2026-05-09-1400

# 一覧
sudo zfs list -t snapshot
# NAME                       USED  AVAIL  REFER  MOUNTPOINT
# tank/nfs@2026-05-09-1400      0      -  24K    -

# ロールバック
sudo zfs rollback tank/nfs@2026-05-09-1400

# 削除
sudo zfs destroy tank/nfs@2026-05-09-1400
```

### ZFS send/receive(リモートへ)

```bash
# ローカルでスナップショット
sudo zfs snapshot tank/nfs@2026-05-09-night

# リモートへ転送(別 ZFS プールへ)
sudo zfs send tank/nfs@2026-05-09-night | \
  ssh k8s-lb sudo zfs receive backup-pool/nfs-mirror

# 差分転送(2 回目以降)
sudo zfs send -i tank/nfs@2026-05-08-night tank/nfs@2026-05-09-night | \
  ssh k8s-lb sudo zfs receive backup-pool/nfs-mirror
```

ZFS なら **何 TiB のボリュームも、変更分だけが転送される** ので圧倒的に効率的です。

## 11.6 ハンズオン: CSI VolumeSnapshot と NFS

第 9 章で見たように、NFS-CSI ドライバは(バックエンド依存ですが)`VolumeSnapshot` API に対応しています。実装としては「**PVC のディレクトリを別ディレクトリに rsync コピー**」する形で、ストレージレベルのスナップショットではない点に注意。

### VolumeSnapshotClass を作る

```bash
cat > vsc.yaml <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: nfs-vsc
driver: nfs.csi.k8s.io
deletionPolicy: Delete
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
EOF

kubectl apply -f vsc.yaml
kubectl get volumesnapshotclass
```

### スナップショットを取る

```bash
cat > vs.yaml <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-snap-test
  namespace: todo
spec:
  volumeSnapshotClassName: nfs-vsc
  source:
    persistentVolumeClaimName: data-postgres-0
EOF

kubectl apply -f vs.yaml
kubectl get volumesnapshot -n todo -w
# postgres-snap-test    true   data-postgres-0   5Gi   nfs-vsc   ...   5s
```

### スナップショットから新 PVC

```bash
cat > restore-pvc.yaml <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-postgres-restored
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-dynamic
  resources:
    requests:
      storage: 5Gi
  dataSource:
    name: postgres-snap-test
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
EOF

kubectl apply -f restore-pvc.yaml
kubectl get pvc -n todo data-postgres-restored
```

### サーバ側で何が起きているか確認

```bash
# k8s-nfs で
ls -la /srv/nfs/k8s/dynamic/
# 元 PVC、スナップショット保管、復元 PVC の 3 ディレクトリ
```

NFS-CSI のスナップショットは **本物のスナップショットではなく rsync コピー** なので、データ量が増えると遅くなります。本格的なスナップショットが必要なら、LVM、ZFS、または Ceph RBD のような本物のスナップショット対応バックエンドが必要です。

## 11.7 ハンズオン: 完全な復元演習

「**バックアップは取れた」「だが戻せるか?**」を確認することが運用品質の核心です。実機で復元演習をします。

### Step 1: バックアップ取得(現状を保存)

```bash
# k8s-nfs で
sudo /usr/local/sbin/nfs-snap-backup.sh
ls -lh /srv/nfs-backup/
# 20260509_1500.tar.gz
```

### Step 2: 災害を演出

```bash
# Postgres Pod を稼働中の Namespace 全削除
kubectl delete namespace todo
# ついでに NFS データも消す
sudo rm -rf /srv/nfs/k8s/dynamic/todo-data-postgres-0
```

これで Pod と NFS 上のデータの両方が消えました。

### Step 3: NFS データ復元

```bash
# 別の場所に展開
sudo mkdir -p /tmp/restore
sudo tar xzf /srv/nfs-backup/20260509_1500.tar.gz -C /tmp/restore
ls /tmp/restore/k8s/dynamic/

# 必要なディレクトリだけ書き戻す
sudo cp -a /tmp/restore/k8s/dynamic/todo-data-postgres-0 /srv/nfs/k8s/dynamic/
sudo chown -R 999:999 /srv/nfs/k8s/dynamic/todo-data-postgres-0
```

### Step 4: Kubernetes リソース復元

第 5 部の静的 PV ハンズオンの応用で、復元されたディレクトリを **手動 PV** として登録 → PVC を bind → Pod を起動、という流れで戻します。

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: todo
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-postgres-restored
spec:
  capacity: { storage: 5Gi }
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions: [nfsvers=4.1, hard]
  nfs:
    server: 192.168.56.30
    path: /srv/nfs/k8s/dynamic/todo-data-postgres-0
  claimRef:
    name: data-postgres-0
    namespace: todo
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-postgres-0
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources: { requests: { storage: 5Gi } }
```

### Step 5: Pod 起動 + 動作確認

```bash
# StatefulSet も復元
kubectl apply -f postgres-sts.yaml      # 第 5 章で作ったもの

kubectl get pod -n todo
kubectl exec -n todo postgres-0 -- psql -U todo -c "SELECT count(*) FROM tasks;"
# (バックアップ時点のデータ数)
```

### Step 6: タイミング測定

復元にかかった時間を測ります。

| 工程 | 想定時間 |
|------|---------|
| バックアップ展開(tar) | 数分(サイズ依存) |
| NFS データ書き戻し | 数分 |
| PV / PVC apply | 数秒 |
| StatefulSet apply + Pod 起動 | 1〜2 分 |
| **合計 RTO** | **10〜15 分** |

「**RTO 10 分**」が SLO に書いてあるなら、この復元時間で OK。「**RTO 1 分**」が要件なら、LVM スナップショットからの戻し or HA NFS への切替で対応する設計が必要です。

## 11.8 バックアップ運用のチェックリスト

```mermaid
flowchart TB
    A[バックアップ運用] --> B[自動化]
    A --> C[暗号化]
    A --> D[オフサイト]
    A --> E[復元演習]
    A --> F[監視]
    B --> B1[cron / systemd timer]
    C --> C1[restic / kopia / GPG]
    D --> D1[別データセンタ /<br>クラウドストレージ]
    E --> E1[四半期に 1 回]
    F --> F1[Prometheus メトリクス]
```

| 項目 | 推奨実装 |
|------|---------|
| 取得頻度 | 日次フル、時次差分(高重要度なら) |
| 保管期間 | 日次 7、週次 4、月次 6、年次 7 |
| 取得場所 | 同サーバの別ボリューム + オフサイト |
| 暗号化 | restic / kopia(自動)or GPG |
| 復元演習 | 四半期に 1 回(本番から切り離した環境で) |
| 監視 | バックアップサイズ、最終成功時刻、容量 |
| ドキュメント | 復元手順書(変更管理に乗せる) |

## 11.9 第 11 部のまとめ

- スナップショットとバックアップは **別物**(スナップショットは同サーバ、バックアップは別サーバ)
- LVM スナップショットは **元 LV と同じ VG に空きが必要**
- 自動化は cron + シェルスクリプトで十分(凝るなら restic / kopia)
- リモート転送は rsync + ハードリンク世代管理(rsnapshot)or ZFS send/receive
- NFS-CSI の VolumeSnapshot は内部的に rsync ベースの実装が多い
- **「戻せること」を確認するまでバックアップは完成していない**

第 12 部では **NFS のトラブルシューティング** を実機で再現しながら覚えます。

---

# 第 12 部: NFS トラブルシューティング完全集

このセクションでは、NFS で起きる代表的なトラブルを **実機で意図的に再現** し、調査の第一手と解決手順を体得します。「症状から原因へ」のフローと、「原因を再現する手順」の両方を持つことが、本番で慌てない秘訣です。

## 12.1 トラブルシュート全体フロー

```mermaid
flowchart TB
    A[症状発生] --> B{どこで起きてる?}
    B --> C[Pod 起動失敗<br>ContainerCreating]
    B --> D[ファイル操作エラー<br>Stale handle, EACCES]
    B --> E[性能劣化]
    B --> F[全断]
    C --> C1[describe pod<br>kubelet ログ]
    D --> D1[mount 状態<br>nfsstat<br>nfsiostat]
    E --> E1[fio, iperf3<br>サーバ負荷]
    F --> F1[ping, ss, ufw<br>サーバプロセス]
```

調査の第一手は **「どこ」を切り分ける** こと。Pod 側か、ノード側か、サーバ側か。

## 12.2 ハンズオン: Stale file handle を再現する

これは NFS で最も有名なエラーです。理屈は第 1.3 節で扱いましたが、実機で再現しましょう。

### 再現手順

#### Step 1: NFS をマウント

```bash
# k8s-w1 で
sudo mkdir -p /mnt/stale-test
sudo mount -t nfs -o nfsvers=4.1 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/stale-test
echo "before" | sudo tee /mnt/stale-test/file.txt
```

#### Step 2: クライアントで開いたまま、サーバで削除

```bash
# k8s-w1 でファイルを開いたまま放置
sudo tail -f /mnt/stale-test/file.txt &
TAIL_PID=$!

# 別ターミナルで k8s-nfs に行ってファイルを削除
ssh k8s-nfs "sudo rm /srv/nfs/k8s/static/file.txt && sudo touch /srv/nfs/k8s/static/file.txt"
# 同名で再作成 → 別 inode に
```

#### Step 3: クライアントで再度触る

```bash
# k8s-w1 で
sudo cat /mnt/stale-test/file.txt
# cat: /mnt/stale-test/file.txt: Stale file handle

ls -la /mnt/stale-test/
# ls: cannot access '/mnt/stale-test/file.txt': Stale file handle
```

これが Stale file handle の正体です。

### 対処法

**ケース A: 単一ファイル**

```bash
# クライアントで再読み込み
sudo umount /mnt/stale-test
sudo mount -t nfs -o nfsvers=4.1 \
  192.168.56.30:/srv/nfs/k8s/static /mnt/stale-test
cat /mnt/stale-test/file.txt
# 正常
```

**ケース B: マウント全体が stale**

```bash
# 強制アンマウント
sudo umount -f /mnt/stale-test

# それでもダメなら lazy umount
sudo umount -l /mnt/stale-test

# 再マウント
sudo mount -t nfs ...
```

**ケース C: Pod 内で起きた場合**

Pod 内で Stale が出ると、Pod 自体を再起動するのが最速です。

```bash
kubectl delete pod -n todo postgres-0
```

新しい Pod が立ち上がるときに kubelet が再マウントするので回復します。

### 予防

- NFS 共有上のファイルを **削除 → 再作成** するワークフローを避ける(`mv` で置き換える、`O_TRUNC` で開きなおす)
- バックアップ復元では一旦アンマウント → 復元 → 再マウントの順
- 長時間開きっぱなしのファイルディスクリプタを持つアプリは、定期的に開きなおす

## 12.3 ハンズオン: Connection refused を再現

「mount しようとすると `Connection refused`」というエラーです。

### 再現

```bash
# k8s-nfs で NFS サービスを止める
ssh k8s-nfs sudo systemctl stop nfs-server

# k8s-w1 でマウントを試す
sudo mount -t nfs 192.168.56.30:/srv/nfs/k8s/static /mnt/test
# mount.nfs: Connection refused
```

### 切り分け

```bash
# 1. ネットワーク到達性
ping -c 3 192.168.56.30

# 2. ポート 2049 が開いてるか
nc -zv 192.168.56.30 2049
# nc: connect to 192.168.56.30 port 2049 (tcp) failed: Connection refused

# 3. サーバ側プロセス確認
ssh k8s-nfs "sudo systemctl status nfs-server"
# Active: inactive (dead) ← サーバが落ちてる

# 4. 復旧
ssh k8s-nfs sudo systemctl start nfs-server

# 再度確認
nc -zv 192.168.56.30 2049
# Connection to 192.168.56.30 2049 port [tcp/nfs] succeeded!

# マウントできるか
sudo mount -t nfs 192.168.56.30:/srv/nfs/k8s/static /mnt/test
ls /mnt/test
```

### Connection refused 系の原因マトリクス

| 原因 | 検知方法 | 対処 |
|------|---------|------|
| nfs-server が落ちてる | `systemctl status nfs-server` | start |
| ファイアウォール | `nc -zv` でも refused | ufw / iptables 確認 |
| サーバ IP 間違い | ping 不可 | hosts や DNS 確認 |
| サブネット非到達 | route 不可 | ルーティング・VLAN 確認 |
| TCP/UDP の指定間違い | `mount -o proto=...` | NFSv4 なら tcp |

## 12.4 ハンズオン: Operation not permitted

権限関連のエラーです。Pod 内で `Permission denied` や `Operation not permitted` が出るパターンを再現します。

### 再現

```bash
# k8s-nfs で root_squash 有効なエクスポートを作る
sudo mkdir -p /srv/nfs/k8s/squash-test
sudo chown 1000:1000 /srv/nfs/k8s/squash-test
sudo chmod 0700 /srv/nfs/k8s/squash-test
echo "/srv/nfs/k8s/squash-test  192.168.56.0/24(rw,sync,no_subtree_check,root_squash,fsid=40)" \
  | sudo tee -a /etc/exports
sudo exportfs -ra
```

```bash
# Pod を root で実行する設定
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-squash-test
spec:
  capacity: { storage: 1Gi }
  accessModes: [ReadWriteMany]
  storageClassName: ""
  nfs:
    server: 192.168.56.30
    path: /srv/nfs/k8s/squash-test
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-squash-test
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  resources: { requests: { storage: 1Gi } }
  volumeName: pv-squash-test
---
apiVersion: v1
kind: Pod
metadata:
  name: squash-test
spec:
  containers:
  - name: app
    image: alpine
    command: ["sh", "-c", "touch /data/i-am-root && sleep 3600"]
    volumeMounts:
    - { name: data, mountPath: /data }
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-squash-test
EOF
```

### 観察

```bash
kubectl logs squash-test
# touch: /data/i-am-root: Permission denied
```

これが起きる理由:

1. Pod のデフォルト UID は 0(root)
2. NFS サーバで `root_squash` 有効
3. クライアントの UID 0 → サーバ側で UID 65534(nobody)に変換
4. NFS 上のディレクトリは UID 1000 所有、`0700` パーミッション
5. nobody は読み書きできない → `Permission denied`

### 解決法 A: Pod を UID 1000 で起動

```yaml
spec:
  securityContext:
    runAsUser: 1000
    fsGroup: 1000
```

### 解決法 B: NFS サーバ側のパーミッションを緩める

```bash
ssh k8s-nfs "sudo chmod 0777 /srv/nfs/k8s/squash-test"
```

### 解決法 C: no_root_squash + 信頼できる環境

学習環境のみ。本番では使わない。

### Operation not permitted の原因マトリクス

| 症状 | 原因 | 対処 |
|------|------|------|
| `Permission denied` | 一般的な UID/権限 不一致 | `runAsUser` / `fsGroup` 合わせ |
| `Operation not permitted` | root_squash で root 操作 | `runAsUser` 設定 or squash 解除 |
| `mount: Operation not permitted` | secure オプションで NAT 越え失敗 | `insecure` を export 側に |

## 12.5 ハンズオン: ContainerCreating で詰まる

Pod が `ContainerCreating` のまま 5 分以上動かないパターンです。原因として NFS マウントタイムアウトがよくあります。

### 再現

```bash
# 存在しない IP の NFS を指定した PV を作る
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-bad-nfs
spec:
  capacity: { storage: 1Gi }
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  nfs:
    server: 192.168.56.99   # ★存在しない
    path: /nonexistent
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-bad-nfs
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  resources: { requests: { storage: 1Gi } }
  volumeName: pv-bad-nfs
---
apiVersion: v1
kind: Pod
metadata:
  name: stuck-pod
spec:
  containers:
  - name: app
    image: alpine
    command: ["sleep", "3600"]
    volumeMounts:
    - { name: data, mountPath: /data }
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-bad-nfs
EOF
```

### 観察

```bash
kubectl get pod stuck-pod
# stuck-pod   0/1   ContainerCreating   0   2m

kubectl describe pod stuck-pod | tail -20
# Events:
#   Type     Reason       From     Message
#   ----     ------       ----     -------
#   Warning  FailedMount  kubelet  Unable to attach or mount volumes:
#     unmounted volumes=[data], unattached volumes=[data kube-api-access-xxxx]:
#     timed out waiting for the condition
```

### 調査の第一手

```bash
# Pod がスケジュールされているノードを特定
kubectl get pod stuck-pod -o wide
# stuck-pod   0/1  ContainerCreating  ...  k8s-w2

# そのノードで kubelet ログを見る
ssh k8s-w2 sudo journalctl -u kubelet -f
# May 09 15:20:23 k8s-w2 kubelet[1234]:
#   mount.nfs: Connection timed out

# 手動マウントで切り分け
ssh k8s-w2 sudo mount -t nfs 192.168.56.99:/nonexistent /mnt/test
# mount.nfs: Connection timed out  ← サーバ側 IP の問題と確定
```

### 解決

```bash
# 正しい IP の PV を作り直す
kubectl delete pod stuck-pod
kubectl delete pvc pvc-bad-nfs
kubectl delete pv pv-bad-nfs

# 正しい設定の PV/PVC を再作成
```

### ContainerCreating 系の原因マトリクス

| サブパターン | 確認 | 対処 |
|------------|------|------|
| NFS サーバ到達不可 | kubelet ログ `Connection timed out` | NW / サーバ確認 |
| エクスポート権限なし | `Permission denied` `access denied by server` | `/etc/exports` 確認 |
| CSI ドライバ Pod 落ちてる | `kubectl get pods -n kube-system | grep csi` | CSI Pod 再起動 |
| `subtree_check` 副作用 | `unauthorized to access` | `no_subtree_check` に |
| `secure` で特権ポート不足 | `mount: Operation not permitted` | `insecure` 追加 |

## 12.6 ハンズオン: マウントが 30 秒以上待たされる

`fsGroup` の再帰 chown が遅いパターンです。

### 再現

```bash
# PVC に大量の小ファイルを置く Pod
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: many-files
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-dynamic
  resources: { requests: { storage: 5Gi } }
---
apiVersion: v1
kind: Pod
metadata:
  name: file-generator
spec:
  containers:
  - name: gen
    image: alpine
    command:
    - sh
    - -c
    - |
      for i in \$(seq 1 50000); do
        echo "file \$i" > /data/file-\$i.txt
      done
      sleep 3600
    volumeMounts:
    - { name: data, mountPath: /data }
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: many-files
EOF

# 5 万ファイル生成を待つ(数分)
kubectl wait --for=condition=Ready pod file-generator --timeout=600s
kubectl exec file-generator -- ls /data | wc -l
# 50000
```

### 遅延が出るパターン

```yaml
# 5 万ファイルがある PVC を、別 Pod で fsGroup 付きでマウント
apiVersion: v1
kind: Pod
metadata:
  name: slow-mount
spec:
  securityContext:
    fsGroup: 1234
    # fsGroupChangePolicy: 未設定(デフォルト Always)
  containers:
  - name: app
    image: alpine
    command: ["sleep", "3600"]
    volumeMounts:
    - { name: data, mountPath: /data }
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: many-files
```

```bash
# 起動時間を計測
time kubectl wait --for=condition=Ready pod slow-mount --timeout=600s
# real    1m23.456s    ← マウントに 1 分以上!
```

### 観察

kubelet ログに **「Setting volume ownership for ... seconds」** のような出力が出ます。

```bash
ssh k8s-w1 sudo journalctl -u kubelet -n 100 | grep -i ownership
```

### 解決 1: `fsGroupChangePolicy: OnRootMismatch`

```yaml
spec:
  securityContext:
    fsGroup: 1234
    fsGroupChangePolicy: OnRootMismatch
```

```bash
kubectl delete pod slow-mount
kubectl apply -f slow-mount-v2.yaml

time kubectl wait --for=condition=Ready pod slow-mount --timeout=600s
# real    0m12.345s    ← 一瞬!
```

`OnRootMismatch` はマウントポイント直下の所有者が `fsGroup` と一致していれば再帰 chown をスキップします。

### 解決 2: サーバ側で事前に chown

```bash
# k8s-nfs 側で、PVC ディレクトリの所有者を事前に揃える
sudo chown -R 999:1234 /srv/nfs/k8s/dynamic/todo-many-files
```

これで Pod 起動時に chown が不要になります。

### 解決 3: CSI ドライバの `fsGroupPolicy`

CSI ドライバが対応していれば、`fsGroupPolicy: None` で kubelet に「`fsGroup` 適用しないで」と伝えられます。NFS-CSI は対応してます。

```bash
kubectl get csidriver nfs.csi.k8s.io -o yaml | grep fsGroupPolicy
# fsGroupPolicy: File  ← デフォルト
```

## 12.7 ハンズオン: NFS のロックがハングする

PostgreSQL や Redis のように fcntl ロックを使うアプリで、ロックが取れず Pod がハングするパターンです。

### 再現(古い NFSv3 環境のシミュレーション)

NFSv3 (mountd, lockd の連携が必要)で、`lockd` を意図的に止めると再現できます。本教材は NFSv4-only なので意図的にロックを破る再現は難しいですが、症状の確認方法は同じです。

### 症状確認方法

```bash
# Pod 内の状態
kubectl exec -n todo postgres-0 -- ps auxf
# postgres プロセスが <defunct> や D state

# ノードで
ssh k8s-w1 sudo ps auxf | grep ' D '
# プロセスが Uninterruptible Sleep に張り付き

# ロック取得待ちのプロセスを探す
ssh k8s-w1 sudo cat /proc/*/wchan 2>/dev/null | grep -i lock
```

### 一般的な解決

1. **NFSv4.1 以上を使う**(本教材のデフォルト)
2. NFS サーバ側で `rpc-statd` がちゃんと動いているか確認(NFSv3 のみ)
3. クライアント・サーバの時刻同期確認(`chronyc tracking`)
4. それでもダメなら強制再マウント

```bash
sudo umount -l /mnt/locked
sudo mount -t nfs -o nfsvers=4.1,hard,timeo=600 ...
```

### 予防のためのマウントオプション

| オプション | 役割 |
|-----------|------|
| `hard` | サーバ復帰まで永遠に待つ(データ整合性◎) |
| `soft,timeo=N` | N 秒で諦めて I/O エラー(整合性× だが固まらない) |
| `intr` | (古い)シグナルで中断可能 |

DB バックエンドなら必ず `hard`。アプリが固まるリスクを許容できないなら `soft`(ただし整合性低下)。

## 12.8 ハンズオン: 性能が突然遅くなる

「**昨日まで普通だったのに、今日から書き込みが遅い**」というクレームに対応するシナリオです。

### 再現(サーバ側ディスクの I/O を意図的に詰まらせる)

```bash
# k8s-nfs で、NFS データボリュームに巨大な書き込みを発生させる
sudo dd if=/dev/zero of=/srv/nfs/k8s/static/iotest bs=1M count=10240 &
```

### 切り分けの第一手

```bash
# 1. クライアントから測る
kubectl exec -n todo postgres-0 -- \
  dd if=/dev/zero of=/var/lib/postgresql/data/pgdata/iotest bs=1M count=100 oflag=direct
# 5+ 秒、急に遅い

# 2. サーバ側 I/O 状況
ssh k8s-nfs sudo iostat -dx 1
# Device  r/s   w/s   rkB/s   wkB/s   await
# sdb     0   500   0      512000  20.00   ← 高負荷

# 3. nfsstat で
ssh k8s-nfs sudo nfsstat -s -Z 1
# 統計が変化していれば NFS への RPC は来ている

# 4. nfsiostat でクライアント側
ssh k8s-w1 sudo nfsiostat 5
# avg RTT が急上昇 → サーバ側遅延
```

### 解決

```bash
# 遅延の元を kill
ssh k8s-nfs sudo pkill -f 'dd if=/dev/zero'

# 性能回復確認
kubectl exec -n todo postgres-0 -- \
  dd if=/dev/zero of=/var/lib/postgresql/data/pgdata/iotest bs=1M count=100 oflag=direct
# 0.5 秒くらいに戻る
```

### 性能劣化の原因マトリクス

| 原因 | 検知 | 対処 |
|------|------|------|
| サーバ I/O 飽和 | `iostat -dx` で `%util` 100% | 重いプロセス特定、I/O 制限 |
| サーバ CPU 飽和 | `top` で nfsd CPU 高い | nfsd threads 増、CPU 増設 |
| ネットワーク帯域 | `nload` / `iftop` | QoS、NIC 増設 |
| NIC エラー | `ip -s link` で errors/drops | ケーブル / 設定 |
| クライアント側 NFS キャッシュ | `nfsstat -c` ヒット率 | actimeo 調整 |
| 同居プロセス | `top` で iotop | 別 LV に分離 |

## 12.9 ハンズオン: rpcinfo が応答しない

サーバ側で NFS が動いていない、または rpcbind の問題。

```bash
# クライアントから
rpcinfo -p 192.168.56.30
# rpcinfo: can't contact portmapper: ...

# 切り分け
ping 192.168.56.30                          # NW 到達?
nc -zv 192.168.56.30 111                    # portmapper ポート?
nc -zv 192.168.56.30 2049                   # NFS ポート?

# サーバ側
ssh k8s-nfs sudo systemctl status rpcbind
ssh k8s-nfs sudo systemctl status nfs-server
```

NFSv4-only モードでは `rpcbind` を切っても動きますが、`rpcinfo` も応答しません。`nc -zv :2049` で代替確認します。

## 12.10 ハンズオン: NFS マウント情報を kubectl で確認する

Pod 内から NFS マウントの素性を確認する小ワザ。

```bash
# Pod 内のマウント情報を見る
kubectl exec -n todo postgres-0 -- cat /proc/mounts | grep nfs
# 192.168.56.30:/srv/nfs/... /var/lib/postgresql/data nfs4 rw,relatime,...,nfsvers=4.1,nconnect=1,...

# マウントオプションを確認
kubectl exec -n todo postgres-0 -- mount | grep nfs
# 192.168.56.30:/srv/nfs/... on /var/lib/postgresql/data type nfs4 (rw,relatime,...)

# NFS 統計
kubectl exec -n todo postgres-0 -- cat /proc/self/mountstats
```

これで「**実際に何バージョンの NFS で、どんなオプションでマウントされているか**」が分かります。StorageClass で指定したオプションが効いているかの最終確認に使います。

## 12.11 全症状カタログ(ワンライナー対処付き)

| 症状 | 第一手コマンド | 第二手 / 対処 |
|------|---------------|---------------|
| `Stale file handle` | `sudo umount -l <mp> && sudo mount ...` | Pod なら `kubectl delete pod` |
| `Connection refused` | `nc -zv <server> 2049` | サーバ `systemctl status nfs-server` |
| `Connection timed out` | `ping <server>` | ufw / 経路確認 |
| `Permission denied` | `kubectl exec ... -- id` | `runAsUser` / `fsGroup` 一致 |
| `Operation not permitted` | `mount | grep nfs` で root_squash 確認 | `runAsNonRoot` 設定 |
| `access denied by server` | `exportfs -v` でクライアント許可確認 | `/etc/exports` 修正 |
| `mount.nfs: Protocol not supported` | `cat /proc/fs/nfsd/versions` | バージョン整合 |
| `ContainerCreating` 5 分以上 | `kubectl describe pod` の Events | kubelet ログ確認 |
| マウントに 30 秒以上 | kubelet ログ `Setting volume ownership` | `fsGroupChangePolicy: OnRootMismatch` |
| 性能急落 | サーバ `iostat -dx 1` | I/O 元プロセス特定 |
| ロックハング | `ps auxf | grep ' D '` | NFSv4.1+ に統一、再マウント |
| `.nfs*` 隠しファイル散乱 | `find <export> -name '.nfs*'` | プロセス終了確認後削除 |
| PVC が Pending | `kubectl describe pvc` | CSI Pod ログ |
| VolumeAttachment 残骸 | `kubectl get volumeattachment` | 手動削除 |

## 12.12 デバッグツール早見表

| 用途 | コマンド |
|------|---------|
| NFS サービス確認 | `systemctl status nfs-server` |
| エクスポート一覧 | `exportfs -v` |
| クライアント一覧 | `showmount -e <server>`(NFSv3 のみ確実) |
| RPC 確認 | `rpcinfo -p <server>` |
| マウント情報 | `mount | grep nfs`、`/proc/mounts` |
| サーバ統計 | `nfsstat -s -Z 5` |
| クライアント I/O | `nfsiostat 5` |
| カーネルデバッグ | `echo 0xffff > /proc/sys/sunrpc/{rpc,nfsd}_debug` |
| ロック一覧 | `cat /proc/locks` |
| サーバ側 I/O | `iostat -dx 1`、`iotop` |
| ネットワーク | `iperf3 -c <server>`、`nload`、`iftop` |
| パケットキャプチャ | `tcpdump -i any -w nfs.pcap port 2049` |

`tcpdump` で NFS パケットを取って Wireshark で開くと、各 RPC オペレーションが見えるので、難しい問題の最終手段として有効です。

## 12.13 ハンズオン: tcpdump で NFS パケットを観察

```bash
# サーバ側で取る(別ターミナル)
ssh k8s-nfs sudo tcpdump -i any -s 0 -w /tmp/nfs.pcap 'port 2049'

# クライアントから操作
kubectl exec -n todo postgres-0 -- ls /var/lib/postgresql/data

# しばらく経ったら停止
# Ctrl+C

# pcap を取ってくる
scp k8s-nfs:/tmp/nfs.pcap .

# Wireshark or tshark で開く
tshark -r nfs.pcap -Y nfs
# 1   0.000000  192.168.56.21 → 192.168.56.30 NFS V4 COMPOUND Call ...
# 2   0.000234  192.168.56.30 → 192.168.56.21 NFS V4 COMPOUND Reply ...
```

NFSv4 の COMPOUND オペレーションが時系列で見られます。「**実際にどの NFS オペレーションで詰まっているか**」が一発で分かるので、原因特定の最強ツールです。

## 12.14 第 12 部のまとめ

- トラブルは「Pod 側 / ノード側 / サーバ側」のどこか切り分けが最優先
- Stale file handle はマウントしなおしで解消(Pod なら delete pod)
- 権限系は `runAsUser` / `fsGroup` をサーバ側ディレクトリと一致させる
- `ContainerCreating` 詰まりは kubelet ログを必ず確認
- 性能劣化は `iostat` / `nfsiostat` で位置特定
- 最後の武器は `tcpdump` で NFS パケット観察

第 13 部では、これまでの全知識を集約して **TODO サービス全体を NFS だけで動かす** 完全ハンズオンに進みます。

---

# 第 13 部: 総合ハンズオン ─ TODO サービスを NFS だけで動かす

ここまでの全知識を統合し、本教材のサンプルアプリ「ミニ TODO サービス」を NFS バックエンドのみで構築します。**ステップを 1 つずつ実行**してください。各ステップで「何が起きるか」「期待される出力」を明示します。

## 13.1 構成図

```mermaid
flowchart TB
    subgraph User[ユーザ]
        Br[Browser]
    end
    subgraph K8s[Kubernetes クラスタ]
        Ing[Ingress<br>todo.example.local]
        Fe[Frontend Deployment<br>nginx + HTML]
        Api[API Deployment<br>FastAPI]
        Up[uploads<br>RWX 静的 PVC]
        subgraph PG[postgres StatefulSet]
            P0[postgres-0]
            Pp[data-postgres-0<br>RWO PVC 動的]
        end
        subgraph RD[redis StatefulSet]
            R0[redis-0]
            Rp[data-redis-0<br>RWO PVC 動的]
        end
        W[Worker CronJob<br>毎10分]
    end
    subgraph NFS[NFS サーバ k8s-nfs]
        D1[/srv/nfs/k8s/dynamic]
        D2[/srv/nfs/k8s/static/uploads]
    end

    Br --> Ing --> Fe & Api
    Api --> P0
    Api --> R0
    Api --> Up
    W --> P0
    W --> Up
    Pp -.NFS-CSI 動的.-> D1
    Rp -.NFS-CSI 動的.-> D1
    Up -.手動 PV.-> D2
```

## 13.2 ハンズオン Step 1: クリーンアップ

前のハンズオンの残骸を一掃しておきます。

```bash
# 既存リソース削除
kubectl delete namespace todo --ignore-not-found
kubectl delete pv -l app.kubernetes.io/part-of=todo --ignore-not-found

# NFS サーバ側のデータも掃除
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/dynamic/todo-*"
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/static/uploads"
```

## 13.3 ハンズオン Step 2: NFS サーバ側準備

第 2 部のサーバ構築が完了している前提です。今回追加で必要なディレクトリ:

```bash
ssh k8s-nfs <<'EOF'
sudo mkdir -p /srv/nfs/k8s/static/uploads
sudo chown 1000:1000 /srv/nfs/k8s/static/uploads
sudo chmod 0775 /srv/nfs/k8s/static/uploads
sudo exportfs -ra
sudo exportfs -v
EOF
```

`/srv/nfs/k8s/static` は第 2.5 節ですでに公開されているので、追加 export は不要です。

## 13.4 ハンズオン Step 3: NFS-CSI ドライバ確認

第 4 部でインストール済みのはずですが、改めて確認します。

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=csi-driver-nfs
# csi-nfs-controller-...     4/4    Running
# csi-nfs-node-...           3/3    Running   (×3 workers)

kubectl get csidriver
# NAME                ATTACHREQUIRED   PODINFOONMOUNT   ...
# nfs.csi.k8s.io      false            false
```

落ちていれば第 4.2 節の Helm 再インストール手順で復旧してください。

## 13.5 ハンズオン Step 4: Namespace と StorageClass

```yaml
# 00-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: todo
  labels:
    app.kubernetes.io/part-of: todo
```

```yaml
# 01-storageclass.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-dynamic
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dynamic
  subDir: ${pvc.metadata.namespace}-${pvc.metadata.name}
mountOptions:
- nfsvers=4.1
- hard
- timeo=600
- noatime
- nconnect=4
reclaimPolicy: Retain
volumeBindingMode: Immediate
allowVolumeExpansion: true
```

```bash
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-storageclass.yaml

# default SC が複数あれば剥がす
kubectl get sc
# nfs-dynamic (default)   nfs.csi.k8s.io   ...
```

## 13.6 ハンズオン Step 5: シークレット

```yaml
# 02-secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: todo
type: Opaque
stringData:
  POSTGRES_PASSWORD: changeme123
  POSTGRES_USER: todo
  POSTGRES_DB: todo
---
apiVersion: v1
kind: Secret
metadata:
  name: redis-secret
  namespace: todo
type: Opaque
stringData:
  REDIS_PASSWORD: redisme456
```

```bash
kubectl apply -f 02-secrets.yaml
kubectl get secret -n todo
```

## 13.7 ハンズオン Step 6: PostgreSQL StatefulSet

```yaml
# 03-postgres.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: todo
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: postgres
  ports:
  - { port: 5432, targetPort: 5432 }
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: todo
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: postgres
  template:
    metadata:
      labels:
        app.kubernetes.io/name: postgres
        app.kubernetes.io/part-of: todo
    spec:
      securityContext:
        fsGroup: 999
        fsGroupChangePolicy: OnRootMismatch
      containers:
      - name: postgres
        image: postgres:16
        env:
        - name: POSTGRES_PASSWORD
          valueFrom: { secretKeyRef: { name: postgres-secret, key: POSTGRES_PASSWORD } }
        - name: POSTGRES_USER
          valueFrom: { secretKeyRef: { name: postgres-secret, key: POSTGRES_USER } }
        - name: POSTGRES_DB
          valueFrom: { secretKeyRef: { name: postgres-secret, key: POSTGRES_DB } }
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        ports:
        - { containerPort: 5432, name: pg }
        volumeMounts:
        - { name: data, mountPath: /var/lib/postgresql/data }
        readinessProbe:
          exec: { command: [pg_isready, -U, todo] }
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          exec: { command: [pg_isready, -U, todo] }
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests: { cpu: 250m, memory: 512Mi }
          limits:   { cpu: 1,    memory: 1Gi }
  volumeClaimTemplates:
  - metadata: { name: data }
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: nfs-dynamic
      resources: { requests: { storage: 5Gi } }
```

```bash
kubectl apply -f 03-postgres.yaml
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=postgres -n todo --timeout=180s

kubectl get pvc -n todo
# data-postgres-0   Bound   pvc-...   5Gi   RWO   nfs-dynamic
```

### 初期スキーマ投入

```bash
kubectl exec -n todo postgres-0 -- psql -U todo <<'EOF'
CREATE TABLE IF NOT EXISTS tasks (
  id          SERIAL PRIMARY KEY,
  title       TEXT NOT NULL,
  description TEXT,
  done        BOOLEAN DEFAULT FALSE,
  due_at      TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS attachments (
  id          SERIAL PRIMARY KEY,
  task_id     INT REFERENCES tasks(id) ON DELETE CASCADE,
  filename    TEXT NOT NULL,
  uploaded_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO tasks (title, due_at) VALUES
  ('K8s ストレージ章を読み終える', NOW() + INTERVAL '3 days'),
  ('NFS-CSI を試す',               NOW() + INTERVAL '1 day'),
  ('スナップショットを取る',       NOW() + INTERVAL '5 days');
SELECT * FROM tasks;
EOF
```

### NFS サーバ側で確認

```bash
ssh k8s-nfs sudo ls -la /srv/nfs/k8s/dynamic/todo-data-postgres-0/pgdata/
# drwx------ 19 999 999 4096 ... base
# drwx------  2 999 999 4096 ... global
# drwx------  2 999 999 4096 ... pg_wal
```

UID **999**、`drwx------` で書かれています = `fsGroup: 999` が効いて PostgreSQL のデフォルト UID にマップされている、ということが NFS サーバから直接確認できます。

## 13.8 ハンズオン Step 7: Redis StatefulSet

```yaml
# 04-redis.yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: todo
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: redis
  ports:
  - { port: 6379, targetPort: 6379 }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
  namespace: todo
data:
  redis.conf: |
    bind 0.0.0.0
    protected-mode yes
    requirepass redisme456
    save 60 1000
    appendonly yes
    appendfsync everysec
    dir /data
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: todo
spec:
  serviceName: redis
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: redis
  template:
    metadata:
      labels:
        app.kubernetes.io/name: redis
        app.kubernetes.io/part-of: todo
    spec:
      securityContext:
        fsGroup: 999
        fsGroupChangePolicy: OnRootMismatch
      containers:
      - name: redis
        image: redis:7-alpine
        command: [redis-server, /etc/redis/redis.conf]
        ports: [{ containerPort: 6379 }]
        volumeMounts:
        - { name: data,   mountPath: /data }
        - { name: config, mountPath: /etc/redis }
        readinessProbe:
          exec: { command: [redis-cli, -a, redisme456, ping] }
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: config
        configMap: { name: redis-config }
  volumeClaimTemplates:
  - metadata: { name: data }
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: nfs-dynamic
      resources: { requests: { storage: 1Gi } }
```

```bash
kubectl apply -f 04-redis.yaml
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=redis -n todo --timeout=120s

kubectl exec -n todo redis-0 -- redis-cli -a redisme456 SET test:hello "world"
kubectl exec -n todo redis-0 -- redis-cli -a redisme456 GET test:hello
# "world"

ssh k8s-nfs sudo ls -la /srv/nfs/k8s/dynamic/todo-data-redis-0/
```

## 13.9 ハンズオン Step 8: アップロード用 RWX PVC(静的 PV)

複数 API Pod が共有書き込みする領域。第 2 部で作った `/srv/nfs/k8s/static/uploads` を bind します。

```yaml
# 05-uploads-pv.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-todo-uploads
  labels:
    app.kubernetes.io/part-of: todo
    use: uploads
spec:
  capacity: { storage: 10Gi }
  accessModes: [ReadWriteMany]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions: [nfsvers=4.1, hard, noatime]
  nfs:
    server: 192.168.56.30
    path: /srv/nfs/k8s/static/uploads
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: uploads
  namespace: todo
  labels:
    app.kubernetes.io/part-of: todo
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  resources: { requests: { storage: 10Gi } }
  selector:
    matchLabels:
      app.kubernetes.io/part-of: todo
      use: uploads
```

```bash
kubectl apply -f 05-uploads-pv.yaml
kubectl get pv,pvc -n todo | grep uploads
# pv/pv-todo-uploads   10Gi   RWX   Retain   Bound   todo/uploads
# pvc/uploads          Bound  pv-todo-uploads   10Gi  RWX
```

## 13.10 ハンズオン Step 9: API Deployment(RWX 共有確認込み)

```yaml
# 06-api.yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: todo
spec:
  selector:
    app.kubernetes.io/name: api
  ports:
  - { name: http, port: 8000, targetPort: 8000 }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: todo
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: api
        app.kubernetes.io/part-of: todo
    spec:
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
      - name: api
        image: 192.168.56.10:5000/todo-api:0.1.0
        env:
        - name: DATABASE_URL
          value: postgresql://todo:changeme123@postgres.todo.svc:5432/todo
        - name: REDIS_URL
          value: redis://:redisme456@redis.todo.svc:6379/0
        - name: UPLOAD_DIR
          value: /uploads
        ports: [{ containerPort: 8000 }]
        volumeMounts:
        - { name: uploads, mountPath: /uploads }
        readinessProbe:
          httpGet: { path: /healthz, port: 8000 }
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: uploads
        persistentVolumeClaim:
          claimName: uploads
      # 異なるノードに分散させる
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app.kubernetes.io/name: api
```

```bash
kubectl apply -f 06-api.yaml
kubectl wait --for=condition=Available deployment/api -n todo --timeout=180s

# 2 つの API Pod が別ノードにいるか
kubectl get pods -n todo -l app.kubernetes.io/name=api -o wide
# api-xxx-y1   1/1   Running   ...   k8s-w1
# api-xxx-y2   1/1   Running   ...   k8s-w2
```

### RWX マウントの実証

```bash
POD1=$(kubectl get pod -n todo -l app.kubernetes.io/name=api -o jsonpath='{.items[0].metadata.name}')
POD2=$(kubectl get pod -n todo -l app.kubernetes.io/name=api -o jsonpath='{.items[1].metadata.name}')

# Pod1 で書く
kubectl exec -n todo $POD1 -- sh -c "echo 'written by $POD1' > /uploads/test.txt"

# Pod2(別ノード)で読む
kubectl exec -n todo $POD2 -- cat /uploads/test.txt
# written by api-xxx-y1     ← 別ノードの別 Pod から見える!
```

これが NFS RWX の本領発揮シーンです。

## 13.11 ハンズオン Step 10: Frontend + Ingress

```yaml
# 07-frontend.yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: todo
spec:
  selector:
    app.kubernetes.io/name: frontend
  ports: [{ port: 80 }]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: todo
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: frontend
  template:
    metadata:
      labels:
        app.kubernetes.io/name: frontend
        app.kubernetes.io/part-of: todo
    spec:
      containers:
      - name: frontend
        image: 192.168.56.10:5000/todo-frontend:0.1.0
        ports: [{ containerPort: 80 }]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: todo
  namespace: todo
spec:
  ingressClassName: nginx
  rules:
  - host: todo.example.local
    http:
      paths:
      - { path: /,    pathType: Prefix, backend: { service: { name: frontend, port: { number: 80   } } } }
      - { path: /api, pathType: Prefix, backend: { service: { name: api,      port: { number: 8000 } } } }
```

```bash
kubectl apply -f 07-frontend.yaml

# クライアントの /etc/hosts に追加
sudo sh -c 'echo "192.168.56.10 todo.example.local" >> /etc/hosts'

curl http://todo.example.local/api/healthz
# {"status":"ok"}

curl http://todo.example.local/api/tasks
# [{"id":1,"title":"K8s ストレージ章を読み終える",...}]
```

## 13.12 ハンズオン Step 11: Worker CronJob

```yaml
# 08-worker-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: notify-due-soon
  namespace: todo
spec:
  schedule: "*/10 * * * *"
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            app.kubernetes.io/name: worker
            app.kubernetes.io/part-of: todo
        spec:
          restartPolicy: OnFailure
          containers:
          - name: worker
            image: 192.168.56.10:5000/todo-worker:0.1.0
            env:
            - name: DATABASE_URL
              value: postgresql://todo:changeme123@postgres.todo.svc:5432/todo
```

```bash
kubectl apply -f 08-worker-cronjob.yaml

# 手動で 1 回走らせて確認
kubectl create job --from=cronjob/notify-due-soon notify-now -n todo
kubectl logs -n todo -l job-name=notify-now
```

## 13.13 ハンズオン Step 12: 全体動作確認

```bash
kubectl get all,pvc -n todo

# 期待される状態
# NAME                          READY   STATUS    RESTARTS   AGE
# pod/api-xxx-y1                1/1     Running   0          5m
# pod/api-xxx-y2                1/1     Running   0          5m
# pod/frontend-xxx-z1           1/1     Running   0          4m
# pod/frontend-xxx-z2           1/1     Running   0          4m
# pod/postgres-0                1/1     Running   0          10m
# pod/redis-0                   1/1     Running   0          8m
#
# NAME                STATUS   VOLUME             CAPACITY   ACCESS MODES   STORAGECLASS
# data-postgres-0     Bound    pvc-...            5Gi        RWO            nfs-dynamic
# data-redis-0        Bound    pvc-...            1Gi        RWO            nfs-dynamic
# uploads             Bound    pv-todo-uploads    10Gi       RWX            ""
```

### NFS サーバ側のディレクトリツリーを見る

```bash
ssh k8s-nfs sudo tree -L 4 /srv/nfs/k8s/ 2>/dev/null || \
ssh k8s-nfs sudo find /srv/nfs/k8s -maxdepth 4 -type d
# /srv/nfs/k8s/
# ├── backup
# ├── dynamic
# │   ├── todo-data-postgres-0/pgdata
# │   └── todo-data-redis-0/appendonlydir
# └── static
#     └── uploads
#         └── test.txt
```

**すべてのアプリデータが NFS サーバ上に集中している** ことが視覚的に確認できます。これが本ハンズオンの最大の見どころです。

## 13.14 ハンズオン Step 13: バックアップ実行

第 11 部のスクリプトで全体バックアップを取ります。

```bash
ssh k8s-nfs sudo /usr/local/sbin/nfs-snap-backup.sh
ssh k8s-nfs ls -lh /srv/nfs-backup/
# -rw-r--r-- 1 root root  ... 20260509_1700.tar.gz

ssh k8s-nfs sudo tar tzf /srv/nfs-backup/20260509_1700.tar.gz | head -20
```

## 13.15 ハンズオン Step 14: 障害シミュレーション ─ NFS サーバ再起動

NFS サーバが落ちたら何が起きるかを目で見ます。

```bash
# Pod 内で書き込みループ
kubectl exec -n todo postgres-0 -- bash -c "
psql -U todo <<'SQL' &
DO \$\$ BEGIN
  FOR i IN 1..10000 LOOP
    INSERT INTO tasks (title) VALUES ('rec-' || i);
    PERFORM pg_sleep(0.5);
  END LOOP;
END \$\$;
SQL
echo \$!
"

# NFS サーバを再起動
ssh k8s-nfs sudo systemctl restart nfs-server

# postgres-0 の様子を観察
kubectl logs -n todo postgres-0 --tail=50 -f
```

**観察ポイント**:

- マウントオプション `hard` を使っているため、NFS サーバ復帰までクライアントは **永遠に待つ**(I/O はハングするがエラーにならない)
- サーバが復帰するとそのまま継続(数秒〜数十秒のハング後、再開)
- これが `soft` だったら `I/O error` でトランザクション失敗していた

これが `hard` マウントの利点(整合性確保)と欠点(I/O が止まる)のトレードオフです。

## 13.16 ハンズオン Step 15: スナップショット → 復元演習

```bash
# 1. 現在のデータを VolumeSnapshot で保存
cat <<'EOF' | kubectl apply -f -
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: pg-snap-baseline
  namespace: todo
spec:
  volumeSnapshotClassName: nfs-vsc
  source:
    persistentVolumeClaimName: data-postgres-0
EOF

kubectl wait --for=jsonpath='{.status.readyToUse}'=true \
  -n todo volumesnapshot/pg-snap-baseline --timeout=120s

# 2. 障害演出: 全タスクを削除
kubectl exec -n todo postgres-0 -- psql -U todo -c "DELETE FROM tasks;"
kubectl exec -n todo postgres-0 -- psql -U todo -c "SELECT count(*) FROM tasks;"
#  count
# -------
#      0

# 3. スナップショットから別 PVC を作る
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-postgres-restored
  namespace: todo
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: nfs-dynamic
  resources: { requests: { storage: 5Gi } }
  dataSource:
    name: pg-snap-baseline
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
EOF

# 4. 復元データを使う検証 Pod を立てる
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: pg-verify
  namespace: todo
spec:
  securityContext:
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
  containers:
  - name: pg
    image: postgres:16
    env:
    - name: POSTGRES_PASSWORD
      value: changeme123
    - name: PGDATA
      value: /var/lib/postgresql/data/pgdata
    volumeMounts:
    - { name: data, mountPath: /var/lib/postgresql/data }
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: data-postgres-restored
EOF

kubectl wait --for=condition=Ready pod pg-verify -n todo --timeout=120s

# 5. 復元側でデータを確認
kubectl exec -n todo pg-verify -- psql -U todo -c "SELECT count(*) FROM tasks;"
#  count
# -------
#      3    ← 削除前のデータが戻っている!
```

スナップショット → 復元のフルサイクルが NFS-CSI 経由で動作することを確認できました。

## 13.17 ハンズオン Step 16: ストレージ拡張(オンライン)

PostgreSQL の容量が足りなくなった想定で、PVC を 5 GiB → 10 GiB に拡張します。

```bash
# 拡張
kubectl patch pvc data-postgres-0 -n todo \
  -p '{"spec":{"resources":{"requests":{"storage":"10Gi"}}}}'

# 進捗確認
kubectl describe pvc -n todo data-postgres-0 | grep -A3 Conditions

# NFS-CSI はオンライン拡張対応なので Pod 再起動不要
kubectl get pvc -n todo data-postgres-0
# data-postgres-0   Bound   ...   10Gi   ...

# Pod 内から確認
kubectl exec -n todo postgres-0 -- df -h /var/lib/postgresql/data
```

NFS は **ボリュームサイズという概念をハードに持たない**(ディレクトリ容量制限は CSI の論理値)ため、リサイズはほぼ即時です。

## 13.18 ハンズオン Step 17: ノード障害シミュレーション

ワーカーノードが落ちたとき、StatefulSet の Pod が別ノードに移動できるかを確認します(NFS だからこそ可能なシナリオ)。

```bash
# postgres-0 がどのノードにいるか
kubectl get pod postgres-0 -n todo -o wide
# postgres-0  ...  k8s-w1

# k8s-w1 を強制シャットダウン
ssh k8s-w1 sudo shutdown -h now

# 5 分くらい待つ(node controller のタイムアウト)
watch kubectl get nodes
# k8s-w1   NotReady

watch kubectl get pod postgres-0 -n todo
# 最初は Running のまま(古い記録)→ Terminating → 再作成 → 別ノードで Running
```

```bash
# 別ノードに移ったことを確認
kubectl get pod postgres-0 -n todo -o wide
# postgres-0  ...  k8s-w2     ← 別ノードに移動

# データは健在
kubectl exec -n todo postgres-0 -- psql -U todo -c "SELECT count(*) FROM tasks;"
```

local PV だとこの移動は不可能で、ノード復旧待ちになります。NFS のような **ノード非依存ストレージ** の最大の価値です。

## 13.19 ハンズオン Step 18: クリーンアップ

```bash
# 全部削除
kubectl delete namespace todo
kubectl delete pv pv-todo-uploads

# 動的 PV は reclaimPolicy: Retain なので残る
kubectl get pv
# pvc-...   ...   Released

# 必要なら手動削除
kubectl delete pv -l app.kubernetes.io/part-of=todo

# NFS サーバ側のデータも掃除(本番では絶対しないが、学習環境なら OK)
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/dynamic/todo-*"
ssh k8s-nfs "sudo rm -rf /srv/nfs/k8s/static/uploads/*"
```

## 13.20 第 13 部のまとめ

このハンズオンで実証できたこと:

- TODO サービス全体(Frontend / API / DB / Cache / Worker / アップロード)を **NFS だけ** でフル稼働
- 動的プロビジョニング(PostgreSQL、Redis)と静的 PV(uploads RWX)の混在運用
- StatefulSet で `fsGroup` が機能し、NFS サーバ側でも UID/GID が正しい
- 別ノード上の API Pod が同じ uploads PVC(RWX)を共有
- NFS サーバ再起動時に `hard` マウントなら自動復旧
- VolumeSnapshot → 別 PVC への復元
- PVC オンライン拡張(Pod 再起動不要)
- ノード障害時の Pod 移動

これで NFS の「**実戦投入レベル**」の手応えが得られたはずです。

---

# 第 14 部: CSI Driver の歴史と nfs.csi.k8s.io アーキテクチャ深堀り

第 4 部では NFS-CSI ドライバを「使う」観点で扱いました。本パートでは **CSI そのものの歴史と内部設計** を、Kubernetes ストレージ進化の文脈で深堀りします。CSI を本当に理解するには、それ以前の **in-tree plugin と FlexVolume の歴史的経緯** を知る必要があります。

## 14.1 ストレージプラグインの 3 世代

```mermaid
timeline
    title Kubernetes ストレージプラグイン進化
    2014 : in-tree plugin<br>(Kubernetes 本体に組込)
    2016 : FlexVolume<br>(out-of-tree 実行ファイル)
    2018 : CSI 1.0 GA<br>(gRPC 標準化)
    2021 : CSI Migration 全面進行<br>(in-tree 廃止フェーズ)
    2024 : 主要 in-tree 完全削除<br>(AWS EBS, GCE PD, Azure Disk)
```

| 世代 | 形式 | 利点 | 欠点 |
|------|------|------|------|
| in-tree | K8s 本体に Go でコード組込 | 性能良、確実な動作 | K8s リリースサイクルに縛られる、サードパーティが寄与しづらい、攻撃面拡大 |
| FlexVolume | ノード上の実行ファイル(`/usr/libexec/kubernetes/kubelet-plugins/volume/exec/...`) | out-of-tree、言語自由 | デプロイ困難(ノードに直接バイナリ配置)、依存関係管理が手作業 |
| CSI | コンテナ化された gRPC サービス | 完全に out-of-tree、Kubernetes 非依存(他コンテナオーケストレータでも使える) | 設計が複雑、サイドカー多数 |

### 14.1.1 in-tree plugin の時代(2014〜)

Kubernetes v1.0 時代、すべてのストレージプラグインは **K8s 本体のソースコード** に直接書き込まれていました。`pkg/volume/aws_ebs/`、`pkg/volume/gce_pd/`、`pkg/volume/nfs/` などです。

```bash
# Kubernetes v1.18 のソース構造(参考)
ls staging/src/k8s.io/legacy-cloud-providers/...
ls pkg/volume/...
# aws_ebs/  azure_dd/  azure_file/  cephfs/  cinder/  configmap/  csi/
# downwardapi/  empty_dir/  fc/  flexvolume/  flocker/  gce_pd/  git_repo/
# glusterfs/  host_path/  iscsi/  local/  nfs/  photon_pd/  portworx/
# projected/  quobyte/  rbd/  scaleio/  secret/  storageos/  vsphere_volume/
```

**問題点**:

1. **リリース速度の縛り** ─ AWS EBS の新機能を入れたい場合でも、K8s のメジャーリリース(数ヶ月単位)を待つ必要があった
2. **コードベース肥大化** ─ 全クラウドベンダーのコードが K8s 本体に同居 → kube-apiserver や kubelet バイナリが肥大化
3. **依存関係の地獄** ─ AWS SDK と GCE SDK が同じバイナリに入る → ベンダーロックインや脆弱性連鎖
4. **テストカバレッジ** ─ K8s チームが全クラウドのテストを面倒見るのは無理
5. **サードパーティ参入障壁** ─ Pure Storage や NetApp が独自プラグインを入れるには K8s 本体への PR が必要

### 14.1.2 FlexVolume(2016)

これらの問題を解決する最初の試みが **FlexVolume** です。FlexVolume はノード上に **実行可能ファイル** を配置し、K8s がそれを呼び出す方式でした。

```mermaid
sequenceDiagram
    participant K as kubelet
    participant F as /usr/libexec/.../exec/vendor~driver/driver
    participant V as ストレージ(NFS等)
    K->>F: ./driver mount /mnt/pv-xxx '{"server":"..."}'
    F->>V: 実際のマウント
    F-->>K: {"status":"Success"}
```

**呼び出されるコマンド一覧**:

| サブコマンド | 役割 |
|------------|------|
| `init` | プラグイン初期化 |
| `attach` | ボリュームをノードに接続 |
| `detach` | ボリュームをノードから切離 |
| `mount` | マウント実行 |
| `unmount` | アンマウント実行 |
| `getvolumename` | ボリューム識別子取得 |

**問題点**:

1. **デプロイの困難** ─ 全ノードの `/usr/libexec/...` に手作業で配置する必要があった(Kubernetes 標準のマニフェストでは管理できない)
2. **依存ライブラリ問題** ─ 実行ファイルがノードの glibc やシェルに依存
3. **動的プロビジョニングが弱い** ─ 当初は静的 PV しか対応していなかった
4. **デバッグが困難** ─ プラグインのログをまとめて見る仕組みが弱い

NFS でも `kubernetes.io/nfs` という in-tree プラグインが長く使われた一方、FlexVolume 版の NFS は普及しませんでした。

### 14.1.3 CSI(Container Storage Interface, 2018 GA)

**CSI は CNCF が策定した、Kubernetes 専用ではない汎用ストレージインターフェース仕様** です。Kubernetes、Mesos、Cloud Foundry、Nomad など、複数のコンテナオーケストレータが共通で使えることを目標にしています。

```mermaid
flowchart LR
    subgraph K[Orchestrators]
        Kub[Kubernetes]
        Nom[Nomad]
        Mes[Mesos]
        CF[Cloud Foundry]
    end
    CSI[CSI 仕様<br>gRPC over UNIX socket]
    subgraph D[Drivers]
        EBS[aws-ebs-csi-driver]
        NFS[nfs.csi.k8s.io]
        Ceph[ceph-csi]
        Lon[longhorn-csi]
        Net[netapp-trident]
    end
    Kub & Nom & Mes & CF --> CSI --> EBS & NFS & Ceph & Lon & Net
```

**CSI の特徴**:

- **gRPC over UNIX domain socket** で通信
- **Identity / Controller / Node** の 3 サービスを定義
- ドライバは **完全にコンテナイメージ** として配布(K8s なら Deployment + DaemonSet)
- **標準サイドカー**(external-provisioner、external-attacher、external-resizer、external-snapshotter)が Kubernetes と CSI ドライバの橋渡し
- ドライバベンダーは **CSI 本体のロジック** だけ書けばよい(K8s API は標準サイドカーが面倒見る)

### 14.1.4 CSI Migration の進行

K8s v1.17 で **CSI Migration** という仕組みが alpha 登場しました。これは **「既存の in-tree PV / PVC マニフェストを、内部的に CSI 呼び出しに変換する」** 互換レイヤです。

```mermaid
flowchart TB
    A[既存 manifest<br>volume.kubernetes.io/aws-ebs] --> B[CSI Migration Shim]
    B -->|変換| C[ebs.csi.aws.com<br>CSI driver]
    C --> D[実際の EBS 操作]
```

これにより、ユーザは **manifest を書き換えずに** in-tree → CSI 移行ができました。各 in-tree プラグインの状況(v1.30 時点):

| in-tree プラグイン | CSI ドライバ | Migration GA | in-tree 廃止 |
|------------------|------------|--------------|--------------|
| `kubernetes.io/aws-ebs` | `ebs.csi.aws.com` | v1.25 | v1.27 で削除 |
| `kubernetes.io/gce-pd` | `pd.csi.storage.gke.io` | v1.25 | v1.28 で削除 |
| `kubernetes.io/azure-disk` | `disk.csi.azure.com` | v1.24 | v1.28 で削除 |
| `kubernetes.io/azure-file` | `file.csi.azure.com` | v1.26 | v1.30 で削除 |
| `kubernetes.io/cinder` | `cinder.csi.openstack.org` | v1.24 | v1.26 で削除 |
| `kubernetes.io/vsphere-volume` | `csi.vsphere.vmware.com` | v1.25 | v1.29 で削除 |
| **`kubernetes.io/nfs`** | **`nfs.csi.k8s.io`** | (Migration なし) | **v1.25 で削除** |

{: .important }
> **`kubernetes.io/nfs` in-tree プラグインは Kubernetes v1.25 で完全削除** されました。これは Migration shim も提供されない直接廃止です。古い manifest の `spec.nfs:` 直書きの PV は今でも動きますが、これは厳密には in-tree NFS ではなく、kubelet がカーネル NFS を直接マウントする **PV 内蔵の NFS マウンタ** であり、CSI ドライバを通りません。
>
> 動的プロビジョニング、VolumeSnapshot、PVC リサイズなどモダンな機能を使うには **`nfs.csi.k8s.io`** に統一する必要があります。本教材も `nfs.csi.k8s.io` 前提です。

### 14.1.5 PV `spec.nfs:` 直書きと CSI の使い分け

両者は共存できます。具体的にはこう使い分けます。

| 用途 | 方式 |
|------|------|
| 静的 PV のみ、シンプルさ重視 | `spec.nfs:` 直書き(本教材の uploads PV) |
| 動的プロビジョニング | StorageClass + `nfs.csi.k8s.io` |
| VolumeSnapshot を使いたい | `nfs.csi.k8s.io` 必須 |
| PVC オンラインリサイズ | `nfs.csi.k8s.io` 必須 |

`spec.nfs:` 直書きの PV では、CSI を介さずに **kubelet が直接 `mount.nfs` を呼ぶ** ため、CSI ドライバが落ちていても影響を受けません。一方、動的機能は使えません。

## 14.2 CSI 仕様の gRPC 定義

CSI 仕様は公式 protobuf 定義として公開されています([csi.proto](https://github.com/container-storage-interface/spec))。NFS-CSI を含む全 CSI ドライバはこの仕様に準拠します。

### 14.2.1 3 つの gRPC サービス

```protobuf
service Identity {
  rpc GetPluginInfo(...) returns (...) {}
  rpc GetPluginCapabilities(...) returns (...) {}
  rpc Probe(...) returns (...) {}
}

service Controller {
  rpc CreateVolume(...) returns (...) {}
  rpc DeleteVolume(...) returns (...) {}
  rpc ControllerPublishVolume(...) returns (...) {}    // attach
  rpc ControllerUnpublishVolume(...) returns (...) {}  // detach
  rpc ValidateVolumeCapabilities(...) returns (...) {}
  rpc ListVolumes(...) returns (...) {}
  rpc GetCapacity(...) returns (...) {}
  rpc ControllerGetCapabilities(...) returns (...) {}
  rpc CreateSnapshot(...) returns (...) {}
  rpc DeleteSnapshot(...) returns (...) {}
  rpc ListSnapshots(...) returns (...) {}
  rpc ControllerExpandVolume(...) returns (...) {}     // resize
  rpc ControllerGetVolume(...) returns (...) {}
  rpc ControllerModifyVolume(...) returns (...) {}     // 各種属性変更
}

service Node {
  rpc NodeStageVolume(...) returns (...) {}            // node-global mount
  rpc NodeUnstageVolume(...) returns (...) {}
  rpc NodePublishVolume(...) returns (...) {}          // pod-specific bind mount
  rpc NodeUnpublishVolume(...) returns (...) {}
  rpc NodeGetVolumeStats(...) returns (...) {}         // df / stats
  rpc NodeExpandVolume(...) returns (...) {}           // FS 拡張
  rpc NodeGetCapabilities(...) returns (...) {}
  rpc NodeGetInfo(...) returns (...) {}
}
```

各 RPC のうち、ドライバが **どれを実装するか** はドライバ次第で、`*GetCapabilities` で「自分が何をサポートしているか」を Kubernetes に申告します。

### 14.2.2 nfs.csi.k8s.io が実装している RPC

```bash
# CSI ドライバの Capabilities を確認
kubectl get csidriver nfs.csi.k8s.io -o yaml
```

NFS-CSI が実装している主な RPC:

| RPC | 実装 | 用途 |
|-----|------|------|
| `Identity.GetPluginInfo` | ✅ | `nfs.csi.k8s.io` + バージョン返却 |
| `Controller.CreateVolume` | ✅ | NFS サーバ上に PVC サブディレクトリ作成 |
| `Controller.DeleteVolume` | ✅ | サブディレクトリ削除(`reclaimPolicy: Delete` 時) |
| `Controller.ControllerPublishVolume` | ❌(非実装) | NFS は attach 不要 |
| `Controller.CreateSnapshot` | ✅ | サブディレクトリの rsync コピー |
| `Controller.ControllerExpandVolume` | ✅ | メタデータ更新のみ(NFS は容量管理弱い) |
| `Node.NodeStageVolume` | ⚠️ オプション | ノード単位の最初のマウント |
| `Node.NodePublishVolume` | ✅ | Pod 固有のバインドマウント |
| `Node.NodeExpandVolume` | ✅ | FS 拡張(NFS は実質 no-op) |
| `Node.NodeGetVolumeStats` | ✅ | `df` 情報 |

NFS の特殊事情として、`ControllerPublishVolume`(attach)が **存在しない** 点に注目してください。AWS EBS や iSCSI なら「ノードに LUN を接続」というステップがありますが、NFS は **クライアントから直接マウントできる** ので attach フェーズが不要です。これが CSIDriver CRD の `attachRequired: false` 設定に反映されます。

```bash
kubectl get csidriver nfs.csi.k8s.io -o jsonpath='{.spec.attachRequired}'
# false
```

### 14.2.3 NodeStageVolume と NodePublishVolume の 2 段階構造

CSI Node 系には **2 段階のマウント機構** があります。

```mermaid
flowchart LR
    A[NFS サーバ] --> B[ノードのグローバルマウントポイント<br>/var/lib/kubelet/plugins/.../globalmount]
    B --> C[Pod1 固有<br>/var/lib/kubelet/pods/uid1/volumes/.../mount]
    B --> D[Pod2 固有<br>/var/lib/kubelet/pods/uid2/volumes/.../mount]
```

| 段階 | RPC | 何が起きる |
|------|-----|----------|
| Stage | `NodeStageVolume` | ノードにグローバルマウント(複数 Pod で 1 回だけ) |
| Publish | `NodePublishVolume` | Pod 固有のディレクトリへバインドマウント |

これにより **同じ PVC を 1 ノード上の複数 Pod が共有** できるようになります。NFS の場合、Stage は実際の `mount.nfs`、Publish は **bind mount** です。

```bash
# 実際のマウント状況を確認
mount | grep -E '(nfs|kubelet)' | head -10
# 192.168.56.30:/srv/nfs/... on /var/lib/kubelet/plugins/.../globalmount type nfs4 (...)
# /var/lib/kubelet/plugins/.../globalmount on /var/lib/kubelet/pods/.../mount type none (bind,...)
```

## 14.3 nfs.csi.k8s.io の内部構造

nfs.csi.k8s.io ドライバ自体は **Go で書かれた小さな gRPC サーバ** です。GitHub: [kubernetes-csi/csi-driver-nfs](https://github.com/kubernetes-csi/csi-driver-nfs)。

### 14.3.1 Pod の中身

第 4.2 節でインストールした状態で、各 Pod の中身を見てみます。

```bash
# Controller Pod
kubectl get pod -n kube-system -l app=csi-nfs-controller -o yaml | grep -A2 'image:' | head -20
# image: registry.k8s.io/sig-storage/csi-provisioner:v5.0.1
# image: registry.k8s.io/sig-storage/csi-snapshotter:v8.0.1
# image: registry.k8s.io/sig-storage/csi-resizer:v1.11.1
# image: registry.k8s.io/sig-storage/livenessprobe:v2.13.1
# image: registry.k8s.io/sig-storage/nfsplugin:v4.7.0

# Node Pod(各ワーカーで)
kubectl get pod -n kube-system -l app=csi-nfs-node -o yaml | grep -A2 'image:' | head -10
# image: registry.k8s.io/sig-storage/livenessprobe:v2.13.1
# image: registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.11.1
# image: registry.k8s.io/sig-storage/nfsplugin:v4.7.0
```

`nfsplugin` が CSI 本体です。それ以外は **Kubernetes プロジェクトが提供する標準サイドカー** で、どの CSI ドライバでも同じものを使います。

### 14.3.2 標準サイドカーの役割詳説

```mermaid
flowchart TB
    subgraph CP[CSI Controller Pod]
        prov[csi-provisioner<br>PVC 監視]
        snap[csi-snapshotter<br>VolumeSnapshot 監視]
        res[csi-resizer<br>PVC リサイズ監視]
        nfs[nfsplugin 本体]
    end
    subgraph K[Kubernetes API]
        api[kube-apiserver]
    end
    prov <-->|watch| api
    snap <-->|watch| api
    res <-->|watch| api
    prov -.unix socket.-> nfs
    snap -.unix socket.-> nfs
    res -.unix socket.-> nfs
```

| サイドカー | 監視リソース | 呼び出す CSI RPC |
|-----------|------------|-----------------|
| `csi-provisioner` | PVC | `CreateVolume` / `DeleteVolume` |
| `csi-attacher` | VolumeAttachment | `ControllerPublishVolume` / `ControllerUnpublishVolume` |
| `csi-snapshotter` | VolumeSnapshot / VolumeSnapshotContent | `CreateSnapshot` / `DeleteSnapshot` |
| `csi-resizer` | PVC (resize) | `ControllerExpandVolume` |
| `node-driver-registrar` | (なし) | kubelet との連携(プラグイン登録) |
| `livenessprobe` | (なし) | ヘルスチェック用 HTTP サーバ |

NFS-CSI には `csi-attacher` が **入っていません**(`attachRequired: false` のため)。AWS EBS-CSI、Ceph RBD-CSI には入っています。

### 14.3.3 ハンズオン: CSI gRPC を直接観察する

CSI ドライバが本当に gRPC を話していることを確認します。

```bash
# Node Pod の中に入る
NODE_POD=$(kubectl get pod -n kube-system -l app=csi-nfs-node -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it -n kube-system $NODE_POD -c nfs -- sh

# UNIX ソケットの位置
ls -la /csi/
# srwxr-xr-x 1 root root 0 ... csi.sock

# grpcurl があれば直接呼べる(コンテナイメージには通常入っていない)
# 代わりに、CSI ドライバ自身のログでオペレーションを観察
exit

kubectl logs -n kube-system $NODE_POD -c nfs -f
# I0509 ... GRPC call: /csi.v1.Identity/GetPluginInfo
# I0509 ... GRPC call: /csi.v1.Node/NodeGetCapabilities
# I0509 ... GRPC call: /csi.v1.Node/NodePublishVolume
# I0509 ... NodePublishVolume called with request volumeId="..."
```

これで CSI が単なる抽象ではなく、**実在の gRPC サービス** であることが見えます。

### 14.3.4 ハンズオン: CSI ドライバのソースを読む

NFS-CSI ドライバの実装は驚くほどシンプルです。GitHub の `pkg/nfs/` ディレクトリに以下のファイルがあります。

| ファイル | 内容 |
|---------|------|
| `nfs.go` | ドライバエントリポイント |
| `controllerserver.go` | `CreateVolume` などの Controller RPC 実装 |
| `nodeserver.go` | `NodePublishVolume` などの Node RPC 実装 |
| `identityserver.go` | `GetPluginInfo` などの Identity RPC 実装 |
| `utils.go` | mount.nfs 呼び出しヘルパ |

`controllerserver.go` の `CreateVolume` 実装の中核(疑似コード):

```go
func (cs *ControllerServer) CreateVolume(ctx context.Context, req *csi.CreateVolumeRequest) (*csi.CreateVolumeResponse, error) {
    name := req.GetName()
    params := req.GetParameters()
    server := params["server"]
    share := params["share"]
    subDir := computeSubDir(params, req)

    // 一時マウント
    tmpDir := mountToTmpDir(server, share)

    // mkdir
    err := os.MkdirAll(filepath.Join(tmpDir, subDir), 0o777)

    // umount
    umount(tmpDir)

    return &csi.CreateVolumeResponse{
        Volume: &csi.Volume{
            VolumeId: fmt.Sprintf("%s#%s#%s", server, share, subDir),
            VolumeContext: params,
        },
    }, nil
}
```

つまり NFS-CSI の **`CreateVolume` は単に「NFS サーバ上に mkdir する」だけ** です。それくらいシンプルな実装で、Kubernetes の完全な動的プロビジョニング機能が手に入ります。

### 14.3.5 VolumeID のフォーマット

`CreateVolume` が返す `VolumeID` は NFS-CSI の場合 **`server#share#subDir`** という文字列です。

```bash
kubectl get pv pvc-abc123 -o jsonpath='{.spec.csi.volumeHandle}'
# 192.168.56.30#/srv/nfs/k8s/dynamic#todo-data-postgres-0
```

`#` 区切りで「サーバ #エクスポートパス #サブディレクトリ」が入っています。`NodePublishVolume` 時にこの ID をパースして実マウントが走ります。

## 14.4 CSIDriver / CSIStorageCapacity / VolumeAttachment CRD

CSI を支える Kubernetes 標準 CRD を見ていきます。

### CSIDriver

```yaml
apiVersion: storage.k8s.io/v1
kind: CSIDriver
metadata:
  name: nfs.csi.k8s.io
spec:
  attachRequired: false              # NFS は attach 不要
  podInfoOnMount: true               # Pod 情報をマウント時に渡す
  volumeLifecycleModes: [Persistent, Ephemeral]
  fsGroupPolicy: File                # fsGroup を kubelet が適用
```

| フィールド | 意味 |
|-----------|------|
| `attachRequired` | `ControllerPublishVolume`(attach)を呼ぶか |
| `podInfoOnMount` | Pod 名/Namespace を `VolumeContext` に入れる(subDir テンプレ変数で使う) |
| `volumeLifecycleModes` | PVC ベース or Generic Ephemeral ボリュームの両対応 |
| `fsGroupPolicy` | `fsGroup` をどう適用するか(`None`/`File`/`ReadWriteOnceWithFSType`) |

### VolumeAttachment(NFS では使われない)

```bash
kubectl get volumeattachment
# EBS や iSCSI なら表示される
# NFS では空
```

### CSIStorageCapacity(GA で v1.24)

CSI ドライバが「あといくら使えるか」をクラスタに報告する仕組み。NFS-CSI は実装しているドライバもありますが、デフォルトでは出ません。

## 14.5 CSI Migration の内部メカニズム(参考)

K8s が `volume.kubernetes.io/aws-ebs` の PV を見たとき、CSI Migration が有効なら以下が起きます。

```mermaid
sequenceDiagram
    participant K as kubelet
    participant M as Migration Shim<br>(pkg/volume/csimigration)
    participant Drv as ebs.csi.aws.com
    K->>K: PV を見る (spec.awsElasticBlockStore)
    K->>M: 互換変換要求
    M->>M: AWSElasticBlockStoreSource → CSIPersistentVolumeSource
    M-->>K: 変換後 PV (spec.csi)
    K->>Drv: gRPC 呼び出し
```

これにより、ユーザのマニフェストや PV/PVC オブジェクトは **一切書き換わらず** に、内部だけ CSI に切替えられます。

NFS には Migration がありません(v1.25 で完全削除)。古いマニフェストの `spec.nfs:` PV は **CSI を介さず kubelet が直接マウント** する形で今でも動きます。

## 14.6 CSI のトラブル時の切り分け

```mermaid
flowchart TB
    A[PV/PVC が動かない] --> B{どの Pod?}
    B --> C[csi-provisioner<br>= PVC 監視]
    B --> D[csi-snapshotter<br>= snapshot 監視]
    B --> E[csi-resizer<br>= resize 監視]
    B --> F[csi-nfs-node<br>= マウント実行]
    B --> G[nfsplugin 本体<br>= CSI gRPC]
    C --> CL[kubectl logs ... csi-provisioner]
    D --> DL[kubectl logs ... csi-snapshotter]
    E --> EL[kubectl logs ... csi-resizer]
    F --> FL[kubectl logs ... csi-nfs-node -c nfs]
    G --> GL[同上 = nfs コンテナ]
```

「PVC が Pending」 → `csi-provisioner` ログ、「Pod が ContainerCreating」 → `csi-nfs-node` ログ、「リサイズが進まない」 → `csi-resizer` ログ、と切り分けます。

## 14.7 第 14 部のまとめ

- ストレージプラグインは **in-tree → FlexVolume → CSI** と進化
- `kubernetes.io/nfs` in-tree は **v1.25 で完全削除**、現在は `nfs.csi.k8s.io` が標準
- CSI は Identity / Controller / Node の 3 gRPC サービス
- NFS-CSI は `attachRequired: false`(attach フェーズなし)
- 標準サイドカー(provisioner、snapshotter、resizer)が Kubernetes と CSI ドライバを橋渡し
- NFS-CSI の `CreateVolume` は実質「NFS 上に mkdir するだけ」というシンプルな実装

---

# 第 15 部: セキュリティ深堀り(production-grade)

第 7 部では NFS のセキュリティ基本を扱いましたが、本番投入には **多層防御** の発想が必要です。本パートでは production-grade のセキュリティ設計を段階的に組み立てます。

## 15.1 攻撃面の整理

```mermaid
flowchart TB
    A[NFS の攻撃面] --> B[ネットワーク層]
    A --> C[認証層]
    A --> D[認可層]
    A --> E[データ保護]
    A --> F[Kubernetes 統合面]
    B --> B1[NFS サーバへの<br>不正接続]
    B --> B2[平文通信の<br>盗聴]
    B --> B3[サブネット<br>越境]
    C --> C1[sec=sys の脆弱性<br>= UID 詐称]
    C --> C2[ホスト指定<br>spoofing]
    D --> D1[root_squash<br>突破]
    D --> D2[squash 設定不備]
    E --> E1[at-rest 暗号化なし]
    E --> E2[バックアップ<br>無保護]
    F --> F1[Pod の権限昇格]
    F --> F2[hostPath 経由]
    F --> F3[psp/PSA バイパス]
```

各層に対する対策を、**production レベル** で見ていきます。

## 15.2 ネットワーク層: NetworkPolicy + Calico GlobalNetworkPolicy

第 7.3 節で NetworkPolicy の基本を扱いました。本番ではこれに **クラスタ外側の制御** を組み合わせます。

### 15.2.1 多層 NetworkPolicy 設計

```mermaid
flowchart TB
    subgraph L1[Layer 1: クラスタ外側]
        FW[VLAN / Firewall<br>192.168.56.0/24 のみ NFS 到達可]
    end
    subgraph L2[Layer 2: クラスタ Ingress]
        CNP[Calico GlobalNetworkPolicy<br>すべてのノード]
    end
    subgraph L3[Layer 3: Namespace 境界]
        NP1[NetworkPolicy<br>todo Namespace のみ NFS へ Egress 可]
    end
    subgraph L4[Layer 4: Pod 単位]
        NP2[NetworkPolicy<br>必要な Pod だけ]
    end
    FW --> CNP --> NP1 --> NP2
```

### 15.2.2 ハンズオン: Calico GlobalNetworkPolicy

Calico CNI を使っている前提です(本教材は Calico)。`GlobalNetworkPolicy` はクラスタ全体に適用される NetworkPolicy です。

```yaml
apiVersion: projectcalico.org/v3
kind: GlobalNetworkPolicy
metadata:
  name: allow-nfs-egress-only-from-allowed
spec:
  selector: "k8s-app != ''"   # すべての Pod
  types: [Egress]
  egress:
  # NFS サーバへの 2049/tcp は許可
  - action: Allow
    protocol: TCP
    destination:
      nets: [192.168.56.30/32]
      ports: [2049]
  # それ以外の 192.168.56.30 への通信は禁止
  - action: Deny
    destination:
      nets: [192.168.56.30/32]
  # 残りは通常通過(クラスタ内通信)
  - action: Pass
```

```bash
kubectl apply -f gnp-nfs.yaml
# 効果確認: 例えば nfs-server の 22/SSH への接続が遮断される
```

これにより、**Pod から NFS サーバへの SSH を試みても遮断される** などの防御が効きます。

### 15.2.3 NFS サーバ側のホストファイアウォール再確認

```bash
ssh k8s-nfs sudo ufw status verbose
# To                         Action      From
# 22/tcp                     ALLOW IN    192.168.56.0/24
# 2049/tcp                   ALLOW IN    192.168.56.0/24
# (default: deny incoming, allow outgoing)
```

**「クラスタ外のサブネットからは絶対に NFS が見えない」** ことを保証するレイヤです。

## 15.3 認証層: sec=sys の限界と Kerberos(sec=krb5)

### 15.3.1 sec=sys の脆弱性デモ

`sec=sys` は **クライアントが申告する UID/GID をそのまま信用** します。つまりクライアントが嘘をついたら通ってしまいます。

```bash
# 攻撃のシナリオ
# 攻撃者がクライアントノードで root を取った場合
sudo -u "#0" cat /export/secret-file
# UID 0 (root) として読みに行く → no_root_squash なら成功

# UID 1000 のフリをすることもできる
sudo -u "#1000" cat /export/user1000-file
# UID 1000 として読みに行く → 通る
```

つまり、**「ノードのカーネル/OS を信頼している前提」** が `sec=sys` のセキュリティモデルです。マルチテナント環境や信頼できないノードを含む場合は **Kerberos** が必須になります。

### 15.3.2 Kerberos(sec=krb5)の三段階

| モード | 認証 | 完全性 | 暗号化 |
|--------|------|--------|--------|
| `sec=krb5` | ✅ チケットで認証 | ❌ | ❌ |
| `sec=krb5i` | ✅ | ✅ チェックサム | ❌ |
| `sec=krb5p` | ✅ | ✅ | ✅ AES |

### 15.3.3 ハンズオン: Kerberos NFS の概略構築

Kerberos の完全構築は本教材のスコープを超えますが、概略を示します。

```bash
# KDC(認証サーバ)のセットアップ
sudo apt install -y krb5-kdc krb5-admin-server

# realm 作成
sudo kdb5_util create -s -r K8S.LOCAL

# KDC 起動
sudo systemctl start krb5-kdc krb5-admin-server

# NFS サーバ用 principal を作る
sudo kadmin.local -q "addprinc -randkey nfs/k8s-nfs.k8s.local"
sudo kadmin.local -q "ktadd -k /etc/krb5.keytab nfs/k8s-nfs.k8s.local"

# /etc/exports を Kerberos 化
echo "/srv/nfs/k8s/static gss/krb5p(rw,sync,no_subtree_check)" \
  | sudo tee /etc/exports
sudo exportfs -ra

# クライアント側で kinit してマウント
sudo kinit user@K8S.LOCAL
sudo mount -t nfs4 -o sec=krb5p k8s-nfs:/srv/nfs/k8s/static /mnt/nfs
```

Kubernetes Pod が Kerberos NFS を使う場合、**Pod 内に Kerberos チケット** を渡す必要があります(`gMSA` ConfigMap、自前 init container での `kinit` など)。マネージドサービスでは「AD 認証 NFS」として簡単化されているケースが多いです。

### 15.3.4 Kerberos NFS の現実的な採用判断

```mermaid
flowchart TB
    A[Kerberos NFS が必要?] --> B{マルチテナント?}
    B -- Yes --> C{コンプラ要件?}
    B -- No --> D[sec=sys でよい]
    C -- HIPAA/PCI 等 --> E[必須]
    C -- なし --> F{ネットワーク信頼?}
    F -- できる --> D
    F -- できない --> G[Kerberos + IPSec 検討]
```

実運用では「Kerberos NFS は **採用判断が重い**」のが現実で、多くのチームは:

1. **クラスタネットワークを物理的に分離**(VPN / VLAN)
2. **NFS サーバ自体への接続を絞る**(NetworkPolicy + ufw)
3. **sec=sys で運用**

という選択をしています。

## 15.4 認可層: 細粒度の権限制御

### 15.4.1 NFSv4 ACL

NFSv4 は POSIX 標準を超える ACL をサポートします。サーバ側のファイルシステムが対応していれば、`nfs4_setfacl` で設定できます。

```bash
sudo apt install -y nfs4-acl-tools

# /srv/nfs/k8s/static/private に対して、特定 UID のみアクセス許可
sudo nfs4_setfacl -a "A::1000:rwx" /srv/nfs/k8s/static/private
sudo nfs4_setfacl -a "A:g:devs@k8s.local:rx" /srv/nfs/k8s/static/private
sudo nfs4_getfacl /srv/nfs/k8s/static/private
# A::1000:rwatTnNcCy
# A:g:devs@k8s.local:rxtncy
```

ただし Pod の UID が動的に変わると ACL マッチが破綻するので、Kubernetes 環境では **使うとしてもごく限定的** です。

### 15.4.2 root_squash + anonuid/anongid の積極利用

`root_squash` を `anonuid=999` のような **特定アプリ用 UID** にマップする使い方があります。

```bash
sudo tee -a /etc/exports <<'EOF'
/srv/nfs/k8s/postgres  192.168.56.0/24(rw,sync,no_subtree_check,all_squash,anonuid=999,anongid=999,fsid=50)
EOF
sudo exportfs -ra
```

**`all_squash + anonuid=999`** とすると、Pod 内のどんな UID も **NFS サーバ側では UID 999** として書き込まれます。「Pod の UID 設定ミスでもデータの所有者が乱れない」という保険になります。

### 15.4.3 ハンズオン: 「データベース専用」exports の分離

PostgreSQL のデータは特別に扱う設計を作ります。

```bash
# サーバ側
sudo mkdir -p /srv/nfs/k8s/dbprivate
sudo chown 999:999 /srv/nfs/k8s/dbprivate
sudo chmod 0700 /srv/nfs/k8s/dbprivate

# /etc/exports に追加
sudo tee -a /etc/exports <<'EOF'
/srv/nfs/k8s/dbprivate  192.168.56.0/24(rw,sync,no_subtree_check,all_squash,anonuid=999,anongid=999,fsid=60)
EOF
sudo exportfs -ra
```

PostgreSQL 専用 StorageClass を別途作ります:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-db-private
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /srv/nfs/k8s/dbprivate
  subDir: ${pvc.metadata.namespace}-${pvc.metadata.name}
mountOptions: [nfsvers=4.1, hard, noatime, nconnect=4]
reclaimPolicy: Retain
allowVolumeExpansion: true
```

これで:

- DB データは別 export 経由(他のワークロードと完全分離)
- `all_squash + anonuid=999` で UID は強制的に 999 に固定
- StorageClass で **DB 用 Pod だけが** この領域を使える

## 15.5 データ保護: at-rest 暗号化

### 15.5.1 NFS データの at-rest 暗号化選択肢

| 層 | 手段 | 利点 | 欠点 |
|----|------|------|------|
| ディスク | LUKS(`dm-crypt`) | ボリューム単位、透過 | 鍵管理必要 |
| ファイルシステム | eCryptfs / fscrypt | 個別ディレクトリ | パフォーマンス低下 |
| 集中型 | ZFS native encryption | スナップショットと統合 | ZFS 採用必須 |
| アプリ | PostgreSQL pgcrypto、`pg_data_at_rest` | 細粒度 | アプリ修正 |

### 15.5.2 ハンズオン: LUKS で NFS データボリュームを暗号化

第 2 部で構築した LVM 構成を、LUKS で暗号化し直します(注意: 既存データを消す手順です)。

```bash
# k8s-nfs で(既存データのバックアップ後に実施)
sudo umount /srv/nfs
sudo lvremove /dev/nfs_vg/nfs_lv

# LUKS で暗号化
sudo cryptsetup luksFormat /dev/nfs_vg/nfs_lv
# Are you sure? Type 'YES'
# Enter passphrase: <強いパスフレーズ>

# 開く
sudo cryptsetup luksOpen /dev/nfs_vg/nfs_lv nfs_crypt
# 仮想デバイス /dev/mapper/nfs_crypt が出現

# ファイルシステム作成
sudo mkfs.ext4 -L nfs_data /dev/mapper/nfs_crypt
sudo mount /dev/mapper/nfs_crypt /srv/nfs
sudo mkdir -p /srv/nfs/k8s/{static,dynamic,backup}
```

ブート時に自動オープンするには `/etc/crypttab`:

```
# /etc/crypttab
nfs_crypt  /dev/nfs_vg/nfs_lv  none  luks
```

これだとブート時にパスフレーズ入力が必要。本番では **鍵をリモート KMS から取得** する仕組み(Vault Transit、Tang、Clevis)を組み合わせます。

### 15.5.3 暗号化のパフォーマンス影響

- ext4 + AES-XTS で **概ね 5〜15% の性能低下**
- AES-NI 対応 CPU なら影響小
- ベンチマーク必須(第 9 部の fio で実測)

## 15.6 in-transit 暗号化: NFS over TLS / IPSec

### 15.6.1 NFS over TLS(RFC 9289, 2022)

NFSv4.2 で **NFS over TLS(NFS-RFC4)** が標準化されました。Linux カーネル 6.5+ で利用可能。

```bash
# サーバ側
sudo tee -a /etc/nfs.conf <<'EOF'
[nfsd]
xprtsec=mtls
EOF

# クライアント側マウント
sudo mount -t nfs4 -o sec=sys,xprtsec=mtls server:/share /mnt
```

エンタープライズ Linux(RHEL 9.4+、Ubuntu 24.04+)以外ではまだ採用しにくい状況ですが、今後の標準になります。

### 15.6.2 IPSec(過去の主流)

カーネル IPSec(strongSwan、Libreswan)で IP 層暗号化を行い、NFS 通信を保護する方式。実装は複雑ですが、NFS over TLS が普及するまでの「現実解」として広く使われてきました。

```bash
sudo apt install -y strongswan
# /etc/ipsec.conf に NFS サーバとの ESP を設定
```

VPN(WireGuard、OpenVPN)で代用するパターンもあります。

### 15.6.3 SSH トンネル(緊急時)

緊急対応として、SSH ポートフォワードで NFS を通すことが原理上可能です(本番では非推奨)。

```bash
ssh -L 2049:nfs-server:2049 jump-host
sudo mount -t nfs4 localhost:/share /mnt
```

## 15.7 Kubernetes 統合面の硬化

### 15.7.1 Pod Security Admission(PSA)

第 7.5 節で扱いましたが、本番では **`restricted` プロファイル** を強制します。

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: todo
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

`restricted` 下では:

- `hostPath` 禁止 → 「NFS サーバを Pod 内で勝手にマウント」が阻止される
- `runAsNonRoot: true` 強制
- `allowPrivilegeEscalation: false` 強制
- `seccompProfile` 必須

NFS-CSI ドライバの Pod 自体は `restricted` を満たさない(特権が必要)ので、ドライバ用 Namespace は別途 `privileged` プロファイルで運用します。

### 15.7.2 Kyverno / OPA Gatekeeper による Policy

```yaml
# Kyverno で「特定 Namespace では nfs-dynamic SC しか使わせない」
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: enforce-nfs-only
spec:
  validationFailureAction: enforce
  rules:
  - name: only-nfs-dynamic
    match:
      any:
      - resources:
          kinds: [PersistentVolumeClaim]
          namespaces: [todo, staging]
    validate:
      message: "todo namespace must use nfs-dynamic StorageClass"
      pattern:
        spec:
          storageClassName: nfs-dynamic
```

### 15.7.3 ServiceAccount と RBAC

CSI スナップショットや手動 PV 操作を行う ServiceAccount は最小権限に絞ります。

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: snapshot-creator
  namespace: todo
rules:
- apiGroups: [snapshot.storage.k8s.io]
  resources: [volumesnapshots]
  verbs: [create, get, list]
```

### 15.7.4 NFS マウントオプションでの硬化

```yaml
mountOptions:
- nfsvers=4.1
- hard
- nosuid                  # setuid を禁止
- nodev                   # デバイスファイル禁止
- noexec                  # 実行ファイルとして使えなくする(uploads など)
- noatime
```

`noexec` をアップロード領域に入れておくと、アップロードされたバイナリが Pod 内で実行されるリスクをサーバ側から遮断できます。

## 15.8 監査ログとモニタリング

### 15.8.1 NFS サーバ側監査

```bash
# auditd で /srv/nfs を監視
sudo apt install -y auditd
sudo tee -a /etc/audit/rules.d/nfs.rules <<'EOF'
-w /srv/nfs -p wa -k nfs_data
-w /etc/exports -p wa -k nfs_config
-w /etc/nfs.conf -p wa -k nfs_config
EOF
sudo systemctl restart auditd

# 監査ログを見る
sudo ausearch -k nfs_data | head
sudo ausearch -k nfs_config
```

### 15.8.2 Prometheus アラート例

```yaml
# 急激な NFS 接続増加(攻撃の兆候)
- alert: NFSConnectionsSpike
  expr: rate(node_nfsd_connections_total[5m]) > 100
  for: 5m
  
# root_squash 違反の可能性
- alert: NFSUnauthorizedAccess
  expr: rate(nfs_audit_unauth_total[5m]) > 0
```

## 15.9 本番セキュリティチェックリスト

```mermaid
flowchart LR
    L1[ネットワーク] --> L2[認証] --> L3[認可] --> L4[データ] --> L5[K8s 統合] --> L6[監査]
```

- [ ] NFS サーバはクラスタ外サブネットから到達不可
- [ ] ufw / firewalld でクラスタ CIDR のみ 2049 許可
- [ ] NetworkPolicy で Pod から NFS への egress を制限
- [ ] Calico GlobalNetworkPolicy で全 Pod 共通の制約を入れる
- [ ] `sec=sys` の限界を理解し、必要なら Kerberos / VPN を導入
- [ ] `root_squash` を本番では絶対に有効化
- [ ] `all_squash + anonuid=999` を機密データに使う
- [ ] LUKS / fscrypt / ZFS encryption で at-rest 暗号化
- [ ] NFS over TLS(対応 OS なら)or IPSec で in-transit 暗号化
- [ ] Namespace に PSA `restricted` を貼る
- [ ] Kyverno / OPA で StorageClass 利用を制約
- [ ] `nosuid,nodev,noexec` をマウントオプションに
- [ ] auditd で `/srv/nfs` と `/etc/exports` の変更を監視
- [ ] Prometheus で NFS 接続/エラーを監視
- [ ] バックアップ自体も暗号化(restic、gocryptfs)

## 15.10 第 15 部のまとめ

- 多層防御(ネットワーク・認証・認可・データ・K8s 統合)で攻撃面を縮小
- `sec=sys` には UID 詐称の限界がある、本気のマルチテナントなら Kerberos
- `all_squash + anonuid` は「Pod の UID 設定ミスでも所有者が乱れない」保険
- LUKS による at-rest 暗号化が現実的選択
- NFS over TLS が今後標準になる(現状は OS バージョン制約あり)
- PSA `restricted` + Kyverno で K8s 側の硬化
- auditd と Prometheus で監視可視化

---

# 第 16 部: Production HA 設計

第 10 部で HA NFS の構築技術を扱いました。本パートでは **production 投入を前提に、SLO を満たす HA 設計** を体系的に組み立てます。

## 16.1 SLO 駆動の設計

HA 設計は **「何を、どのレベルで保証するか」** から始まります。

```mermaid
flowchart TB
    A[SLO 定義] --> B[Availability<br>99.9% / 99.99% ?]
    A --> C[RPO<br>許容データ損失]
    A --> D[RTO<br>復旧時間]
    A --> E[性能<br>p99 latency]
    B --> F[実装選択]
    C --> F
    D --> F
    E --> F
```

| SLO 指標 | 例 | 意味 |
|---------|-----|------|
| **Availability** | 99.9%(月 43 分以下のダウン) | サービス稼働率 |
| **RPO**(Recovery Point Objective) | 5 分 | 最新何分までのデータが守られるか |
| **RTO**(Recovery Time Objective) | 15 分 | 障害発生から復旧までの時間 |
| **Latency p99** | 10ms | 99 パーセンタイル応答時間 |

### 16.1.1 SLO から構成を逆算する

```mermaid
flowchart LR
    A[99.9% Avail<br>RPO 1h<br>RTO 1h] --> B[単一 NFS<br>+ 毎時 rsync]
    C[99.95% Avail<br>RPO 5min<br>RTO 15min] --> D[Pacemaker DRBD HA<br>+ VolumeSnapshot 5min]
    E[99.99% Avail<br>RPO 30s<br>RTO 1min] --> F[商用アプライアンス<br>or マネージド]
    G[99.999% Avail<br>RPO ≒0<br>RTO 30s] --> H[アクティブ-アクティブ<br>分散ストレージ + 多重化]
```

「**99.99% を達成するのに自前で組むより、AWS EFS / Azure NetApp Files を買うほうが安い**」という結論になる場合が多いのが現実です。

## 16.2 障害モードと対策マッピング

### 16.2.1 ありえる障害の網羅

```mermaid
flowchart TB
    A[障害シナリオ] --> B[ハードウェア]
    A --> C[ソフトウェア]
    A --> D[人為的]
    A --> E[セキュリティ]
    A --> F[環境]
    B --> B1[ディスク故障]
    B --> B2[NIC 故障]
    B --> B3[電源故障]
    B --> B4[サーバ全死]
    C --> C1[OS カーネル panic]
    C --> C2[ファイルシステム破損]
    C --> C3[NFS デーモン暴走]
    D --> D1[誤削除]
    D --> D2[設定ミス]
    D --> D3[マイグレーション事故]
    E --> E1[ランサムウェア]
    E --> E2[内部犯行]
    F --> F1[データセンタ災害]
    F --> F2[電力喪失]
    F --> F3[ネットワーク分断]
```

### 16.2.2 対策マッピング

| 障害 | 対策 |
|------|------|
| ディスク故障 | RAID(または ZFS RAID-Z)、SMART モニタリング |
| NIC 故障 | NIC bonding(active-backup、LACP) |
| 電源故障 | デュアル PSU、UPS |
| サーバ全死 | Pacemaker + DRBD、または分散ストレージ |
| OS panic | watchdog、自動再起動 |
| FS 破損 | バックアップ、ジャーナル FS(ext4/XFS) |
| NFS デーモン暴走 | systemd Restart=always、メモリ制限 |
| 誤削除 | Snapshot(時間軸冗長化) |
| 設定ミス | GitOps、change review、Pre-prod での検証 |
| ランサムウェア | Immutable backup(WORM、Object Lock) |
| データセンタ災害 | リモートサイトレプリカ(rsync over WAN、ZFS send) |
| 電力喪失 | UPS、複数電源系統 |
| NW 分断 | Pacemaker の split-brain 対策(STONITH) |

## 16.3 production 構成パターン

### 16.3.1 パターン A: 単一 NFS + 多層バックアップ(SMB 中規模向け)

```mermaid
flowchart TB
    subgraph DC1[Primary DC]
        NFS1[NFS Server<br>RAID-6<br>NIC bonding]
        BAK1[Local Backup<br>rsnapshot]
    end
    subgraph DC2[Secondary site]
        BAK2[Remote Backup<br>rsync nightly]
        S3[(Object Storage<br>WORM)]
    end
    NFS1 --> BAK1 --> BAK2 --> S3
```

| 観点 | 設計 |
|------|------|
| Availability | 99.5% 程度(年 1〜2 日のダウンを許容) |
| RPO | 24 時間 |
| RTO | 数時間〜半日 |
| 実装 | 第 2 部 + 第 11 部の構成 |
| 適合 | 小規模ビジネス、社内ツール |

### 16.3.2 パターン B: Pacemaker + DRBD アクティブ-パッシブ HA(中規模本番)

```mermaid
flowchart TB
    Cli[Clients] --> VIP[VIP 192.168.56.45]
    VIP --> NFS1[NFS-HA1<br>Primary]
    NFS1 <==DRBD 同期==> NFS2[NFS-HA2<br>Standby]
    NFS1 -.snapshot.-> S3[(Object Storage)]
```

| 観点 | 設計 |
|------|------|
| Availability | 99.9% |
| RPO | 数秒(DRBD 同期) |
| RTO | 30 秒〜2 分(Pacemaker フェイルオーバ) |
| 実装 | 第 10 部 + 第 15 部 + 監視 + 自動運用 |
| 適合 | 中規模本番、エンタープライズ社内 |

実装ポイント:

- DRBD は **必ず Protocol C(同期)**
- Pacemaker の **STONITH 必須**(本番では fencing なしの 2 ノード HA は地雷)
- ネットワーク二重化(DRBD 専用 NIC + サービス NIC)
- 監視: `pcs status`、DRBD 同期遅延、VIP 状態

### 16.3.3 パターン C: 分散ストレージ + NFS-Ganesha(大規模)

```mermaid
flowchart TB
    Cli[Clients] --> LB[Load Balancer]
    LB --> G1[Ganesha-1] & G2[Ganesha-2] & G3[Ganesha-3]
    G1 & G2 & G3 --> Ceph[CephFS Cluster<br>3+ OSD ノード]
```

| 観点 | 設計 |
|------|------|
| Availability | 99.95%+ |
| RPO | ≒ 0(同期分散書き込み) |
| RTO | 数秒〜数十秒 |
| 実装 | Rook-Ceph + nfs-ganesha |
| 適合 | 大規模、複数アプリ同居 |

### 16.3.4 パターン D: マネージドサービス(クラウドネイティブ)

```mermaid
flowchart TB
    K8s[EKS / AKS / GKE] --> CSI[CSI Driver]
    CSI --> EFS[(AWS EFS<br>Multi-AZ)]
    CSI --> ANF[(Azure NetApp Files)]
    CSI --> FS[(GCP Filestore Enterprise)]
```

| 観点 | 設計 |
|------|------|
| Availability | 99.99%(SLA) |
| RPO | ≒ 0 |
| RTO | ≒ 0(常時 HA) |
| 実装 | CSI ドライバを使うだけ |
| 適合 | クラウドネイティブ全般、リソース最小化 |

## 16.4 多重化ポイントの完全カバー

production HA では **「単一障害点を 1 つも残さない」** ことが目標です。NFS で見落としがちなポイント:

```mermaid
flowchart TB
    A[多重化ポイント] --> B[電源]
    A --> C[ネットワーク]
    A --> D[ストレージ]
    A --> E[ノード]
    A --> F[サイト]
    B --> B1[2 系統電源<br>UPS]
    C --> C1[NIC bonding]
    C --> C2[L2 スイッチ冗長]
    C --> C3[L3 ルータ冗長]
    D --> D1[RAID 6 / Z2]
    D --> D2[Hot spare]
    E --> E1[2+ ノード HA]
    F --> F1[Cross-DC レプリカ]
```

### 16.4.1 ハンズオン: NIC Bonding(active-backup)

```bash
# Ubuntu 22.04 で netplan の場合
sudo tee /etc/netplan/00-bond.yaml <<'EOF'
network:
  version: 2
  ethernets:
    enp0s8: { dhcp4: no }
    enp0s9: { dhcp4: no }
  bonds:
    bond0:
      interfaces: [enp0s8, enp0s9]
      addresses: [192.168.56.30/24]
      parameters:
        mode: active-backup
        primary: enp0s8
        mii-monitor-interval: 100
EOF

sudo netplan apply

# 確認
cat /proc/net/bonding/bond0
# Bonding Mode: fault-tolerance (active-backup)
# Primary Slave: enp0s8 (primary_reselect always)
# Currently Active Slave: enp0s8
# MII Status: up
# Slave Interface: enp0s8 / enp0s9
```

### 16.4.2 ハンズオン: ZFS RAID-Z2 でディスク冗長

ext4 + LVM では RAID は別途必要ですが、ZFS なら 1 つでカバーできます。

```bash
# 4 ディスク構成での RAID-Z2(2 ディスク故障まで耐性)
sudo zpool create nfs-pool raidz2 /dev/sdb /dev/sdc /dev/sdd /dev/sde
sudo zfs create nfs-pool/k8s

# 状態
sudo zpool status
#   pool: nfs-pool
#  state: ONLINE
# config:
#   NAME        STATE     READ WRITE CKSUM
#   nfs-pool    ONLINE       0     0     0
#     raidz2-0  ONLINE       0     0     0
#       sdb     ONLINE
#       sdc     ONLINE
#       sdd     ONLINE
#       sde     ONLINE
```

ディスクを抜いて挙動を確認できます(production では Hot spare も追加)。

## 16.5 STONITH の重要性

2 ノード HA で **split-brain** が起こると、両ノードが「自分が Primary」と思ってデータが分岐します。これを防ぐのが **STONITH(Shoot The Other Node In The Head)** です。

```mermaid
flowchart TB
    A[ネットワーク分断] --> B{お互いの<br>到達性ロス}
    B --> C[両ノードとも<br>「相手は死んだ」と判定]
    C --> D[両方が Primary に]
    D --> E[Split-brain<br>= データ分岐]
    E --> F[復旧時に<br>致命的データロス]
    G[STONITH 有効] -.防ぐ.-> E
```

### 16.5.1 STONITH の実装例

| 方式 | 仕組み | 環境 |
|------|--------|------|
| IPMI / iLO / iDRAC | リモート電源管理で相手をシャットダウン | 物理サーバ |
| 仮想化プラットフォーム | VMware vSphere の API で VM 停止 | VM 環境 |
| クラウド | AWS EC2 API で stop-instances | クラウド |
| PDU 制御 | スマート PDU で電源カット | データセンタ |
| SBD(Storage-Based Death) | 共有ディスクのトークン書込で死亡通知 | DRBD/共有 SAN |

### 16.5.2 ハンズオン: SBD-STONITH(参考)

```bash
sudo apt install -y sbd

# 共有ブロックデバイス(本ハンズオンでは追加した /dev/sdc)を SBD 用に
sudo sbd -d /dev/sdc create
sudo sbd -d /dev/sdc list

# Pacemaker に STONITH リソース追加
sudo pcs stonith create sbd-fence external/sbd \
  pcmk_host_list="nfs-ha1 nfs-ha2"

sudo pcs property set stonith-enabled=true
```

**本番 2 ノード HA では STONITH なしは厳禁** です。「学習目的だから無効化」は OK ですが、production では必ず有効化してください。

## 16.6 障害復旧プレイブック

production では「**手順書がないと夜中の障害で詰む**」のが現実です。最低限以下のプレイブックを用意します。

### プレイブック例: NFS サーバ全死

```markdown
# プレイブック: NFS Primary 全死

## 兆候
- Pacemaker `pcs status` で nfs-ha1 が UNCLEAN
- VIP がどちらにも乗っていない / Secondary に乗っている
- クライアント側で I/O ハング

## エスカレーション
- L1 サポート → L2 SRE(15分以内)→ DBA → CTO

## 復旧手順
1. `ssh nfs-ha2 sudo pcs status` で Secondary 状態確認
2. Secondary が UP なら自動 failover を待つ(通常 30 秒)
3. 自動 failover しない場合、`sudo pcs resource move vip_nfs nfs-ha2`
4. クライアント側で I/O 再開確認
5. nfs-ha1 の根本原因調査(iDRAC、コンソールログ、bootstrap)
6. nfs-ha1 復旧後、`sudo pcs cluster start nfs-ha1`
7. DRBD 同期完了を待つ(`drbdadm status`)
8. failback は計画停止時間に実施(`pcs resource move vip_nfs nfs-ha1`)
9. ポストモーテム作成

## バックアウト
- 自動 failover が機能しない & 緊急の場合
  - クライアント側で手動マウント切替(VIP 直 → Secondary IP)
- DRBD split-brain 発生時
  - 1. どちらを採用するか判断(タイムスタンプ、業務影響度)
  - 2. 棄却側で `drbdadm secondary && drbdadm invalidate`
  - 3. 採用側を `drbdadm primary --force`
  - 4. 同期完了まで監視
```

このようなプレイブックを **全障害パターン分** 用意し、定期的に演習します。

## 16.7 容量計画と監視

### 16.7.1 容量計画

```mermaid
flowchart LR
    A[現状利用量] --> B[成長率予測]
    B --> C[6ヶ月後/1年後]
    C --> D[ストレージ追加計画]
    D --> E[LVM 拡張<br>or<br>新ボリューム]
```

NFS は **データが増えるたびに止まらず拡張できる** のが利点。LVM の `lvextend + resize2fs`、ZFS の `zpool add` で運用中に拡張可能。

### 16.7.2 監視メトリクス

```yaml
# Prometheus アラート例
groups:
- name: nfs-production
  rules:
  - alert: NFSDiskUsageHigh
    expr: (node_filesystem_avail_bytes{mountpoint="/srv/nfs"} / node_filesystem_size_bytes{mountpoint="/srv/nfs"}) < 0.15
    for: 10m
    annotations:
      summary: NFS data disk < 15% free
    labels:
      severity: warning

  - alert: NFSDiskUsageCritical
    expr: (node_filesystem_avail_bytes{mountpoint="/srv/nfs"} / node_filesystem_size_bytes{mountpoint="/srv/nfs"}) < 0.05
    for: 5m
    labels:
      severity: critical

  - alert: NFSDPanic
    expr: rate(node_nfsd_panic_total[5m]) > 0
    labels:
      severity: critical

  - alert: NFSLatencyHigh
    expr: histogram_quantile(0.99, rate(nfs_op_duration_seconds_bucket[5m])) > 0.1
    for: 10m
    annotations:
      summary: NFS p99 > 100ms

  - alert: PacemakerNodeDown
    expr: pacemaker_node_status == 0
    for: 1m
    labels:
      severity: critical

  - alert: DRBDOutOfSync
    expr: drbd_oos_kb > 1024
    for: 5m
```

## 16.8 災害復旧(DR)サイト

production の最終ガードは **「データセンタごと吹き飛んでも、別サイトから復旧できる」** です。

```mermaid
flowchart LR
    subgraph Pri[Primary DC]
        PrimNFS[Primary NFS HA]
    end
    subgraph DR[DR site - 地理的に離れた場所]
        DRNFS[DR NFS - Standby]
        DRK8s[DR Kubernetes]
    end
    Pri -.zfs send -i / rsync.-> DR
    Pri -.Velero backup.-> S3[(Object Storage<br>Cross-region replicated)]
    S3 -.復元先.-> DR
```

| DR 形態 | RPO | RTO | コスト |
|---------|-----|-----|--------|
| Cold(月次バックアップ持出) | 30 日 | 24 時間 | 低 |
| Warm(日次差分 + 月次フル) | 24 時間 | 4 時間 | 中 |
| Hot(リアルタイムレプリカ) | 数分 | 30 分 | 高 |
| Active-Active | ≒0 | ≒0 | 最高 |

### 16.8.1 ZFS send による Warm DR

```bash
# Primary でスナップショット
sudo zfs snapshot nfs-pool/k8s@daily-$(date +%F)

# DR サイトへ差分転送
sudo zfs send -i nfs-pool/k8s@daily-2026-05-08 nfs-pool/k8s@daily-2026-05-09 \
  | ssh dr-nfs sudo zfs receive dr-pool/k8s
```

cron で日次実行。RPO 24h を達成。

### 16.8.2 Velero クロスリージョン

```bash
velero install \
  --bucket velero-dr-region \
  --backup-location-config region=us-west-2 \
  ...

# 定期バックアップ
velero schedule create daily \
  --schedule="0 1 * * *" \
  --include-namespaces todo \
  --ttl 168h
```

復元時は DR の K8s クラスタに同じ Velero を入れて `velero restore` で戻します。

## 16.9 ハンズオン: 全障害復旧演習

四半期に 1 度、以下の演習を実機で行います。

```bash
#!/bin/bash
# 障害復旧演習スクリプト
# 注意: ステージング環境で実施

# 演習 1: Primary NFS をシャットダウン → 自動 failover 確認
echo "=== Test 1: Primary NFS shutdown ==="
START=$(date +%s)
ssh nfs-ha1 sudo shutdown -h now &
sleep 60
ssh nfs-ha2 pcs status
RECOVERY=$(( $(date +%s) - START ))
echo "Failover time: ${RECOVERY}s"

# 演習 2: DRBD 同期遅延注入 → 検知時間測定
echo "=== Test 2: DRBD lag injection ==="
ssh nfs-ha1 sudo tc qdisc add dev eth0 root netem delay 500ms
# Prometheus でアラート発火を確認
sleep 600
ssh nfs-ha1 sudo tc qdisc del dev eth0 root

# 演習 3: バックアップから完全復元
echo "=== Test 3: Full restore from backup ==="
kubectl create namespace test-restore
velero restore create --from-backup latest-daily --namespace-mappings todo:test-restore --wait
kubectl exec -n test-restore postgres-0 -- psql -U todo -c "SELECT count(*) FROM tasks;"
kubectl delete namespace test-restore

# 演習 4: DR サイト切替
echo "=== Test 4: DR site failover ==="
# DR サイトの DNS を本番に切替
# DR の Velero で復元
# クライアントの接続テスト
```

このような演習を **書面で計画し、実機で実行し、結果を記録** する文化が production の HA を支えます。

## 16.10 第 16 部のまとめ

- HA 設計は **SLO 駆動**(Availability、RPO、RTO、Latency)
- 構成パターンは 4 種類(単一+バックアップ、HA+DRBD、分散+Ganesha、マネージド)
- **STONITH なしの 2 ノード HA は地雷**(split-brain 必発)
- NIC bonding、RAID、UPS で物理層も冗長化
- プレイブック整備と定期演習は production の絶対条件
- DR サイトを **離れた場所** に持つ(地震、停電、政情)
- 監視・アラート・容量計画は HA とセットで設計

---

# 第 17 部: NFS の弱点と限界

ここまで NFS の良さばかり強調してきましたが、**「使うべきでない場面」** を見抜く力は、技術者として等しく重要です。本パートでは NFS の構造的弱点を体系的に整理します。

## 17.1 NFS の 5 大弱点

```mermaid
flowchart TB
    A[NFS の構造的弱点] --> B[単一障害点 SPOF]
    A --> C[レイテンシ]
    A --> D[メタデータ性能]
    A --> E[ロック問題]
    A --> F[ネットワーク依存]
```

| 弱点 | 影響度 | 緩和策の有無 | 影響範囲 |
|------|--------|------------|---------|
| 単一障害点 | 高 | あり(HA 化) | 全クライアント |
| レイテンシ | 中〜高 | 限定的 | OLTP・低レイテンシ要件 |
| メタデータ性能 | 中 | 限定的 | 多数小ファイルワークロード |
| ロック問題 | 中 | NFSv4 で改善 | DB・並行書込 |
| ネットワーク依存 | 高 | あり(専用 NW) | 全アクセス |

それぞれを深く見ていきます。

## 17.2 弱点 1: 単一障害点(SPOF)

### 17.2.1 何が単一障害点か

```mermaid
flowchart TB
    subgraph Single[単一 NFS 構成]
        K8s[K8s クラスタ<br>全 Pod] --> NFS[NFS サーバ 1 台]
        NFS --> D[(ディスク)]
        NFS --> N[(NIC)]
        NFS --> P[(電源)]
    end
```

単一の NFS サーバ構成では、**サーバ全体だけでなく、その中の任意のコンポーネント故障** がクラスタ全体のストレージ I/O を止めます。

| 故障ポイント | 影響 |
|------------|------|
| サーバ電源 | 全 NFS クライアント停止 |
| NIC | 同上 |
| カーネル panic | 同上 |
| ディスク(RAID なし) | データ損失 |
| OS バグ | 同上 |
| 設定ミス | 同上 |

### 17.2.2 SPOF の実害シナリオ

```mermaid
flowchart LR
    A[NFS サーバ落ちる] --> B[全クライアントの<br>I/O ハング]
    B --> C[Pod が hard mount で<br>無限待ち]
    C --> D[Liveness Probe<br>失敗で再起動]
    D --> E[再起動した Pod も<br>マウントできない]
    E --> F[全アプリ停止]
```

「Pod のレプリカを増やしても、ストレージが 1 つなら冗長化にならない」のが NFS の致命的な構造です。

### 17.2.3 緩和策

| 対策 | 効果 | コスト |
|------|------|--------|
| Pacemaker + DRBD HA | サーバ全死に耐性 | 中(2 ノード分) |
| 分散 FS(Ceph/Gluster) | スケールアウト冗長 | 高(3+ ノード、運用工数) |
| 商用アプライアンス | 標準で HA | 高(ライセンス) |
| マネージド NFS(EFS 等) | クラウド側が保証 | 従量課金 |
| バックアップ強化 | 復元時間を短縮 | 低 |

### 17.2.4 「SPOF と分かって使う」設計

すべてを冗長化するとコストが爆発するので、「**SPOF だと自覚した上で運用する**」のも選択肢です。

- **Tier 1 データ**(顧客 DB):ローカル SSD + アプリレベルレプリケーション
- **Tier 2 データ**(セッション、キャッシュ):NFS + 多層バックアップ
- **Tier 3 データ**(ログ、解析素材):NFS + リモートレプリカ

データの重要度ごとにストレージ種別を選ぶ「**ストレージ層の階層化**」が production の常識です。

## 17.3 弱点 2: レイテンシ

### 17.3.1 NFS レイテンシの内訳

```mermaid
flowchart LR
    A[Pod] -->|VFS| B[NFS Client]
    B -->|RPC over TCP| C[Network]
    C -->|2049 LISTEN| D[NFS Server]
    D -->|VFS| E[ローカル FS]
    E -->|hw| F[Disk]
```

各レイヤでのレイテンシ加算(典型値、低負荷時):

| レイヤ | レイテンシ追加 |
|--------|--------------|
| Pod → NFS Client(VFS) | ~50µs |
| NFS Client → Network | ~10µs |
| Network(1GbE) | RTT ~200µs |
| Network(10GbE) | RTT ~50µs |
| NFS Server → ローカル FS | ~50µs |
| ローカル FS → SSD(同期書込) | ~100µs |
| **合計(1GbE)** | **~410µs / 操作** |
| **合計(10GbE)** | **~260µs / 操作** |
| **比較: ローカル SSD** | **~150µs / 操作** |

つまり NFS は **ローカル SSD 比でレイテンシ 2〜3 倍** です。

### 17.3.2 PostgreSQL での実害

```bash
# pgbench で TPS 比較(参考値)
# ローカル SSD:           2,500 TPS
# NFS over 10GbE:         400〜800 TPS
# NFS over 1GbE:          200〜400 TPS
```

PostgreSQL は WAL 書き込みごとに `fsync` を呼ぶため、**レイテンシが直接 TPS に効きます**。同期書込が必要な OLTP は NFS では性能が出ません。

### 17.3.3 緩和策と限界

| 手法 | 効果 | 限界 |
|------|------|------|
| 10GbE 化 | レイテンシ半減 | 物理的に光速限界がある |
| `nconnect=4` | 並列度向上(レイテンシ自体は変わらない) | 単発オペは速くならない |
| async export(`async`) | 50〜80% 改善 | データロスリスク |
| サーバ側 NVMe | サーバ側遅延を減らす | ネットワーク部分は不変 |
| アプリ層キャッシュ | I/O 回数自体を減らす | アプリ修正 |
| RDMA(NFS-RDMA) | RTT 大幅短縮 | InfiniBand 機材必要 |

**「同期書込を多用する OLTP には NFS は本質的に不向き」** は揺らぎません。これは緩和策の話ではなく、**プロトコル的限界** です。

### 17.3.4 ハンズオン: NFS とローカルのレイテンシ比較

```bash
# NFS PVC を持つ Pod
kubectl exec -n todo postgres-0 -- \
  fio --name=lat --rw=randwrite --bs=4k --iodepth=1 --runtime=30 \
      --time_based --direct=1 --sync=1 --filename=/var/lib/postgresql/data/pgdata/fio-test
# clat (usec): min=400, avg=2500, max=20000     ← NFS の典型値

# ノード上で local-path
kubectl exec -n bench local-fio-0 -- \
  fio --name=lat --rw=randwrite --bs=4k --iodepth=1 --runtime=30 \
      --time_based --direct=1 --sync=1 --filename=/data/fio-test
# clat (usec): min=80, avg=200, max=1500        ← local SSD は 1 桁 µs 速い
```

数字が **オーダー違い** なのが分かります。

### 17.3.5 OLTP DB を NFS で動かす場面の判断

```mermaid
flowchart TB
    A[OLTP DB を NFS で動かす?] --> B{TPS 要件?}
    B -- <100 --> C[NFS で十分]
    B -- 100~1000 --> D{許容レイテンシ?}
    D -- p99 <100ms --> E[NFSv4.1+ 10GbE で要検証]
    D -- p99 <10ms --> F[ローカル SSD 推奨]
    B -- >1000 --> F
```

学習・小規模社内ツールは NFS で十分、商用 OLTP は **NFS では避けるのが原則**。

## 17.4 弱点 3: メタデータ性能

### 17.4.1 メタデータ操作とは

ファイル**内容**ではなく、**ファイルの構造情報** に対する操作です。

- `stat()` / `lstat()` ─ 属性取得
- `readdir()` ─ ディレクトリ列挙
- `open()` / `close()` ─ ファイルディスクリプタ確保
- `lookup` ─ 名前 → inode 解決
- `rename` / `link` / `unlink` ─ ディレクトリ書換
- `getxattr` ─ 拡張属性

### 17.4.2 NFS でのメタデータ性能問題

各メタデータ操作は **1 つの RPC 呼出を必要とする** ため、ネットワーク往復が直接効きます。

```mermaid
sequenceDiagram
    participant C as Client
    participant N as NFS Server
    Note over C,N: ls -la /mnt/nfs/dir (1000 ファイル)
    C->>N: READDIR
    N-->>C: 100 entries
    C->>N: GETATTR for each entry × 1000
    N-->>C: attrs × 1000
    Note over C: 1000+ RTT 発生!
```

`ls -la` が 1 ディレクトリで 1000 ファイル列挙するのに、**1000 回以上のラウンドトリップ** が発生することがあります。

### 17.4.3 実害シナリオ

| ワークロード | NFS での挙動 |
|------------|-------------|
| `find /mnt/nfs -type f` | 1 ファイルにつき複数 RPC、巨大ディレクトリで数分〜数十分 |
| `ls -lR` | 同上、再帰深さに比例 |
| `git status`(NFS 上の repo) | 全ファイルの mtime チェック → 激遅 |
| Maven / npm の依存解決 | 数千の小ファイルへ stat |
| Docker build context 転送 | 大量の stat |
| 大量小ファイル削除 | 1 ファイルごとに RPC |

### 17.4.4 ハンズオン: メタデータ性能の実測

```bash
# 1000 ファイルを作る
kubectl exec -n todo file-generator -- \
  sh -c "for i in \$(seq 1 1000); do touch /data/f-\$i; done"

# ls -la の時間
kubectl exec -n todo file-generator -- time ls -la /data | tail -5
# real    0m3.456s   ← NFS

# 比較: ローカル
kubectl exec -n local file-gen-local -- time ls -la /data
# real    0m0.123s   ← ローカル
```

ファイル数を 1万 にすると差がさらに開きます。

### 17.4.5 緩和策

| 手法 | 効果 | 限界 |
|------|------|------|
| `actimeo=N` 大きく | キャッシュヒットでメタデータ RPC 削減 | 整合性低下 |
| `lookupcache=all` | 名前解決キャッシュ強化 | 削除・リネームで不整合リスク |
| Directory delegation(NFSv4.1+) | ディレクトリ単位委譲 | サーバ実装依存 |
| pNFS でメタデータ分散 | スケールアウト | 商用機向け |
| アプリ層変更(階層化) | ディレクトリを小さく | 設計改変 |

### 17.4.6 「NFS で git が遅い」問題

DevOps チームでよくあるシナリオ。Git は `.git/objects/` に大量の小ファイルを置き、`git status` で全ファイルの mtime をチェックします。**NFS 上の git repo は使い物にならない** ことが多いです。

回避策:

- 開発者ホームディレクトリは NFS にせず、ローカル
- CI/CD では `.git` だけ tar で送って tmpfs 展開
- `git config core.preloadIndex true`、`core.fsmonitor` 等のチューニング

## 17.5 弱点 4: ロック問題

### 17.5.1 NFS ロックの歴史的弱点

```mermaid
timeline
    title NFS ロックの進化
    NFSv2/v3 : NLM 別プロトコル<br>クライアント死 = ロック残骸
    NFSv4    : プロトコル組込<br>状態管理改善
    NFSv4.1  : セッションモデル<br>exactly-once
```

### 17.5.2 NFSv3 NLM の問題

- 別プロトコル(`lockd`、`statd`)が必要
- クライアントが死ぬとロック復旧に時間
- **PostgreSQL 公式が NFSv3 を非推奨** とした歴史
- ロックリーク(プロセスが死んでロックが残る)

### 17.5.3 NFSv4 でも残る課題

- **クライアント時刻同期が必須**(リース時間管理)
- ネットワーク分断時のロック状態管理
- 多 Pod から同一ファイルへのロック競合

### 17.5.4 ハンズオン: ロック競合の観察

```bash
# 2 つの Pod が同じファイルに `flock` を取り合う
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: locker-1
spec:
  containers:
  - name: app
    image: alpine
    command: ["sh","-c","apk add flock && while true; do flock /data/lock -c 'date >> /data/log.txt; sleep 1'; done"]
    volumeMounts: [{ name: data, mountPath: /data }]
  volumes:
  - name: data
    persistentVolumeClaim: { claimName: uploads }
EOF
# locker-2 も同様に作る

# /data/log.txt にどのくらいの頻度で書けるか
kubectl exec locker-1 -- tail -f /data/log.txt
```

NFS だとロック取得・解放が往復するため、競合が激しいと急激にスループット低下します。

### 17.5.5 緩和策

| 手法 | 効果 |
|------|------|
| NFSv4.1+ 統一 | ロック信頼性向上 |
| `nolock` マウント | 単一プロセスの場合のみ(共有禁止) |
| 時刻同期厳格化 | リース処理の安定 |
| アプリ層レイヤでロック | NFS ロックに頼らない(Redis、DB の row lock) |

**DB は DB エンジン内部でロックを管理する** ので、PostgreSQL や MySQL がうまく動くかは NFS ロックの信頼性次第。「**NFS で OLTP やるなら NFSv4.1+ 必須**」が業界の暗黙合意です。

## 17.6 弱点 5: ネットワーク依存

### 17.6.1 何がネットワーク依存か

NFS のあらゆる操作は **ネットワーク経由** です。これは利点(共有可能)でもあり、最大の弱点でもあります。

```mermaid
flowchart TB
    A[ネットワーク依存] --> B[帯域]
    A --> C[レイテンシ]
    A --> D[パケットロス]
    A --> E[ジッタ]
    A --> F[分断]
    B --> B1[NIC 性能上限]
    C --> C1[物理距離 + ホップ数]
    D --> D1[再送で性能劣化]
    E --> E1[アプリの揺らぎ]
    F --> F1[全 I/O 停止]
```

### 17.6.2 帯域の例(クラスタ全体共有)

- 1GbE = 125 MB/s 理論値、実効 100 MB/s 程度
- これを **クラスタの全クライアントで共有**
- 10 ノード × 10 MB/s で帯域消費すると即飽和

10GbE = 1 GB/s 理論値で、これも本気のクラスタなら詰まることがあります。

### 17.6.3 ハンズオン: 帯域飽和の実演

```bash
# 全ワーカーで同時に大量書込
for w in k8s-w1 k8s-w2 k8s-w3; do
  kubectl exec -n bench fio-pod-$w -- fio --rw=write --bs=1M --runtime=60 --time_based --filename=/data/fio &
done

# サーバ側で iperf3 + iftop で帯域消費を見る
ssh k8s-nfs sudo iftop -i bond0
# 1GbE の場合、すぐ 940Mbps で頭打ち
```

### 17.6.4 ネットワーク分断時の挙動

NFS は **ネットワークが切れた瞬間に I/O が止まる**。`hard` マウントなら永遠に待ち、`soft` ならエラー。

`grace-time`(NFSv4 のリース回復時間、デフォルト 90 秒)も加味すると、**短時間の NW 切断でも数十秒の I/O 停止** は避けられません。

### 17.6.5 緩和策

| 手法 | 効果 | コスト |
|------|------|--------|
| 10GbE / 25GbE / 100GbE | 帯域確保 | NIC・スイッチ更新 |
| NIC bonding | 帯域 + 冗長 | スイッチ設定 |
| ストレージ専用 VLAN | 業務トラフィックと分離 | NW 設計 |
| RDMA(NFS-RDMA) | 低レイテンシ・低 CPU | InfiniBand 機材 |
| クライアント側キャッシュ強化 | RPC 数削減 | 整合性 |
| ローカル SSD への階層化 | NFS 依存度低減 | アプリ設計 |

### 17.6.6 ストレージ専用ネットワーク

production では **ストレージ専用 NIC** を別系統で用意することが多いです。

```mermaid
flowchart TB
    subgraph N1[Node]
        eth0[eth0<br>192.168.10.x<br>業務 LAN]
        eth1[eth1<br>10.0.0.x<br>ストレージ専用]
    end
    eth0 -->|API/Pod 通信| Net1[業務スイッチ]
    eth1 -->|NFS| Net2[ストレージスイッチ]
    Net2 --> NFS[NFS サーバ]
```

これで:

- 業務トラフィックと NFS が干渉しない
- セキュリティ(NFS が業務 LAN 経由でアクセスされない)
- 性能(専用帯域)

## 17.7 NFS の弱点を「踏まない」設計フローチャート

```mermaid
flowchart TB
    A[NFS を使うか?] --> B{SPOF 受容?}
    B -- No --> B1[HA / 分散 / マネージドへ]
    B -- Yes --> C{レイテンシ要件?}
    C -- p99 <10ms 必須 --> C1[ローカル SSD]
    C -- 緩い --> D{メタデータ多い?}
    D -- Yes --> D1[アプリ層キャッシュ or 階層化]
    D -- No --> E{ロック多い?}
    E -- Yes --> E1[NFSv4.1+ 必須、ロックは慎重テスト]
    E -- No --> F{NW 信頼?}
    F -- Yes --> G[NFS で OK]
    F -- No --> F1[専用 NW + bonding]
```

## 17.8 NFS が「使えない」ワークロード一覧

私たちが本教材で NFS を中心に据えていても、**本当に使ってはいけないワークロード** はあります。

| ワークロード | NFS NG な理由 | 代替 |
|------------|--------------|------|
| etcd / Consul | 同期書込・ロックの厳しさ | local PV + アプリ層複製 |
| Kafka | 高スループット sequential、レプリケーション | local PV、Kafka 内蔵レプリカ |
| Elasticsearch インデックス | 同様 | local PV |
| 高 TPS OLTP DB | レイテンシ | local PV + DB レプリケーション |
| 大規模 git monorepo | メタデータ性能 | ローカル SSD |
| iOS 開発の Xcode キャッシュ | メタデータ・並行性 | ローカル SSD |
| Bazel / Buck の `.bazel-cache` | メタデータ | ローカル SSD |
| ブロックデバイスが必要なもの | ファイル抽象では無理 | iSCSI、Ceph RBD |

## 17.9 NFS を選ぶときのチェックリスト

```mermaid
flowchart LR
    A[要件分析] --> B[弱点との照合] --> C[緩和策の確認] --> D[採用決定]
```

- [ ] SPOF を受容できるか、HA 化するか
- [ ] レイテンシ要件は緩いか、それとも厳しいか
- [ ] メタデータ操作の量を見積もっているか
- [ ] ファイルロックの使用頻度を見積もっているか
- [ ] ストレージ専用 NW を用意できるか
- [ ] バックアップ・DR を設計しているか
- [ ] アプリのキャッシュ戦略を持っているか
- [ ] 代替(local PV、分散 FS、マネージド)を検討したか

## 17.10 第 17 部のまとめ

- NFS には 5 大弱点(SPOF、レイテンシ、メタデータ、ロック、NW 依存)が **構造的に存在**
- 緩和策はあるが、**プロトコル的限界もある**
- OLTP DB、etcd、Kafka など特定ワークロードでは **NFS を選んではいけない**
- 弱点を理解した上で **適性に応じてストレージを階層化** するのが production 設計
- 「すべてを NFS で」「すべてを分散 FS で」は両方とも誤り
- 本教材の学習段階では NFS で十分、要件が出たら段階的に移行

---

# 全体のチェックポイント

このページ全体で **以下を自分の言葉で説明できる** か確認してください。

## プロトコル理解(第 1 部)

- [ ] NFSv3 と NFSv4 の決定的な違い(単一ポート化、ステートフル化、COMPOUND)を述べられる
- [ ] NFSv4.1 で導入された pNFS が解決した課題を説明できる
- [ ] close-to-open consistency と、それが破れるシナリオを述べられる
- [ ] Stale file handle が発生する 3 パターン以上を挙げられる
- [ ] サイレントリネーム(`.nfs*` ファイル)の意味を述べられる

## サーバ構築(第 2 部)

- [ ] `/etc/exports` の主要 8 オプション(rw, sync, root_squash 系, subtree_check, secure, sec, fsid, anonuid)を説明できる
- [ ] `/etc/nfs.conf` で NFSv4-only モードに切替える具体的設定が書ける
- [ ] LVM でストレージを準備し、`/etc/fstab` に永続マウントを登録できる
- [ ] ufw で 2049/tcp のみ許可するルールが書ける
- [ ] `exportfs -v`、`rpcinfo`、`showmount`、`nfsstat`、`nfsiostat` のそれぞれの用途が言える

## クライアント側(第 3 部)

- [ ] hard / soft マウントの違いと、DB バックエンドでは hard が必須な理由
- [ ] `timeo`、`retrans`、`nconnect`、`rsize/wsize` の意味
- [ ] `noac` / `actimeo` の使い分け
- [ ] `mount | grep nfs` で実マウントオプションを確認できる

## NFS-CSI(第 4 部)

- [ ] NFS-CSI ドライバの主要 Pod(controller、node)と、controller の各サイドカー(provisioner、attacher、resizer、snapshotter)の役割
- [ ] Helm でインストールして動作確認するまでの一連手順
- [ ] CSIDriver オブジェクトを `kubectl get csidriver` で確認できる

## 静的 PV(第 5 部)

- [ ] 静的 PV と動的プロビジョニングのトレードオフを述べられる
- [ ] 複数 PV を一括作成するスクリプトを書ける
- [ ] PV ラベルと PVC `selector.matchLabels` で意図したマッチングを実現できる
- [ ] `claimRef` で別 Namespace への流出を防ぐ手法

## 動的プロビジョニング(第 6 部)

- [ ] StorageClass の `parameters` の主要キー(server、share、subDir)を説明できる
- [ ] `subDir` で `${pvc.metadata.namespace}` 等のテンプレ変数が使える
- [ ] `mountOptions` で NFS 接続パラメータをチューニングできる
- [ ] `reclaimPolicy: Delete` と `Retain` の選択基準

## セキュリティ(第 7 部)

- [ ] `sec=sys` の挙動と、Kerberos(sec=krb5)を採用すべき場面
- [ ] `root_squash` がない環境で起こり得る攻撃シナリオ
- [ ] NetworkPolicy で NFS への通信を制限する設計
- [ ] NFS データの暗号化選択肢(at-rest、in-transit)

## 権限問題(第 8 部)

- [ ] UID/GID が「コンテナ内 → kernel → NFS → サーバ」と流れる過程
- [ ] `fsGroup` と `fsGroupChangePolicy: OnRootMismatch` を組み合わせる理由
- [ ] PostgreSQL / Redis / Nginx それぞれの公式イメージの UID
- [ ] 「すべての Pod に対応する」UID 設計

## パフォーマンス(第 9 部)

- [ ] `fio` で NFS ベースラインを測る基本コマンド
- [ ] `nconnect=4` の効果と限界
- [ ] `nfsd threads` を上げるべき指標(`nfsstat -s` のスレッド分布)
- [ ] `rsize=wsize=1048576` の根拠
- [ ] NFS で PostgreSQL の TPS が下がる根本理由

## HA(第 10 部)

- [ ] keepalived + DRBD と Pacemaker + DRBD の違い
- [ ] DRBD の Protocol C(同期)が NFS HA で必須な理由
- [ ] GlusterFS / CephFS + NFS-Ganesha の用途
- [ ] 商用アプライアンス / クラウド NFS との比較

## バックアップ(第 11 部)

- [ ] スナップショットとバックアップの違い
- [ ] LVM スナップショットの容量設計(`-L` で指定する量の意味)
- [ ] `rsync --delete` の罠と、rsnapshot による世代管理
- [ ] ZFS send / recv の差分転送
- [ ] CSI VolumeSnapshot と NFS の組み合わせと制約

## トラブルシューティング(第 12 部)

- [ ] Stale file handle の発生原因と対処
- [ ] `ContainerCreating` で 5 分以上止まるときの調査フロー
- [ ] マウントに 30 秒以上かかるときの原因と解決
- [ ] `tcpdump` で NFS パケットを取って解析する方法

## 総合実技(第 13 部)

- [ ] TODO サンプルアプリの全コンポーネント(Frontend / API / Postgres / Redis / Worker / Uploads)を NFS だけで動かせる
- [ ] StatefulSet の `volumeClaimTemplates` と、Deployment + 静的 RWX PVC の使い分け
- [ ] NFS サーバ再起動時の `hard` マウント挙動を観察し、説明できる
- [ ] スナップショット → 別 PVC への復元演習を完遂できる
- [ ] ワーカーノード障害時に Pod が別ノードへ移動することを確認できる

## CSI Driver 深堀り(第 14 部)

- [ ] in-tree plugin → FlexVolume → CSI への進化の動機を説明できる
- [ ] `kubernetes.io/nfs` in-tree が v1.25 で完全削除されたこと、Migration shim もないことを述べられる
- [ ] CSI の 3 サービス(Identity / Controller / Node)の役割
- [ ] NFS-CSI が `attachRequired: false` である理由
- [ ] `NodeStageVolume` と `NodePublishVolume` の 2 段階マウント構造
- [ ] 標準サイドカー(provisioner、snapshotter、resizer、node-driver-registrar)が何を監視して何を呼ぶか
- [ ] NFS-CSI の `CreateVolume` 実装が実質「mkdir」であること
- [ ] `CSIDriver` CRD の主要フィールド(`attachRequired`、`podInfoOnMount`、`fsGroupPolicy`)

## セキュリティ深堀り(第 15 部)

- [ ] `sec=sys` で UID 詐称が起こりうる仕組み
- [ ] Kerberos の 3 段階(`krb5` / `krb5i` / `krb5p`)の違い
- [ ] `all_squash + anonuid=999` が「Pod の UID 設定ミスに対する保険」となる仕組み
- [ ] Calico GlobalNetworkPolicy で全 Pod に共通制約を適用する設計
- [ ] LUKS による at-rest 暗号化のセットアップ手順
- [ ] NFS over TLS(NFSv4.2)の現状と利用条件
- [ ] PSA `restricted` 適用時に CSI ドライバ Pod は別 Namespace に置く理由
- [ ] `nosuid,nodev,noexec` マウントオプションの効用

## Production HA 設計(第 16 部)

- [ ] SLO(Availability、RPO、RTO、Latency)を起点に HA 構成を選ぶ流れ
- [ ] 4 つの構成パターン(単一+バックアップ、Pacemaker+DRBD、分散+Ganesha、マネージド)の使い分け
- [ ] **STONITH なしの 2 ノード HA が地雷** である理由(split-brain)
- [ ] 多重化ポイント(電源、NIC、ディスク、ノード、サイト)
- [ ] NIC bonding(active-backup)の設定と確認
- [ ] ZFS RAID-Z2 とディスク冗長
- [ ] 障害復旧プレイブックに含めるべき要素
- [ ] DR サイト構成パターン(Cold / Warm / Hot / Active-Active)と RPO/RTO トレードオフ
- [ ] ZFS send による差分転送、Velero クロスリージョン
- [ ] 四半期の障害復旧演習

## NFS の弱点と限界(第 17 部)

- [ ] NFS の 5 大弱点(SPOF、レイテンシ、メタデータ、ロック、NW 依存)を列挙し、それぞれの実害シナリオを述べられる
- [ ] **OLTP DB を NFS で動かすとなぜ TPS が下がるか**(同期書込 × レイテンシ)
- [ ] メタデータ操作の RPC コストと、`ls -la` が NFS で遅い理由
- [ ] `git status` が NFS 上の repo で遅い具体的メカニズム
- [ ] NFSv3 NLM の歴史的問題と、NFSv4 で何が改善されたか
- [ ] ストレージ専用ネットワークを業務 LAN と分離する設計
- [ ] NFS が **絶対に使えない** ワークロード(etcd / Kafka / 高 TPS DB / Bazel 等)
- [ ] 「データの重要度ごとにストレージ層を階層化する」設計思想

---

→ 次は [ステートフル運用の実例]({{ '/05-storage/stateful-storage/' | relative_url }})
