# 3D-Spatial-Foresight：GOAT-Bench Split 1 运行结果

## 运行设置

- 代码：`feat/3d-spatial-foresight`（`7826ab2`），基于 `feat/semantic-bev-dedupe-smoothing`，保留 5 cm TSDF、structured semantic/gaussian BEV，并启用 3D spatial foresight。
- VLM：本地 Ollama `qwen3-vl:8b-instruct`；未使用 OpenAI API。
- 基准：GOAT-Bench `val_unseen`，Split 1，36 episodes / **278 tasks**。
- 并行：GPU5 运行 `[0.00, 0.50]`（133 tasks），GPU7 运行 `[0.50, 1.00]`（145 tasks）；按 task ID 合并后无重复、无缺失。
- 为控制存储，关闭持久化可视化与 VLM 输入包；运行时仍会临时生成模型决策必需的图像。

## 结果

| 指标 | 结果 |
| --- | ---: |
| Snapshot success | **33.09%** |
| Distance success | **57.55%** |
| Snapshot SPL（见下方说明） | 24.90% |
| Distance SPL（见下方说明） | 41.31% |

按目标类型的 Distance success：description **41.76%**（91 tasks）、image **63.64%**（88 tasks）、object **66.67%**（99 tasks）。

## 运行时间

两个分片近乎同时启动；端到端关键路径为 GPU5 的 **18:27:59**，GPU7 用时 **16:29:53**，合计 GPU 运行时间 **34:57:52**。单次成功 VLM 请求的平均耗时分别为 GPU5 **6.119 s**（6,642 / 7,167）和 GPU7 **4.673 s**（6,366 / 6,716）；该值仅表示单个模型请求，不等于单 task 总耗时。

## SPL 限制与结论

278 条任务中有 2 条的 GT 探索距离为 0。当前继承的记录器按 `success × gt_dist / max(gt_dist, explored_dist)` 计算，导致 `0 / 0`，原始 `np.mean` 汇总会得到 `NaN`。表中的 SPL 是排除这 2 条未定义值后对其余 **276 tasks** 的均值；若将未定义值保守记为 0，则 Snapshot / Distance SPL 分别为 **24.72% / 41.01%**。

因此，本次 Split 1 的任务覆盖和 success 指标有效；SPL 在明确零长度任务的统一处理规则前，不应作为与其他实验或论文的正式比较结论。本次记录仅报告该配置的单次结果，并不宣称相对 baseline 的提升。

