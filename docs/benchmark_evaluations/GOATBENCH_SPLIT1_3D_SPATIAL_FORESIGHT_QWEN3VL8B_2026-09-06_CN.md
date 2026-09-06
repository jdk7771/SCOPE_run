# 3D-Spatial-Foresight：GOAT-Bench Split 1 运行结果

## 运行设置

- 代码：`feat/3d-spatial-foresight`（`7826ab2`），基于 `feat/semantic-bev-dedupe-smoothing`，保留 5 cm TSDF、structured semantic/gaussian BEV，并启用 3D spatial foresight。
- VLM：本地 Ollama `qwen3-vl:8b-instruct`；未使用 OpenAI API。
- 基准：GOAT-Bench `val_unseen`，Split 1，36 episodes / **278 tasks**。
- 并行：GPU5 运行 `[0.00, 0.50]`（133 tasks），GPU7 运行 `[0.50, 1.00]`（145 tasks）；按 task ID 合并后无重复、无缺失。
- 为控制存储，关闭持久化可视化与 VLM 输入包；运行时仍会临时生成模型决策必需的图像。

## 结果

| 目标类型 | Tasks | Snapshot success | Distance success | Snapshot SPL（见下方说明） | Distance SPL（见下方说明） |
| --- | ---: | ---: | ---: | ---: | ---: |
| **总体** | **278** | **33.09%** | **57.55%** | 24.90% | 41.31% |
| description | 91 | — | **41.76%** | — | — |
| image | 88 | — | **63.64%** | — | — |
| object | 99 | — | **66.67%** | — | — |

“—”表示本次未按该目标类型单独汇总该指标。

## 运行时间

两个分片近乎同时启动，端到端用时由较慢的 GPU5 分片决定。

| 分片 | GPU | Tasks | 运行时间 | 成功 VLM 请求 / 总请求 | 单次成功 VLM 请求平均时间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `[0.00, 0.50]` | GPU5 | 133 | 18:27:59 | 6,642 / 7,167 | 6.119 s |
| `[0.50, 1.00]` | GPU7 | 145 | 16:29:53 | 6,366 / 6,716 | 4.673 s |
| **合计 / 关键路径** | GPU5 + GPU7 | **278** | **18:27:59**（端到端） | **13,008 / 13,883** | — |
| **合计 GPU 运行时间** | GPU5 + GPU7 | — | **34:57:52** | — | — |

单次 VLM 请求时间仅表示模型请求本身，不等于单 task 的总耗时。

## SPL 限制与结论

278 条任务中有 2 条的 GT 探索距离为 0。当前继承的记录器按 `success × gt_dist / max(gt_dist, explored_dist)` 计算，导致 `0 / 0`，原始 `np.mean` 汇总会得到 `NaN`。表中的 SPL 是排除这 2 条未定义值后对其余 **276 tasks** 的均值；若将未定义值保守记为 0，则 Snapshot / Distance SPL 分别为 **24.72% / 41.01%**。

因此，本次 Split 1 的任务覆盖和 success 指标有效；SPL 在明确零长度任务的统一处理规则前，不应作为与其他实验或论文的正式比较结论。本次记录仅报告该配置的单次结果，并不宣称相对 baseline 的提升。
