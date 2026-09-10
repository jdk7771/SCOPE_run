# 3D-Spatial-Foresight：GOAT-Bench Split 1 运行结果（Gemma3 27B）

## 运行设置

- 代码：`feat/3d-spatial-foresight`（`7826ab2`），5 cm TSDF，启用 structured semantic/gaussian BEV 与 3D spatial foresight。
- VLM：本地 Ollama `gemma3:27b`；未使用 OpenAI API。
- 基准：GOAT-Bench `val_unseen`，Split 1，36 episodes、**278 tasks**。
- 使用两张 GPU 并行完成整个 Split 1；结果按全部 278 tasks 汇总。

## 结果

| 总体指标 | 结果 |
| --- | ---: |
| Tasks | **278** |
| Snapshot success | **24.46%** |
| Distance success | **47.84%** |
| Snapshot SPL（见下方说明） | 15.43% |
| Distance SPL（见下方说明） | 28.16% |

| 目标类型 | Tasks | Distance success |
| --- | ---: | ---: |
| description | 91 | **32.97%** |
| image | 88 | **35.23%** |
| object | 99 | **72.73%** |

## 运行时间

| 范围 | Tasks | 端到端运行时间 | 成功 VLM 请求 / 总请求 |
| --- | ---: | ---: | ---: |
| **GOAT-Bench Split 1 整体** | **278** | **47:04:13** | **34,322 / 34,322** |

单次 VLM 请求时间仅表示模型请求本身，不等于单 task 的总耗时。

## SPL 说明

4 条 task 的 SPL 记录为未定义值（`0 / 0`）。表中的 Snapshot / Distance SPL 均为排除这 4 条后、其余 **274 tasks** 的非 NaN 均值。
