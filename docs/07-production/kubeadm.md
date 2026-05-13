---
title: kubeadmで自前クラスタ構築 (HA)
parent: 07. 本番運用
nav_order: 1
---

# kubeadmで自前クラスタ構築 (HA)
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

ここがローカル完結型 K8s 学習の山場です。VMware Workstation 上に **マスター 3 + ワーカー 3** の HA(High Availability、高可用性)構成を kubeadm で構築します。
所要時間は手順を理解しながらで 4〜8 時間、慣れた人で 2 時間。**最初の一回はうまくいきません。** 失敗を前提にスナップショットを取りながら進めてください。

## このページのゴール

このページを読み終えると、以下を **自分の言葉で説明できる** ようになります。

- なぜ Control Plane を 3 台にするのか、奇数にする理由(Raft クォーラム)を説明できる
- kubeadm の各サブコマンドが「内部で何をしているか」を上から下まで言える
- HAProxy + keepalived の VIP がどう機能しているかを図で説明できる
- containerd / runc / CRI / OCI の関係をスタック図で説明できる
- Calico の VXLAN モードと BGP モードの違いを説明できる
- etcd のスナップショット取得とリストア手順を実行できる
- `kubeadm reset` で何が消え、何が消えないかを把握している

## なぜ自分でクラスタを構築するのか

K8s の世界に足を踏み入れた人のほとんどは、最初に EKS / GKE / AKS のようなクラウドマネージド K8s を触ります。これらは「kubectl を叩いたら何かが動く」状態を提供してくれます。便利ですが、教材として扱うと **見えるべきものが見えません**。

| 隠されるもの | 見えると何が学べるか |
|------------|----------------------|
| etcd | 状態がどこに保存されているか、HA がどう機能しているか |
| Control Plane の Pod | API Server / Scheduler / Controller Manager の関係 |
| ノードの kubelet | コンテナランタイムとの通信プロトコル(CRI) |
| CNI のインストール | Pod ネットワークがどう作られるか |
| 証明書 | mTLS、PKI、ローテーションの考え方 |
| LoadBalancer の実装 | クラウドの ELB が何をやってくれているか |

本章ではこれらを **手で全部組み立てる** ことで、「ボタン一発で来てくれた魔法」を解体し、再現可能な理解に変えていきます。

```mermaid
flowchart LR
    subgraph cloud[クラウド K8s]
      direction TB
      hidden1[etcd<br>隠し]
      hidden2[Control Plane<br>隠し]
      hidden3[CNI<br>隠し]
      vis1[Pod<br>見える]
      vis2[Service<br>見える]
    end
    subgraph self[自前 kubeadm]
      direction TB
      see1[etcd<br>見える]
      see2[Control Plane<br>見える]
      see3[CNI<br>見える]
      see4[Pod<br>見える]
      see5[Service<br>見える]
    end
```

## K8s インストール手段の歴史

クラスタを「組む」道具にも歴史があります。

```mermaid
timeline
    title K8s クラスタ構築の歴史
    2014 : Kubernetes 公開 / 「kube-up.sh」スクリプト時代
    2015 : kops 登場 (AWS 中心)
    2016 : kubeadm 登場 (公式ベータ)
    2017 : kubeadm v1.6 で安定化
    2018 : EKS / AKS GA、kubeadm v1.13 で GA
    2020 : kubeadm が事実上の標準ローカル構築手段に
    2024 : kubeadm v1.30 (Cluster API への移行が議論される)
```

| 道具 | 種類 | 用途 |
|------|------|------|
| **手動 (Kubernetes The Hard Way)** | チュートリアル | 全コンポーネントを手で起動。深く理解するための行 |
| **kube-up.sh** | 公式スクリプト(廃止) | 初期に同梱されていたが今はない |
| **kops** | OSS ツール | AWS / GCP の VM を作って K8s を入れる。一時期は事実上の標準 |
| **kubespray** | Ansible Playbook 集 | オンプレで多ノードに一括構築 |
| **kubeadm** | 公式ツール | ノードに入って `kubeadm init` / `join`。本章で使用 |
| **Cluster API (CAPI)** | K8s で K8s を管理 | 大規模・複数クラスタを管理する次世代の標準 |
| **k3s / k0s / microk8s** | 軽量ディストリ | エッジ / 開発向け、コンポーネントを 1 バイナリに統合 |
| **EKS / GKE / AKS** | マネージド | クラウド事業者が Control Plane を運営 |

なぜ kubeadm を使うのか:

1. **公式ツール**(SIG Cluster Lifecycle が管理)
2. **学習素材になる**(各 phase が見える)
3. **本物のクラスタが組める**(Minikube ほど省略がない)
4. **手数が少ない**(Kubernetes The Hard Way ほど辛くない)

[Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way) は本気で K8s に向き合うときに通る道ですが、本教材では kubeadm を選びました。kubeadm が隠している処理は、本章の中で随時「これが裏で何をしているか」を解説します。

## なぜ HA(マスター 3 台)なのか

「マスター 1 台で十分では?」という疑問に答えます。

```mermaid
flowchart TB
    subgraph single[マスター 1 台]
      cp[Control Plane] --> e1[(etcd)]
    end
    subgraph ha[マスター 3 台]
      cp1[CP1] --> e2[(etcd)]
      cp2[CP2] --> e3[(etcd)]
      cp3[CP3] --> e4[(etcd)]
      e2 <-.Raft.-> e3
      e3 <-.Raft.-> e4
      e2 <-.Raft.-> e4
    end
```

### マスターが落ちた時に何が起きるか

| マスター数 | マスター 1 台ダウン時の挙動 |
|----------|------------------------|
| 1 | クラスタ全体が **API 操作不可**(Pod は動き続けるがスケール・更新できない) |
| 2 | etcd の Raft で **クォーラム喪失** → 残った 1 台でも書き込み不可 |
| 3 | クォーラム維持(2/3 で過半数) → **正常に書き込み継続** |
| 5 | 2 台落ちても継続(3/5 で過半数) |

> 既存の Pod は kubelet が動かしているので、Control Plane 全停止でも **「動いている Pod」は動き続けます**。死ぬのは「変更系操作」と「Pod 死亡時の再スケジュール」。

### Raft とクォーラム

etcd は分散合意アルゴリズム **Raft** を使います。Raft は「過半数が同意した変更だけを採用する」というシンプルなルールで、ネットワーク分断時でも一貫性を保ちます。

```mermaid
sequenceDiagram
    participant Client
    participant Leader as etcd Leader
    participant F1 as Follower1
    participant F2 as Follower2
    Client->>Leader: PUT key=v1
    Leader->>F1: AppendEntries
    Leader->>F2: AppendEntries
    F1-->>Leader: ack
    F2-->>Leader: ack
    Note over Leader: 過半数のack確認
    Leader-->>Client: OK
    Leader->>F1: commit
    Leader->>F2: commit
```

奇数(3, 5, 7)にする理由:

| ノード数 | 過半数 | 耐障害台数 |
|---------|--------|-----------|
| 1 | 1 | 0(=可用性ゼロ) |
| 2 | 2 | 0(1 台落ちると過半数喪失) |
| 3 | 2 | 1 |
| 4 | 3 | 1(3 と同じ耐障害性なのにコスト増) |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

つまり 4 や 6 にしてもメリットがなく、**奇数(3 か 5)が最適**。ローカル学習では 3 台で十分です。

