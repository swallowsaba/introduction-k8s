---
title: DNSとサービスディスカバリ
parent: 04. ネットワーキング
nav_order: 4
---

# DNSとサービスディスカバリ
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

Kubernetes は **CoreDNS** が `kube-system` に常駐し、Service / Pod の名前解決を提供します。

## DNS 名

| リソース | DNS |
|----------|-----|
| Service | `<service>.<namespace>.svc.cluster.local` |
| Pod (StatefulSet) | `<pod>.<service>.<namespace>.svc.cluster.local` |
| Pod (一般) | `<pod-ip-with-dashes>.<namespace>.pod.cluster.local` |

短縮:

- 同 Namespace: `web`
- 別 Namespace: `web.prod`
- 完全修飾: `web.prod.svc.cluster.local`

## /etc/resolv.conf

Pod 内では:

```
search prod.svc.cluster.local svc.cluster.local cluster.local
nameserver 10.96.0.10
options ndots:5
```

`ndots:5` により、4個以内のドットしかない名前は **search にあるサフィックスを順に試す** 動きをします。
これが「外部DNSへの解決が遅い」現象の原因になることがあるので、外部ホスト名は **末尾に `.` を付けて FQDN** にすると無駄な検索を避けられます。

## CoreDNS の Corefile

```bash
kubectl get configmap coredns -n kube-system -o yaml
```

`Corefile` で動作を変更可能。
たとえば社内 DNS への転送ゾーンを足すなど。

## Headless Service の DNS

`clusterIP: None` の Service は、DNS で **背後の全 Pod IP** を返します。

```bash
nslookup postgres
# Returns multiple A records (IPs of postgres-0, postgres-1, ...)
```

StatefulSet の各 Pod も DNS 名を持ちます:

```
postgres-0.postgres.prod.svc.cluster.local
postgres-1.postgres.prod.svc.cluster.local
```

## ExternalName Service

外部DNSへのCNAME。

```yaml
apiVersion: v1
kind: Service
metadata:
  name: legacy-db
spec:
  type: ExternalName
  externalName: db.example.com
```

クラスタ内から `legacy-db` で外部の `db.example.com` を引けるようになります。

## チェックポイント

- [ ] 別 Namespace の Service を引く DNS 名を書ける
- [ ] StatefulSet の各 Pod を直接指す DNS 名を書ける
- [ ] `ndots:5` がもたらす副作用を説明できる
