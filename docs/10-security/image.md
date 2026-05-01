---
title: イメージセキュリティ
parent: 10. セキュリティ
nav_order: 4
---

# イメージセキュリティ
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

コンテナイメージは攻撃の主要侵入経路。**スキャン・署名・許可** の三本柱で守ります。

## 1. 脆弱性スキャン

`Trivy` がデファクトスタンダード。

```bash
# CIで
trivy image --severity CRITICAL,HIGH --exit-code 1 ghcr.io/<USER>/todo-api:1.2.3

# クラスタ内で常時運用 (Trivy Operator)
helm install trivy-operator aquasec/trivy-operator -n trivy-system --create-namespace
```

Trivy Operator は CRD `VulnerabilityReport` / `ConfigAuditReport` を Pod ごとに作るので、Grafana で可視化したり、Falco/Alertmanagerでアラート化できます。

## 2. 署名と検証 (Sigstore)

イメージが「想定した場所で・想定したCIで・想定したコミットから」作られたかを検証する仕組み。
`cosign` で署名。

```bash
# CIで署名
cosign sign --yes \
  --identity-token=$ID_TOKEN \
  ghcr.io/<USER>/todo-api:1.2.3

# Kubernetes 側で検証 (Kyverno + cosign)
```

Kyverno でクラスタに入る前に検証:

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-images
spec:
  validationFailureAction: Enforce
  rules:
  - name: verify-cosign-signature
    match:
      any:
      - resources:
          kinds: [Pod]
    verifyImages:
    - imageReferences:
      - "ghcr.io/<USER>/todo-*"
      attestors:
      - count: 1
        entries:
        - keyless:
            subject: "https://github.com/<USER>/todo-app/.github/workflows/ci.yaml@*"
            issuer: "https://token.actions.githubusercontent.com"
```

「GitHub Actions の自社CIで作られたイメージしか動かさない」をクラスタで強制できます。

## 3. SBOM (Software Bill of Materials)

イメージに含まれるパッケージのリスト。SLSA や SBOM 添付要件を満たすために生成・添付する。

```bash
syft ghcr.io/<USER>/todo-api:1.2.3 -o spdx-json > sbom.spdx.json
cosign attest --predicate sbom.spdx.json --type spdx ghcr.io/<USER>/todo-api:1.2.3
```

## 4. Distroless / Minimal イメージ

ベースイメージを小さくすると **CVE の数が劇的に減る**。

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --target=/deps .

FROM gcr.io/distroless/python3-debian12
WORKDIR /app
COPY --from=builder /deps /deps
COPY app/ ./app/
ENV PYTHONPATH=/deps
USER nonroot
ENTRYPOINT ["python","-m","app.main"]
```

注意:

- Distroless には shell がないので、`exec` で入っての調査が困難
- そのトレードオフを understand したうえで採用

## 5. Admission control での "policy as code"

クラスタに入れるイメージそのものを policy で絞り込む。

- 信頼できるレジストリだけ許可
- `latest` タグを禁止
- コミット SHA タグを必須

これらは Kyverno / Gatekeeper / OPA で実装可能。

## チェックポイント

- [ ] Trivy Operator が解決する課題
- [ ] cosign での keyless 署名がもたらす利点
- [ ] Distroless 採用のメリット・デメリット