参考:
- Raft 論文: [In Search of an Understandable Consensus Algorithm](https://raft.github.io/raft.pdf)(Diego Ongaro, John Ousterhout, 2014)
- etcd 公式ドキュメント: <https://etcd.io/docs/>

## クラスタ全体像

```mermaid
flowchart TB
    user[kubectl on host] --> vip[VIP 192.168.56.10:6443]
    vip --> haproxy[HAProxy<br>k8s-lb]
    haproxy --> cp1[k8s-cp1<br>192.168.56.11<br>kube-apiserver]
    haproxy --> cp2[k8s-cp2<br>192.168.56.12<br>kube-apiserver]
    haproxy --> cp3[k8s-cp3<br>192.168.56.13<br>kube-apiserver]
    cp1 --- e1[(etcd1)]
    cp2 --- e2[(etcd2)]
    cp3 --- e3[(etcd3)]
    e1 <-.Raft.-> e2
    e2 <-.Raft.-> e3
    e1 <-.Raft.-> e3
    cp1 -.kubelet通信.-> w1[k8s-w1]
    cp1 -.kubelet通信.-> w2[k8s-w2]
    cp1 -.kubelet通信.-> w3[k8s-w3]
    nfs[k8s-nfs] -.NFS export.-> w1
    nfs -.NFS export.-> w2
    nfs -.NFS export.-> w3
```

| ホスト | IP | 役割 | スペック |
|--------|----|----|----------|
| `k8s-lb` | 192.168.56.10 | HAProxy + keepalived(VIP も同 IP)+ Docker Registry | 1 vCPU 1 GB |
| `k8s-cp1` 〜 3 | 192.168.56.11-13 | Control Plane | 2 vCPU 4 GB |
| `k8s-w1` 〜 3 | 192.168.56.21-23 | Worker | 2 vCPU 4 GB |
| `k8s-nfs` | 192.168.56.30 | NFS サーバ | 1 vCPU 2 GB |

合計 RAM: `1 + 4×3 + 4×3 + 2 = 27 GB`(ホスト OS 用に 8 GB 残すと 35 GB 必要 → 32 GB だとギリギリ、64 GB あれば余裕)。

## VM の作成(VMware Workstation)

VMware Workstation 上での VM 作成の手順を簡略にまとめます。詳細は付録のスクリーンショット集を参照してください。

```bash
# VMware Workstation の vmrun コマンドを使った例(Windows PowerShell)
$VMRUN = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"

# テンプレート VM を作っておき、リンククローンで複製
foreach ($name in "k8s-lb","k8s-cp1","k8s-cp2","k8s-cp3","k8s-w1","k8s-w2","k8s-w3","k8s-nfs") {
  & $VMRUN clone "D:\vm\template\ubuntu2204.vmx" "D:\vm\$name\$name.vmx" linked -cloneName=$name
}
```

各 VM の設定:

| 項目 | 設定 |
|------|------|
| OS | Ubuntu Server 22.04.4 LTS |
| ファームウェア | UEFI(BIOS でも可) |
| プロセッサ | 2 vCPU、Virtualize Intel VT-x/EPT 有効 |
| メモリ | 4 GB(LB と NFS は 1〜2 GB) |
| ディスク | 40 GB(thin) |
| NIC #1 | NAT(インターネット用、DHCP) |
| NIC #2 | Host-only(VMnet1)、static IP |
| ディスプレイ | コンソールアクセスのみ |

NIC を 2 つ持たせて「インターネット出口は NAT、クラスタ内通信は Host-only」とするのが本教材の流儀です。これにより VM 間通信が安定し、ホスト PC のネットワーク変更(出張先の Wi-Fi など)に左右されません。

```mermaid
flowchart LR
    internet[インターネット] --> nat[NAT NIC]
    nat --> vm[VM]
    vm --> hostonly[Host-only NIC<br>192.168.56.x]
    hostonly --> other[他のVM]
    host[Host PC] -.- hostonly
```

### Ubuntu インストール時のポイント

- **Swap を作らない**(K8s で必要なので、kubeadm の前提に合わせて最初から作らない)
- ホスト名は VM 名と一致させる(`k8s-cp1` など)
- SSH サーバーを有効化
- ユーザは `ubuntu`、パスワード認証 + sudo NOPASSWD(学習用)

## Step1: VM 全台共通の前準備

8 台すべてで実行する初期設定です。各コマンドの意味を逐一説明します。

```bash
# root に昇格(以降のコマンドはすべて root 想定)
sudo -i
```

### 1-1. ホスト名と /etc/hosts

```bash
# ホスト名設定 (VM ごとに変える)
hostnamectl set-hostname k8s-cp1
```

> `hostnamectl` は systemd-hostnamed への薄いラッパーです。`/etc/hostname` を書き換え、即時反映します。

```bash
# 全ノードに /etc/hosts を配布
cat <<'EOF' | tee -a /etc/hosts
192.168.56.10 k8s-lb k8s-api
192.168.56.11 k8s-cp1
192.168.56.12 k8s-cp2
192.168.56.13 k8s-cp3
192.168.56.21 k8s-w1
192.168.56.22 k8s-w2
192.168.56.23 k8s-w3
192.168.56.30 k8s-nfs
EOF
```

`k8s-api` は VIP 用の別名です。`kubeadm init` で `--control-plane-endpoint=k8s-api:6443` と指定するため、すべてのノードで同じ名前で解決できる必要があります。**この `/etc/hosts` 設定を忘れると `kubeadm init` で失敗します**。

DNS サーバを別途立てるなら `k8s-api` を A レコードで登録するのが正攻法ですが、本教材ではローカル環境なので `/etc/hosts` で済ませます。

### 1-2. Swap 無効化

```bash
swapoff -a
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
```

| コマンド | 意味 |
|---------|------|
| `swapoff -a` | 現在有効な全 swap を無効化 |
| `sed -i ...` | `/etc/fstab` の swap 行をコメントアウト(再起動後も無効化) |

**なぜ swap を無効化するのか**:
kubelet は v1.22 までは swap が有効だと **起動時にエラーで止まります**。これは「メモリ管理を kubelet が正確にできなくなる」ためです。具体的には:

- メモリ使用量の計測がノイジーになる
- メモリ Limit を設定しても、実際に Limit に達する前に swap で誤魔化されて、性能が予測不可能になる
- OOMKill のタイミングがズレて、QoS が壊れる

K8s v1.22 から `--fail-swap-on=false` で swap 有効でも起動は可能になりましたが、**production-ready ではない**(KEP-2400)とされています。本教材では従来通り無効化します。

参考: [KEP-2400 Node system swap support](https://github.com/kubernetes/enhancements/tree/master/keps/sig-node/2400-node-swap)

### 1-3. ファイアウォール無効化

```bash
ufw disable
```

学習用ではこれで十分。本番では以下のポートを開けます。

| 用途 | ポート | プロトコル | 対象 |
|------|--------|-----------|------|
| API Server | 6443 | TCP | All |
| etcd peer | 2379-2380 | TCP | Control Plane 同士 |
| Kubelet API | 10250 | TCP | Control Plane → Worker |
| kube-scheduler | 10259 | TCP | Localhost |
| kube-controller-manager | 10257 | TCP | Localhost |
| NodePort | 30000-32767 | TCP | クラスタ外 |
| Calico VXLAN | 4789 | UDP | All |
| Calico BGP(BGP モード時) | 179 | TCP | All |

### 1-4. カーネルモジュール

```bash
cat <<'EOF' > /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter
```

| モジュール | 役割 |
|-----------|------|
| `overlay` | OverlayFS。コンテナイメージのレイヤを重ね合わせる(containerd の snapshotter で使用) |
| `br_netfilter` | bridge を通る IP パケットを iptables で扱えるようにする(Service の iptables/IPVS モードに必要) |

`/etc/modules-load.d/` に書くと **再起動後もロード** されます。`modprobe` は今すぐロード。

### 1-5. sysctl 設定

```bash
cat <<'EOF' > /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system
```

| パラメータ | 意味 |
|----------|------|
| `bridge-nf-call-iptables=1` | Linux Bridge を通るパケットも iptables に通す。Service の DNAT に必須 |
| `bridge-nf-call-ip6tables=1` | IPv6 版。同上 |
| `ip_forward=1` | パケット転送有効化。Pod から外への通信、ノード間通信に必須 |

これを忘れると **「Service にアクセスできるが応答が返らない」「Pod 間通信できない」** という症状で詰まります。トラブル時の典型的な確認項目。

```bash
# 確認
sysctl net.ipv4.ip_forward
# net.ipv4.ip_forward = 1
```

## Step2: コンテナランタイム(containerd)

K8s はコンテナを直接動かさず、**コンテナランタイム(CRI 互換実装)** に依頼します。

```mermaid
flowchart TB
    kubelet[kubelet] -- CRI gRPC --> cri[containerd]
    cri -- runc --> oci[OCI Container]
    cri -- snapshotter --> overlay[OverlayFS]
    cri -- image pull --> registry[(registry)]
```

### CRI / OCI とは

| 標準 | 守備範囲 | 主な実装 |
|------|---------|---------|
| **CRI** (Container Runtime Interface) | kubelet とランタイム間の gRPC API | containerd, CRI-O, dockershim(廃止) |
| **OCI** (Open Container Initiative) | コンテナイメージ形式 / ランタイム仕様 | runc, crun, runsc(gVisor), kata |

K8s はかつて Docker を直接呼んでいましたが、これは Docker daemon → containerd → runc という冗長な経路を通っていました。 v1.20 で **dockershim 廃止** が予告され、v1.24 で実際に削除。現在は kubelet が直接 containerd を叩くのが標準です。

```mermaid
flowchart LR
    subgraph old[v1.23 以前 (dockershim)]
      kubelet1[kubelet] --> dockershim --> docker[dockerd] --> ctd1[containerd] --> runc1[runc]
    end
    subgraph new[v1.24 以降 (CRI 直接)]
      kubelet2[kubelet] --> ctd2[containerd] --> runc2[runc]
    end
```

参考: [Don't Panic: Kubernetes and Docker](https://kubernetes.io/blog/2020/12/02/dont-panic-kubernetes-and-docker/)

### containerd インストール

```bash
apt-get update
apt-get install -y containerd
```

> **代替**: Docker Engine 公式リポジトリから新しい `containerd.io` を入れる手もあります。Ubuntu 標準リポジトリのバージョンが古い場合はこちら。
>
> ```bash
> install -m 0755 -d /etc/apt/keyrings
> curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
> chmod a+r /etc/apt/keyrings/docker.asc
> echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
>   | tee /etc/apt/sources.list.d/docker.list
> apt-get update
> apt-get install -y containerd.io
> ```

### containerd 設定

```bash
mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml
```

`containerd config default` はデフォルト設定を吐くだけで、ファイルには書きません。`tee` でリダイレクトしています。

#### SystemdCgroup を有効にする

```bash
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
```

これは **絶対に必要** な変更です。理由:

- Linux の cgroup driver は `cgroupfs` と `systemd` の 2 種類
- systemd 系 OS(Ubuntu / RHEL / Debian)は **systemd が cgroup を管理する**
- kubelet と containerd で driver が食い違うと、リソース制限が効かない / Pod 起動が遅い / OOM 動作が変
- kubeadm v1.22 以降の **既定は systemd**

```mermaid
flowchart LR
    systemd[systemd] -- cgroup管理 --> cgroupv2[cgroup v2]
    kubelet -- cgroupDriver=systemd --> systemd
    containerd -- SystemdCgroup=true --> systemd
```

確認:

```bash
grep SystemdCgroup /etc/containerd/config.toml
# SystemdCgroup = true
```

#### sandbox イメージの指定(中国などからの環境向け)

デフォルトでは `registry.k8s.io/pause:3.x` を使いますが、ネットワーク的に到達できない環境では `sandbox_image` を変更します。本教材の Host-only ネットワークは NAT 経由でインターネットに出られる前提です。

```toml
# /etc/containerd/config.toml
[plugins."io.containerd.grpc.v1.cri"]
  sandbox_image = "registry.k8s.io/pause:3.9"
```

#### プライベートレジストリの登録

`k8s-lb:5000` のローカルレジストリを使うので、**TLS なしで pull できるよう** 設定します。

```toml
[plugins."io.containerd.grpc.v1.cri".registry]
  config_path = "/etc/containerd/certs.d"
```

```bash
mkdir -p /etc/containerd/certs.d/192.168.56.10:5000
cat <<'EOF' > /etc/containerd/certs.d/192.168.56.10:5000/hosts.toml
server = "http://192.168.56.10:5000"

[host."http://192.168.56.10:5000"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
```

#### 起動

```bash
systemctl restart containerd
systemctl enable containerd

# 動作確認
ctr version
crictl --runtime-endpoint unix:///run/containerd/containerd.sock version
```

`ctr` は containerd 純正クライアント、`crictl` は CRI 経由で叩く CLI(K8s と同じインターフェース)。

### コンテナランタイムの代替

| 実装 | 特徴 | 用途 |
|------|------|------|
| **containerd** | デフォルト。シンプルで高速 | 一般用途 |
| **CRI-O** | RHEL/OpenShift で標準 | RHEL 系 |
| **Docker(dockershim 経由)** | v1.23 まで | 過去の互換用、新規不可 |
| **cri-dockerd** | コミュニティ版 dockershim | どうしても Docker daemon を残したい場合 |
| **gVisor (runsc)** | サンドボックス化されたユーザ空間カーネル | マルチテナントセキュリティ |
| **Kata Containers** | 軽量 VM でコンテナを隔離 | 強い隔離が必要な用途 |

containerd は CNCF Graduated。`runc` は OCI Reference 実装で、containerd の下で動く実体です。

## Step3: kubeadm / kubelet / kubectl のインストール

```bash
apt-get install -y apt-transport-https ca-certificates curl gpg
```

### Kubernetes apt リポジトリの登録

```bash
mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | \
  gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /' | \
  tee /etc/apt/sources.list.d/kubernetes.list
```

| URL | 内容 |
|-----|------|
| `pkgs.k8s.io/core:/stable:/v1.30/deb/` | community-owned Kubernetes APT リポジトリ。**v1.30 系のみ** が入っている |

> **歴史的経緯**: 以前は `apt.kubernetes.io` という Google 運営のリポジトリでしたが、2023 年 9 月に **community-owned** な `pkgs.k8s.io` に移行しました。 旧リポジトリは 2023 年末で凍結。`apt.kubernetes.io` を使った古い記事はそのままでは動きません。
>
> 参考: [Changes to the Kubernetes apt-get repository](https://kubernetes.io/blog/2023/08/15/pkgs-k8s-io-introduction/)

URL に `v1.30` が含まれている点に注目してください。バージョンごとに別 URL です。これにより「うっかり apt-get upgrade で v1.31 に上がる事故」を防いでいます。アップグレードは別途 sources.list を書き換えてから行います。

### パッケージインストール

```bash
apt-get update
apt-get install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl
```

| パッケージ | 役割 |
|-----------|------|
| `kubelet` | 各ノードで動くエージェント。kubelet が containerd に「このコンテナを起動して」と依頼 |
| `kubeadm` | クラスタブートストラップ用 CLI |
| `kubectl` | クラスタ操作用 CLI |
| `apt-mark hold` | これらを apt-get upgrade の対象から外す。**事故防止に必須** |

`apt-mark hold` を忘れると、ある日 `apt-get upgrade` で kubelet だけ minor バージョンが上がって、API Server とのバージョン差が許容範囲(±1 minor)を超えて死ぬ、ということが起こります。

### kubelet を起動準備状態に

```bash
systemctl enable --now kubelet
```

> このタイミングでは kubelet は **設定ファイルがないので CrashLoopBackOff** で起動と停止を繰り返します。これは正常な状態です。`kubeadm init` または `kubeadm join` の中で /var/lib/kubelet/config.yaml が作られた時点で起動が安定します。
>
> ```bash
> systemctl status kubelet
> # Active: activating (auto-restart) (Result: exit-code) ←これでOK
> ```

## Step4: k8s-lb で HAProxy + keepalived

`k8s-lb` ノードのみで実行します。

```mermaid
flowchart TB
    user[kubectl] --> vip[VIP 192.168.56.10:6443]
    vip --> hap[HAProxy<br>frontend k8s-api]
    hap --> backend[backend k8s-api-backend]
    backend -- TCP 6443 --> cp1[k8s-cp1]
    backend -- TCP 6443 --> cp2[k8s-cp2]
    backend -- TCP 6443 --> cp3[k8s-cp3]
    keep[keepalived<br>VRRP] -.VIP保持.-> hap
```

### HAProxy

```bash
apt-get install -y haproxy
```

`/etc/haproxy/haproxy.cfg`:

```
global
    log /dev/log local0
    log /dev/log local1 notice
    daemon
    maxconn 4096

defaults
    mode tcp
    log global
    option tcplog
    timeout connect 10s
    timeout client  60s
    timeout server  60s
    retries 3

frontend k8s-api
    bind *:6443
    mode tcp
    default_backend k8s-api-backend

backend k8s-api-backend
    mode tcp
    balance roundrobin
    option tcp-check
    server cp1 192.168.56.11:6443 check fall 3 rise 2
    server cp2 192.168.56.12:6443 check fall 3 rise 2
    server cp3 192.168.56.13:6443 check fall 3 rise 2

listen stats
    bind *:8404
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
```

各設定の意味:

| 行 | 意味 |
|----|------|
| `mode tcp` | L4 ロードバランス。kube-apiserver は TLS なので L7 解釈はせずに素通し |
| `balance roundrobin` | ラウンドロビン。`leastconn` も可だが apiserver は接続単価が低いので RR で十分 |
| `option tcp-check` | TCP 接続できるか確認。HTTP プローブも書けるが TCP で十分 |
| `fall 3` | 3 回連続失敗で down 扱い |
| `rise 2` | 2 回連続成功で up 扱い |
| `listen stats` | 8404 ポートで HAProxy 自体の統計画面 |

#### なぜ HAProxy なのか?

VIP に到達した API リクエストを 3 台の Control Plane に振り分ける必要があります。これを実現する代替手段:

| 手段 | メリット | デメリット |
|------|--------|-----------|
| **HAProxy** | 軽い、設定が直感的、TCP/HTTP両対応 | 単一障害点(対策に keepalived) |
| **NGINX (stream モジュール)** | HTTP も TCP も使える | TCP モードはやや影が薄い |
| **kube-vip** | K8s と統合、特別なノード不要 | やや新しい / トラブル時の情報量がまだ少ない |
| **MetalLB** | ARP/L2 でVIP保持 | apiserver が起動するまで使えない(=apiserver の手前で使えない) |
| **クラウド LB** | マネージド | クラウド前提、ローカルでは不可 |

本教材では HAProxy + keepalived の伝統的な組み合わせを使います。kube-vip は 9 章のおまけで紹介します。

```bash
systemctl enable --now haproxy
systemctl status haproxy
```

### keepalived(VRRP で VIP を持ち上げる)

VIP `192.168.56.10` は **`k8s-lb` 自身の IP と同じ** にしています。これは「k8s-lb が 1 台しかない」前提の簡略化。本格的に冗長化するなら lb1/lb2 の 2 台にして、ARP 切替で VIP を引き渡します。本教材ではここまでは踏み込みません。

```bash
apt-get install -y keepalived
```

`/etc/keepalived/keepalived.conf`:

```
vrrp_script chk_haproxy {
    script "/usr/bin/killall -0 haproxy"
    interval 2
    weight 2
}

vrrp_instance VI_1 {
    state MASTER
    interface ens33
    virtual_router_id 51
    priority 100
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass k8spass
    }
    virtual_ipaddress {
        192.168.56.10/24
    }
    track_script {
        chk_haproxy
    }
}
```

| キーワード | 意味 |
|-----------|------|
| `state MASTER` | 起動時から VIP を保持しようとする |
| `interface ens33` | VIP を載せる NIC(VM ごとに違うので確認) |
| `virtual_router_id 51` | 0-255 の任意の ID。同セグメントに別の VRRP がいたら被らせない |
| `priority 100` | 値の大きい方がマスター。バックアップは 99 などにする |
| `auth_pass` | VRRP メッセージの簡易認証 |
| `vrrp_script chk_haproxy` | HAProxy が落ちたら weight を変えて他に引き渡す(本教材では同一ホストなので意味は薄い) |

NIC 名の確認:

```bash
ip -br addr
# ens33 UP 192.168.56.10/24
```

```bash
systemctl enable --now keepalived

# VIP が乗っているか確認
ip addr show ens33 | grep '192.168.56.10'
```

## Step5: 1 台目の Control Plane 初期化

`k8s-cp1` で実行します。**ここが kubeadm の核心** です。

### kubeadm init コマンド

```bash
kubeadm init \
  --control-plane-endpoint "k8s-api:6443" \
  --upload-certs \
  --pod-network-cidr=10.244.0.0/16 \
  --service-cidr=10.96.0.0/12 \
  --kubernetes-version=v1.30.0 \
  --apiserver-advertise-address=192.168.56.11
```

各フラグの意味:

| フラグ | 必須 | 意味 |
|-------|------|------|
| `--control-plane-endpoint` | HA で必須 | API Server の表側 URL。VIP のホスト名を書く。生成証明書の SAN に入る |
| `--upload-certs` | HA で必須 | etcd / API Server / front-proxy 証明書を Secret に upload。他の CP から `--certificate-key` で受け取れる |
| `--pod-network-cidr` | CNI による | Pod に割り当てるサブネット。Calico / Flannel のデフォルトに合わせる |
| `--service-cidr` | 任意 | Service VIP のサブネット。デフォルト `10.96.0.0/12` |
| `--kubernetes-version` | 任意 | 明示すると `kubeadm` が公開バージョン取得をスキップして高速化 |
| `--apiserver-advertise-address` | NIC 複数時 | NAT NIC ではなく Host-only NIC を使うよう明示 |

危険なフラグ:

| フラグ | 危険性 |
|-------|--------|
| `--ignore-preflight-errors=all` | 全プリフライト無視。失敗を隠蔽するため学習の機会を失う。**使うな** |
| `--skip-phases=...` | 特定フェーズをスキップ。意味を分かってから使う |
| `--token-ttl=0` | トークンを永続化。本来 24 時間で失効するが永続にすると漏洩時のリスクが高い |

### kubeadm init の中身(phase 一覧)

`kubeadm init` は実は内部で複数の phase を順番に実行する複合コマンドです。

```mermaid
flowchart TB
    A[preflight<br>環境チェック] --> B[certs<br>PKI生成]
    B --> C[kubeconfig<br>各種kubeconfigファイル生成]
    C --> D[etcd<br>etcd Static Pod manifest]
    D --> E[control-plane<br>API/Scheduler/CM Static Pod]
    E --> F[upload-config<br>kubeadm-config ConfigMap]
    F --> G[upload-certs<br>--upload-certs時]
    G --> H[mark-control-plane<br>NoScheduleラベル]
    H --> I[bootstrap-token]
    I --> J[kubelet-finalize]
    J --> K[addon coredns + kube-proxy]
```

各 phase は `kubeadm init phase <name>` で個別に実行できます。学習用に分解して見るのもおすすめ:

```bash
kubeadm init phase preflight \
  --control-plane-endpoint=k8s-api:6443 \
  --apiserver-advertise-address=192.168.56.11
kubeadm init phase certs all
ls /etc/kubernetes/pki/
# apiserver.crt, apiserver-etcd-client.crt, ca.crt, etcd/, front-proxy-ca.crt, ...
```

### 期待される出力

```
[preflight] Running pre-flight checks
[preflight] Pulling images required for setting up a Kubernetes cluster
[certs] Using certificateDir folder "/etc/kubernetes/pki"
[certs] Generating "ca" certificate and key
... (中略) ...
[upload-certs] Storing the certificates in Secret "kubeadm-certs" in the "kube-system" Namespace
[upload-certs] Using certificate key:
abc123...

Your Kubernetes control-plane has initialized successfully!

To start using your cluster, you need to run the following as a regular user:
  mkdir -p $HOME/.kube
  sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
  sudo chown $(id -u):$(id -g) $HOME/.kube/config

You can now join any number of the control-plane node:
  kubeadm join k8s-api:6443 --token xxx \
    --discovery-token-ca-cert-hash sha256:yyy \
    --control-plane --certificate-key abc123...

Then you can join any number of worker nodes:
  kubeadm join k8s-api:6443 --token xxx \
    --discovery-token-ca-cert-hash sha256:yyy
```

**この出力をすべてコピーしておきます**(後で使う)。トークンと certificate-key は紛失すると面倒なので、安全な場所にメモ。

### kubectl 設定

```bash
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

kubectl get nodes
# NAME      STATUS     ROLES           AGE   VERSION
# k8s-cp1   NotReady   control-plane   1m    v1.30.0
```

`NotReady` は CNI が入っていないため。次のステップで解決します。

### init で失敗するパターン

| エラー | 原因 | 対処 |
|--------|------|------|
| `[ERROR Swap]: running with swap on is not supported` | swap 有効 | `swapoff -a` 忘れ |
| `[ERROR FileContent--proc-sys-net-bridge-bridge-nf-call-iptables]` | sysctl 未適用 | `/etc/sysctl.d/k8s.conf` 確認 |
| `[ERROR CRI]: container runtime is not running` | containerd 未起動 | `systemctl status containerd` |
| `[ERROR Port-6443]: Port 6443 is in use` | 既に動いている / リセット忘れ | `kubeadm reset -f` |
| `failed to pull image "registry.k8s.io/kube-apiserver:..."` | NAT NIC でインターネット出られず | NAT 確認、`/etc/resolv.conf` 確認 |
| `error execution phase wait-control-plane: couldn't initialize a Kubernetes cluster` | API Server が起動しない | `crictl ps -a`、`/var/log/pods/` 確認 |
| `the cluster is not exposed via the control-plane endpoint k8s-api` | `/etc/hosts` に `k8s-api` の行なし | `/etc/hosts` 修正 |

### init 失敗時のリカバリ

```bash
# 中途半端に作られたものを全部消す
kubeadm reset -f
rm -rf /etc/kubernetes /var/lib/etcd ~/.kube
iptables -F
iptables -t nat -F
ipvsadm --clear 2>/dev/null
```

`kubeadm reset` だけだと iptables ルールや CNI 設定が残ることがあるので、上記のフルクリーンが安全。

## Step6: CNI(Calico)のインストール

CNI を入れないと Pod 間通信ができず、`coredns` も Pending のままです。

### CNI とは

Container Network Interface。Pod に IP を振り、Pod 間ルーティングを実現するプラグイン仕様です。

```mermaid
flowchart LR
    kubelet --> cni[/CNI Plugin\n/]
    cni --> calico[Calico]
    cni --> flannel[Flannel]
    cni --> cilium[Cilium]
    cni --> weave[Weave]
    cni --> ovn[OVN-Kubernetes]
```

主要 CNI の比較:

| CNI | 特徴 | おすすめ用途 |
|-----|------|------------|
| **Calico** | BGP / VXLAN、NetworkPolicy 強力、eBPF 対応 | 本教材。中規模以上 |
| **Flannel** | シンプル、VXLAN 中心 | 学習用、小規模 |
| **Cilium** | eBPF ベース、性能高、可観測性 | 大規模、観測重視 |
| **Weave Net** | メッシュ。最近開発停止 | 新規不可 |
| **OVN-Kubernetes** | Open vSwitch ベース | OpenShift |
| **AWS VPC CNI** | EKS 専用、ENI 直接割当 | EKS |

本教材では Calico を選びます。理由:

- VXLAN / IP-in-IP / BGP の 3 モード切替で「ネットワーク層を自分で選んでいる感」が出る
- NetworkPolicy(第 5 章で扱った)が完全実装
- 学習リソースが豊富

### Calico のインストール

Tigera Operator 方式(推奨):

```bash
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.27.3/manifests/tigera-operator.yaml
```

これで `tigera-operator` Namespace に Operator が立ち上がります。次に `Installation` リソースを作って実体をデプロイ:

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: operator.tigera.io/v1
kind: Installation
metadata:
  name: default
spec:
  calicoNetwork:
    ipPools:
    - blockSize: 26
      cidr: 10.244.0.0/16
      encapsulation: VXLANCrossSubnet
      natOutgoing: Enabled
      nodeSelector: all()
EOF
```

| フィールド | 意味 |
|----------|------|
| `cidr` | `kubeadm init --pod-network-cidr` と一致させる |
| `blockSize: 26` | ノードあたり `2^(32-26)=64` IP を割当 |
| `encapsulation: VXLANCrossSubnet` | 異なるサブネット間のみ VXLAN、同セグメント内は直接 |
| `natOutgoing: Enabled` | Pod から外部への通信は SNAT してノード IP で出る |

### モード比較

```mermaid
flowchart TB
    subgraph vxlan[VXLAN モード]
      v1[Pod] --> v2[ノード] --> v3[VXLANカプセル化] --> v4[ノード] --> v5[Pod]
    end
    subgraph bgp[BGP モード]
      b1[Pod] --> b2[ノード] --> b3[ルーター/ノード経由でルーティング] --> b4[ノード] --> b5[Pod]
    end
```

| モード | メリット | デメリット |
|-------|--------|-----------|
| **VXLAN** | どこでも動く、L2/L3 関係なし | カプセル化のオーバーヘッド |
| **IP-in-IP** | VXLAN より軽量 | Linux のみ、UDP 4789 不要 |
| **BGP** | カプセル化なし、最速 | ルーター/上流 BGP 環境必要 |

ローカル学習では VXLAN が無難。本教材もこれ。

### 数分後に確認

```bash
kubectl get nodes
# NAME      STATUS   ROLES           AGE   VERSION
# k8s-cp1   Ready    control-plane   10m   v1.30.0

kubectl get pods -n kube-system
# coredns-...           Running   ←Calico入った後にRunning
# kube-apiserver-...    Running
# kube-controller-...   Running
# kube-proxy-...        Running
# kube-scheduler-...    Running

kubectl get pods -n calico-system
# calico-kube-controllers-...   Running
# calico-node-...               Running
# calico-typha-...              Running
```

## Step7: 残りの Control Plane を join

`k8s-cp2` と `k8s-cp3` で実行します。

```bash
kubeadm join k8s-api:6443 \
  --token xxx \
  --discovery-token-ca-cert-hash sha256:yyy \
  --control-plane \
  --certificate-key abc123 \
  --apiserver-advertise-address=192.168.56.12   # cp2 用、cp3 では .13
```

### 各フラグの意味

| フラグ | 意味 |
|-------|------|
| `--token` | 24 時間有効なトークン。`kubeadm token create` で作り直せる |
| `--discovery-token-ca-cert-hash` | 認証情報の正当性を SHA256 で検証 |
| `--control-plane` | Worker ではなく CP として参加 |
| `--certificate-key` | `--upload-certs` で uploadした証明書を取り出す鍵 |

certificate-key は **2 時間で失効** します。失効後は cp1 で再生成:

```bash
kubeadm init phase upload-certs --upload-certs
```

token はもっと頻繁に作り直されます:

```bash
kubeadm token create --print-join-command
# kubeadm join k8s-api:6443 --token ... --discovery-token-ca-cert-hash sha256:...
```

これに `--control-plane --certificate-key xxx` を付け足せば CP 用 join に。

### join 後の確認

```bash
kubectl get nodes
# NAME      STATUS   ROLES           AGE   VERSION
# k8s-cp1   Ready    control-plane   30m   v1.30.0
# k8s-cp2   Ready    control-plane   5m    v1.30.0
# k8s-cp3   Ready    control-plane   3m    v1.30.0
```

etcd メンバーシップ確認:

```bash
kubectl exec -n kube-system etcd-k8s-cp1 -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  member list
# 3 メンバー出るはず
```

## Step8: ワーカー参加

`k8s-w1` 〜 `k8s-w3` で:

```bash
kubeadm join k8s-api:6443 \
  --token xxx \
  --discovery-token-ca-cert-hash sha256:yyy
```

`--control-plane` を付けないので Worker として参加します。

### join の中身

```mermaid
sequenceDiagram
    participant W as Worker
    participant API as kube-apiserver (via VIP)
    W->>API: ブートストラップトークン認証
    API-->>W: クラスタ情報 (CA証明書など)
    W->>W: kubelet 用クライアント証明書を生成 (CSR)
    W->>API: CSR 提出
    API-->>W: 署名済み証明書
    W->>W: kubelet 設定ファイル作成、起動
    W->>API: ノード登録
```

### 期待される出力

```
[preflight] Running pre-flight checks
[preflight] Reading configuration from the cluster...
[kubelet-start] Starting the kubelet
[kubelet-start] Waiting for the kubelet to perform the TLS Bootstrap...

This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.
```

## Step9: 動作確認

```bash
kubectl get nodes -o wide
# NAME      STATUS   ROLES           AGE   VERSION   INTERNAL-IP     OS-IMAGE
# k8s-cp1   Ready    control-plane   1h    v1.30.0   192.168.56.11   Ubuntu 22.04
# k8s-cp2   Ready    control-plane   45m   v1.30.0   192.168.56.12   Ubuntu 22.04
# k8s-cp3   Ready    control-plane   40m   v1.30.0   192.168.56.13   Ubuntu 22.04
# k8s-w1    Ready    <none>          15m   v1.30.0   192.168.56.21   Ubuntu 22.04
# k8s-w2    Ready    <none>          14m   v1.30.0   192.168.56.22   Ubuntu 22.04
# k8s-w3    Ready    <none>          13m   v1.30.0   192.168.56.23   Ubuntu 22.04

kubectl get pods -A
# 全部 Running

kubectl get componentstatuses
# scheduler / controller-manager / etcd-0,1,2 が Healthy
```

### 疎通テスト

```bash
# 適当な Pod を立てて Pod 間通信確認
kubectl run busybox --image=busybox -- sleep 3600
kubectl exec busybox -- ping -c 3 8.8.8.8

# CoreDNS 名前解決
kubectl run -it --rm tmp --image=busybox -- nslookup kubernetes.default
# Server:    10.96.0.10
# Address:   10.96.0.10:53
# Name:      kubernetes.default.svc.cluster.local
# Address 1: 10.96.0.1
```

## Step10: MetalLB(LoadBalancer Service 用)

クラウドの ELB 相当をオンプレで提供する OSS。

### MetalLB がやること

```mermaid
flowchart TB
    user[ユーザ] --> vip2[VIP 192.168.56.200]
    vip2 -.ARP応答 / BGP広告.-> metallb[MetalLB Speaker]
    metallb --> svc[Service<br>type:LoadBalancer]
    svc --> pod1[Pod1]
    svc --> pod2[Pod2]
```

`type: LoadBalancer` の Service を作ると、MetalLB が `192.168.56.200-250` のプールから IP を割当て、その IP に対する ARP 応答(L2 モード)or BGP 広告(BGP モード)を行います。

### インストール

```bash
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.4/config/manifests/metallb-native.yaml
```

数分待ち、`metallb-system` Namespace の Pod がすべて Running になるのを確認。

```bash
kubectl wait --for=condition=Ready pods -n metallb-system --all --timeout=300s
```

### IP プール設定

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: default-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.56.200-192.168.56.250
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: default
  namespace: metallb-system
spec:
  ipAddressPools:
  - default-pool
```

### 動作確認

```bash
kubectl create deployment whoami --image=traefik/whoami
kubectl expose deployment whoami --port=80 --type=LoadBalancer
kubectl get svc whoami
# whoami   LoadBalancer   10.96.x.x   192.168.56.200   80:32xxx/TCP
```

ホスト PC から:

```bash
curl http://192.168.56.200/
# Hostname: whoami-...
# IP: 10.244.x.x
# RemoteAddr: 192.168.56.21:xxxx
```

### MetalLB のモード

| モード | 仕組み | メリット / デメリット |
|-------|-------|---------------------|
| **L2(ARP/NDP)** | あるノードが VIP の所有者になり、ARP 応答 | 設定が簡単 / そのノードに帯域が集中 |
| **BGP** | 各ノードがルーターに広告 | ECMP で負荷分散 / BGP ルーターが必要 |

ローカル環境では L2 モード一択。

## Step11: NFS サーバ + NFS-CSI(動的プロビジョニング)

PV / PVC を動的に作るために StorageClass が必要です。クラウドなら EBS-CSI などが標準ですが、オンプレでは自分で用意します。

### NFS サーバ構築(`k8s-nfs`)

```bash
apt-get install -y nfs-kernel-server
mkdir -p /export
chown nobody:nogroup /export
chmod 0777 /export
```

`/etc/exports`:

```
/export 192.168.56.0/24(rw,sync,no_subtree_check,no_root_squash,fsid=0)
```

| オプション | 意味 |
|----------|------|
| `rw` | 読み書き可 |
| `sync` | 同期書き込み(性能と引き換えに耐久性) |
| `no_subtree_check` | パフォーマンス向上 |
| `no_root_squash` | root の権限をそのまま保つ(本番では避けるが、PV のために必要) |

```bash
exportfs -arv
systemctl enable --now nfs-kernel-server
```

確認:

```bash
showmount -e localhost
# Export list for localhost:
# /export 192.168.56.0/24
```

各ノードで NFS クライアントを入れます:

```bash
# 全ノード(cp/worker)で
apt-get install -y nfs-common
```

### NFS-CSI ドライバ

```bash
helm repo add csi-driver-nfs https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/master/charts
helm install csi-driver-nfs csi-driver-nfs/csi-driver-nfs \
  --namespace kube-system \
  --version v4.7.0 \
  --set kubeletDir=/var/lib/kubelet
```

確認:

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=csi-driver-nfs
# csi-nfs-controller-...   Running
# csi-nfs-node-...         Running (各ノード分)
```

### StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.56.30
  share: /export
reclaimPolicy: Retain
volumeBindingMode: Immediate
allowVolumeExpansion: true
mountOptions:
- nfsvers=4.1
```

| フィールド | 意味 |
|----------|------|
| `is-default-class: "true"` | StorageClass を指定しない PVC は自動でこれが使われる |
| `reclaimPolicy: Retain` | PVC 削除でも PV 残す。Delete もあるが、データ事故防止に Retain 推奨 |
| `volumeBindingMode: Immediate` | PVC 作成と同時に PV 作成。`WaitForFirstConsumer` だと Pod スケジュールまで遅延 |
| `allowVolumeExpansion` | PVC のサイズ拡張を許可 |

### 動作確認

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
spec:
  accessModes: [ReadWriteMany]
  resources:
    requests:
      storage: 1Gi
```

```bash
kubectl apply -f test-pvc.yaml
kubectl get pvc
# NAME       STATUS   VOLUME           CAPACITY   ACCESS MODES   STORAGECLASS
# test-pvc   Bound    pvc-xxx          1Gi        RWX            nfs
```

NFS サーバ側:

```bash
ls /export/
# pvc-xxx-yyy/   ←PV 用ディレクトリが自動作成
```

## Step12: Docker Registry(`k8s-lb`)

サンプルアプリの自前イメージを置くため、`k8s-lb:5000` にレジストリを立てます。

```bash
# k8s-lb で
mkdir -p /var/lib/registry
docker run -d --restart=always --name registry \
  -p 5000:5000 \
  -v /var/lib/registry:/var/lib/registry \
  registry:2
```

> 簡略化のため Docker を `k8s-lb` で動かしています。systemd unit にしてもよいです。

クライアント側(イメージを push したい開発機)では `daemon.json` にこのレジストリを `insecure-registries` に登録するか、containerd の `hosts.toml` で `skip_verify = true` を設定する必要があります(Step2 で設定済み)。

```bash
# 開発機(WSL2でもmacでも)
docker pull nginx:1.27
docker tag nginx:1.27 192.168.56.10:5000/test:1
docker push 192.168.56.10:5000/test:1
```

`curl http://192.168.56.10:5000/v2/_catalog` で `{"repositories":["test"]}` が返れば OK。

## etcd バックアップ

K8s クラスタのすべての状態は etcd にあります。**etcd を失う = クラスタを失う**。バックアップは必須。

```bash
# k8s-cp1 で(任意の CP でよい)
mkdir -p /backup/etcd

ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save /backup/etcd/etcd-$(date +%Y%m%d-%H%M%S).db

# 確認
etcdctl --write-out=table snapshot status /backup/etcd/etcd-*.db
# +----------+----------+------------+------------+
# |   HASH   | REVISION | TOTAL KEYS | TOTAL SIZE |
# +----------+----------+------------+------------+
# | xxxxxxx  |  12345   |    678     |   3.4 MB   |
# +----------+----------+------------+------------+
```

### CronJob で定期バックアップ

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: etcd-backup
  namespace: kube-system
spec:
  schedule: "0 */6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          hostNetwork: true
          nodeSelector:
            node-role.kubernetes.io/control-plane: ""
          tolerations:
          - key: node-role.kubernetes.io/control-plane
            operator: Exists
            effect: NoSchedule
          containers:
          - name: backup
            image: registry.k8s.io/etcd:3.5.12-0
            command:
            - sh
            - -c
            - |
              etcdctl --endpoints=https://127.0.0.1:2379 \
                --cacert=/pki/etcd/ca.crt \
                --cert=/pki/etcd/server.crt \
                --key=/pki/etcd/server.key \
                snapshot save /backup/etcd-$(date +%Y%m%d-%H%M%S).db
              # 7 日以上前は削除
              find /backup -name "etcd-*.db" -mtime +7 -delete
            volumeMounts:
            - name: pki
              mountPath: /pki
              readOnly: true
            - name: backup
              mountPath: /backup
            env:
            - name: ETCDCTL_API
              value: "3"
          restartPolicy: OnFailure
          volumes:
          - name: pki
            hostPath:
              path: /etc/kubernetes/pki
          - name: backup
            hostPath:
              path: /backup/etcd
```

### リストア

実際にクラスタが壊れたとき:

```bash
# 全 CP で kubelet と etcd を停止
systemctl stop kubelet
crictl ps -a | grep etcd | awk '{print $1}' | xargs -r crictl stop

# 既存の etcd データを退避
mv /var/lib/etcd /var/lib/etcd.broken

# スナップショットからリストア
ETCDCTL_API=3 etcdctl snapshot restore /backup/etcd/etcd-20240301.db \
  --name k8s-cp1 \
  --initial-cluster k8s-cp1=https://192.168.56.11:2380,k8s-cp2=https://192.168.56.12:2380,k8s-cp3=https://192.168.56.13:2380 \
  --initial-cluster-token etcd-cluster-1 \
  --initial-advertise-peer-urls https://192.168.56.11:2380 \
  --data-dir /var/lib/etcd

# kubelet 再起動
systemctl start kubelet
```

リストアは **デリケート** です。すべての etcd メンバーで同じスナップショットからリストアし、同じ initial-cluster を指定する必要があります。

## クラスタアップグレード

K8s は 4 か月に 1 回 minor バージョンが上がります。アップグレード手順:

```mermaid
flowchart TB
    A[apt repo を v1.31 に変更] --> B[cp1 で kubeadm upgrade plan]
    B --> C[cp1 で kubeadm upgrade apply v1.31.0]
    C --> D[cp1 の kubelet/kubectl 更新]
    D --> E[cp2 で kubeadm upgrade node]
    E --> F[cp2 の kubelet/kubectl 更新]
    F --> G[cp3 同様]
    G --> H[各 worker で kubeadm upgrade node]
    H --> I[各 worker の kubelet/kubectl 更新]
```

### 1. リポジトリ切り替え

```bash
sed -i 's|v1.30|v1.31|' /etc/apt/sources.list.d/kubernetes.list
apt-get update
```

### 2. cp1 で kubeadm 更新

```bash
apt-mark unhold kubeadm
apt-get install -y kubeadm=1.31.0-1.1
apt-mark hold kubeadm

kubeadm upgrade plan
kubeadm upgrade apply v1.31.0
```

`upgrade plan` で「何が変わるか、何ができるか」を確認できる。失敗時は中断するのでドライラン的に使える。

### 3. cp1 のドレイン → kubelet 更新 → 再起動

```bash
# 別端末で
kubectl drain k8s-cp1 --ignore-daemonsets
```

```bash
# k8s-cp1 で
apt-mark unhold kubelet kubectl
apt-get install -y kubelet=1.31.0-1.1 kubectl=1.31.0-1.1
apt-mark hold kubelet kubectl
systemctl daemon-reload
systemctl restart kubelet
```

```bash
# 別端末で
kubectl uncordon k8s-cp1
```

### 4. cp2/cp3 で

```bash
apt-get install -y kubeadm=1.31.0-1.1
kubeadm upgrade node           # ← apply ではなく node
# 以下 kubelet 更新は同じ
```

### 5. 各 worker で

```bash
kubectl drain k8s-w1 --ignore-daemonsets --delete-emptydir-data
# w1 で:
apt-get install -y kubeadm=1.31.0-1.1
kubeadm upgrade node
apt-get install -y kubelet=1.31.0-1.1 kubectl=1.31.0-1.1
systemctl daemon-reload
systemctl restart kubelet
# 戻る:
kubectl uncordon k8s-w1
```

### バージョンスキューポリシー

K8s には「バージョン差はどこまで許容されるか」のルールがあります。

| | API Server | kubelet | kube-proxy |
|---|-----------|---------|-----------|
| API Server | 同じ | -3 minor まで前 | -3 minor まで前 |
| kubelet | -3 minor まで前 | - | 同じノード上で同 minor |

つまり API Server v1.30 → kubelet v1.27 はギリギリ。逆(kubelet が新しい)は **禁止**。

参考: [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)

## ノードの増減

### Worker 追加

```bash
# 新しい VM を作って Step1〜3 まで完了させ
kubeadm token create --print-join-command
# でトークンを発行、新ノードで kubeadm join 実行
```

### Worker 削除

```bash
kubectl drain k8s-w3 --ignore-daemonsets --delete-emptydir-data
kubectl delete node k8s-w3

# 削除する VM 側で
kubeadm reset -f
```

### Control Plane 削除

```bash
# まず etcd メンバーから外す
kubectl exec -n kube-system etcd-k8s-cp1 -- etcdctl member list
# ID を確認
kubectl exec -n kube-system etcd-k8s-cp1 -- etcdctl member remove <ID>

# ノード削除
kubectl delete node k8s-cp3

# cp3 側で
kubeadm reset -f
```

## トラブルシューティング

### Pod が起動しない一般的フロー

```mermaid
flowchart TB
    A[kubectl get pod] --> B{Status}
    B -->|Pending| C[kubectl describe pod<br>Events を見る]
    B -->|ImagePullBackOff| D[イメージ名 / レジストリ認証 / NW]
    B -->|CrashLoopBackOff| E[kubectl logs --previous]
    B -->|Running 0/1| F[Readiness Probe 失敗の可能性]
    C --> C1{原因}
    C1 -->|FailedScheduling Resources| G[ノード資源不足 / Requests 過大]
    C1 -->|FailedScheduling NoNodes| H[Taint / nodeSelector 確認]
    C1 -->|FailedAttachVolume| I[PVC / StorageClass 確認]
    C1 -->|FailedCreatePodSandBox| J[CNI / containerd 確認]
```

### よくあるエラー対応表

| エラー | 場所 | 原因 | 対処 |
|--------|------|------|------|
| `node "xxx" not found` | kubeadm join | VIP に到達できない | `nslookup k8s-api`、HAProxy 確認 |
| `Get https://k8s-api:6443/...: x509: certificate signed by unknown authority` | join | 古い ca.crt を持っている | reset、token 再発行 |
| `Unable to register node ...` | kubelet | API Server に届かない | NW、kubelet config の server URL 確認 |
| `failed to set up sandbox container ...: Operation not permitted` | Pod | AppArmor / SELinux | `aa-status`、`getenforce` |
| `nfs: rpc-statd is not running but is required for remote locking` | Pod (NFS PVC) | nfs-common 未インストール | `apt-get install nfs-common` |
| `0/3 nodes are available: 3 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }` | スケジューラ | toleration 不足 | toleration 追加 or worker でデプロイ |

### kubelet の調査

```bash
# ノードに ssh して
journalctl -u kubelet -n 200 --no-pager
journalctl -u kubelet -f               # follow

# kubelet の設定
cat /var/lib/kubelet/config.yaml

# kubelet が見ているコンテナ一覧
crictl ps -a
crictl logs <CONTAINER_ID>
```

### API Server の調査

API Server は Static Pod です。

```bash
# k8s-cp1 で
crictl ps | grep apiserver
crictl logs <APISERVER_CONTAINER_ID>

# Static Pod の manifest
ls /etc/kubernetes/manifests/
# etcd.yaml  kube-apiserver.yaml  kube-controller-manager.yaml  kube-scheduler.yaml

# manifest を編集して保存すると自動で再起動(kubelet が監視)
vi /etc/kubernetes/manifests/kube-apiserver.yaml
```

### etcd の調査

```bash
kubectl exec -n kube-system etcd-k8s-cp1 -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
# https://127.0.0.1:2379 is healthy: ...

# クラスタ全体
kubectl exec -n kube-system etcd-k8s-cp1 -- etcdctl \
  --endpoints=https://192.168.56.11:2379,https://192.168.56.12:2379,https://192.168.56.13:2379 \
  --cacert=... --cert=... --key=... \
  endpoint status --write-out=table
```

### よくある事象別フローチャート

#### 「kubectl が応答しない」

```mermaid
flowchart TB
    A[kubectl get nodes が刺さる] --> B{ping k8s-api}
    B -->|失敗| C[VIP 確認: ip addr on k8s-lb]
    B -->|成功| D{nc k8s-api 6443}
    D -->|失敗| E[HAProxy 落ちてる: systemctl status haproxy]
    D -->|成功| F{API Server 応答?}
    F -->|失敗| G[CP1 で crictl ps grep apiserver]
    G -->|落ちてる| H[crictl logs / journalctl -u kubelet]
    G -->|起動中| I[etcd 死んでないか確認]
```

#### 「Pod が ContainerCreating で止まる」

```mermaid
flowchart TB
    A[ContainerCreating] --> B[kubectl describe pod]
    B --> C{Events}
    C -->|FailedCreatePodSandBox| D[CNI 設定 missing]
    D --> D1[ls /etc/cni/net.d/ で .conflist 存在確認]
    C -->|MountVolume.SetUp failed| E[PV / PVC]
    E --> E1[kubectl get pvc / pv]
    C -->|ImagePullBackOff| F[イメージ名 / 認証]
    F --> F1[crictl pull で手動 pull テスト]
```

## トラブル時のフルリセット

```bash
# 全ノードで
kubeadm reset -f
rm -rf /etc/kubernetes /var/lib/etcd ~/.kube /etc/cni/net.d
iptables -F
iptables -t nat -F
iptables -t mangle -F
iptables -X
ipvsadm --clear 2>/dev/null
ip link delete cni0 2>/dev/null
ip link delete flannel.1 2>/dev/null
ip link delete vxlan.calico 2>/dev/null
systemctl restart containerd
```

スナップショットから巻き戻すのが一番楽。VMware Workstation の「Snapshot Manager」で **構築前 / Step5 直後 / 完了後** の 3 箇所を取る運用がオススメ。

## ハンズオン:サンプルアプリのデプロイ

クラスタが組めたら、ミニ TODO サービスをこのクラスタにデプロイしてみます。詳細は他のページで深掘りするので、ここでは「動くこと」確認のみ。

### Namespace 作成

```bash
kubectl create namespace todo
kubectl config set-context --current --namespace=todo
```

### PostgreSQL (StatefulSet)

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  labels:
    app.kubernetes.io/name: postgres
    app.kubernetes.io/part-of: todo
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
      containers:
      - name: postgres
        image: postgres:16
        env:
        - name: POSTGRES_DB
          value: todo
        - name: POSTGRES_USER
          value: todo
        - name: POSTGRES_PASSWORD
          value: todo-pass
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: nfs
      resources:
        requests:
          storage: 5Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: postgres
  ports:
  - port: 5432
```

### API Deployment(最小)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: todo-api
  labels:
    app.kubernetes.io/name: todo-api
    app.kubernetes.io/part-of: todo
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: todo-api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: todo-api
        app.kubernetes.io/part-of: todo
    spec:
      containers:
      - name: api
        image: 192.168.56.10:5000/todo-api:0.1.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          value: postgres://todo:todo-pass@postgres:5432/todo
---
apiVersion: v1
kind: Service
metadata:
  name: todo-api
spec:
  selector:
    app.kubernetes.io/name: todo-api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

```bash
kubectl apply -f postgres.yaml
kubectl apply -f api.yaml
kubectl get pods -w
kubectl get svc todo-api
# todo-api  LoadBalancer  10.96.x.x  192.168.56.201  80:32xxx/TCP
curl http://192.168.56.201/api/health
```

これで「自前構築したクラスタでアプリが動いた」状態に。

## セキュリティ強化(本番に向けて)

学習用クラスタを「本番に近づける」ために、以下を順次入れていきます(本章の他のページで詳述)。

| 項目 | 対応ページ |
|------|----------|
| Probe で死活監視 | `probe.md` |
| Resources で QoS 制御 | `resources.md` |
| HPA で水平スケール | `autoscaling.md` |
| PDB で安全なメンテナンス | `scheduling.md` |
| RBAC | 第 5 章 |
| NetworkPolicy | 第 5 章 |
| Pod Security Standards | 第 8 章 |
| 監査ログ(audit log) | 第 9 章 |
| イメージ脆弱性スキャン(Trivy) | 第 9 章 |

## チェックポイント

- [ ] HA 構成の kubeadm クラスタを自分で組める
- [ ] etcd の Raft クォーラムの考え方と、奇数台にする理由を説明できる
- [ ] HAProxy + keepalived の役割を図で説明できる
- [ ] CRI と OCI の違い、containerd と runc の関係を説明できる
- [ ] `kubeadm init` の各 phase が何をしているか言える
- [ ] Calico / MetalLB / NFS-CSI を入れて動作確認できる
- [ ] `apt-mark hold kubelet kubeadm kubectl` の意味を説明できる
- [ ] `--upload-certs` と `--certificate-key` の関係を説明できる
- [ ] etcd のスナップショット取得とリストア手順を実行できる
- [ ] `kubeadm reset` で何が消え、何が残るかを把握している
- [ ] バージョンスキューポリシーを踏まえた upgrade 手順を説明できる
- [ ] Pod が ContainerCreating で止まったときの調査フローを説明できる

→ 次は [Probe (Liveness/Readiness/Startup)]({{ '/07-production/probe/' | relative_url }})
