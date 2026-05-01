---
title: 07. 本番運用
nav_order: 8
has_children: true
permalink: /07-production/
---

# 07. 本番運用

ここからが本教材の核心です。
VMware Workstation 上に kubeadm で **HA構成のクラスタを自前構築** し、Probe・リソース管理・Autoscaling・Helm/Kustomize までを段階的に学びます。

本章を読み終えると、

- マスター3 + ワーカー3 の HA クラスタを kubeadm で構築できる
- 適切な Probe とリソース要求を設計できる
- HPA / VPA / Cluster Autoscaler の役割を理解できる
- Helm Chart 化、Kustomize 化したサンプルアプリをデプロイできる

状態になります。
