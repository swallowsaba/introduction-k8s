---
title: 05. ストレージ
nav_order: 6
has_children: true
permalink: /05-storage/
---

# 05. ストレージ

Pod は揮発するので、永続データを扱うには **PersistentVolume (PV)** と **PersistentVolumeClaim (PVC)** の仕組みを使います。
本章では Volume の種類、PV/PVC の動的プロビジョニング、StatefulSet との組み合わせまでを学びます。
