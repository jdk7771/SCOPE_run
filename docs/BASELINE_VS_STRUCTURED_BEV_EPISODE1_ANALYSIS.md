# Baseline 与结构化 BEV VLM：单 Episode 分析

## 对比范围与可复现性

两份结果使用同一个 GOAT-Bench scene 和同一个 episode。

| 运行 | 分支 | 结果目录 | Scene / Episode | Subtask 数 |
| --- | --- | --- | --- | --- |
| Baseline | `fix/stale-snapshot-object-ids` | `results/episode1_baseline_time` | `00848-ziup5kvtCCR_ep_0` | 9 |
| Structured BEV | `feat/hsgm-structured-bev-vlm` | `results/episode1_scope_bev` | `00848-ziup5kvtCCR_ep_0` | 9 |

两次运行均正常结束，并使用本地 `gemma3:27b` VLM 服务。这只是一个 episode 的诊断性对比，不能作为具有统计显著性的 benchmark 结论。

## 相对 Baseline 改动了什么

结构化 BEV 分支**没有把 SCOPE 的建图或局部导航替换为 HSGM**。它仍然使用 SCOPE 的 TSDF 地图、SCOPE 的 frontier 打分/规划，以及 SCOPE 的下层执行。“HSGM-style”仅描述可视化和输入 VLM 的地图表达形式。

| 模块 | Baseline | Structured-BEV 分支 |
| --- | --- | --- |
| 建图和局部导航 | SCOPE TSDF 与 SCOPE planner | 仍为 SCOPE TSDF 与 SCOPE planner |
| 输入 VLM 的语义地图 | 没有俯视语义 BEV | 结构化语义 BEV：agent 位姿/朝向、已探索和已观测区域、轨迹、F1/F2/F3、筛选后的语义标签 |
| 未观测区域证据 | 没有 BEV evidence field | Gaussian evidence BEV：中心为候选 frontier，权重来自 SCOPE 的未来证据/子任务相关性预测，宽度表示不确定性 |
| Frontier 呈现 | Frontier 缩略图和 SCOPE 分数 | 仍使用 SCOPE 分数排序，但 F1/F2/F3 在两张 BEV 和 prompt 中保持一致 |
| VLM 决策协议 | 文本选择，由 SCOPE 解析 | 显式 JSON：候选点/物体选择、决策类型、子任务状态、原因、置信度 |
| 可追溯性和计时 | 常规运行日志 | 完整 VLM 输入包记录两张 BEV；`vlm_timing.json` 记录每个 API 请求 |

重要混杂因素：结构化 BEV 运行使用 `tsdf_grid_size: 0.05`，baseline 使用 `0.1`。因此当前比较衡量的是“结构化 BEV/prompt 改动 + 更细 TSDF 网格”的联合效果，**不是严格的仅 BEV 消融实验**。

## 导航结果

| 指标 | Baseline | Structured BEV | 差值 |
| --- | ---: | ---: | ---: |
| Snapshot success | 11.11% (1/9) | 11.11% (1/9) | 0.00 pp |
| Snapshot SPL | 9.17% | 9.63% | +0.46 pp |
| Distance success | 33.33% (3/9) | 44.44% (4/9) | +11.11 pp |
| Distance SPL | 31.39% | 39.86% | +8.47 pp |
| 总运行时间 | 19:29 | 33:25 | +13:56 |

在这个 episode 中，Structured BEV 多到达了一个目标视点，并获得更高的 distance SPL。严格的 snapshot 正确性仍然都是一个 subtask 成功，且两边成功的 subtask 并不相同。因此，这说明它在此 episode 中产生了不同、且在 distance 指标上更好的轨迹；但不能据此证明语义目标选择能力已经普遍提升。

## 为什么 Structured-BEV 运行时间更长

两张 BEV 图被放在**同一次**最终决策请求中；它们不会让一次决策自动变成两次额外 VLM 请求。主要原因是结构化 BEV 运行触发了更多高层重规划事件。

两边均启用 `choose_every_step: true`。可将一次 `prefilter` 近似看作一次高层决策事件：robot 到达局部目标、更新观测/地图后，需要再次询问 VLM 是去已有 snapshot，还是继续探索哪个 frontier。

| VLM 调用类型 | Baseline | Structured BEV | 含义 |
| --- | ---: | ---: | --- |
| `prefilter` | 11 | 24 | 约 24 次 vs. 11 次高层决策事件 |
| `decision` | 36 | 75 | 最终选择请求，包含必要的重试 |
| `self_refine` | 27 | 25 | Snapshot 验证请求；不是次数增加的来源 |
| `frontier_potential` | 22 | 36 | 新 frontier 的潜力评估更多 |
| **API 请求总数** | **96** | **160** | **+64 请求** |

每次高层事件的最终选择尝试比例相近：baseline 为 `36 / 11 = 3.27`，Structured BEV 为 `75 / 24 = 3.13`。因此没有证据表明 JSON 协议导致了额外的格式错误重试。请求总数增加主要来自更多决策/重规划事件；这与 Structured BEV 每个 subtask 更多的平均 snapshot 数（20.67 vs. 15.56）和平均 frame 数（77.44 vs. 72.11）一致。更细的 TSDF 网格也可能改变 frontier 几何形状与路径。

网格大小是地图分辨率，不是物理移动步长。planner 的局部目标距离由独立参数控制；但是更细的地图仍然可能产生不同的 frontier 序列和重规划过程。

## 为什么单次 VLM 响应更快，但完整运行更慢

| 调用类型 | Structured BEV 平均值 | Baseline 平均值 | 差值 |
| --- | ---: | ---: | ---: |
| 所有成功请求 | 7.286 s (160) | 8.443 s (96) | -1.157 s |
| `decision` | 10.781 s (75) | 15.330 s (36) | -4.548 s |
| `frontier_potential` | 5.764 s (36) | 5.811 s (22) | -0.047 s |
| `prefilter` | 2.017 s (24) | 2.063 s (11) | -0.046 s |
| `self_refine` | 4.051 s (25) | 4.004 s (27) | +0.047 s |

Structured-BEV prompt 要求输出紧凑 JSON，而 baseline 常生成更长的自然语言选择/解释。本地 VLM 服务上，生成 token 更少是 `decision` 平均延迟更低的一个合理解释。但这不能证明 BEV 图使推理更快：服务负载/缓存、不同的 snapshot 集合和输出长度都会影响延迟。

尽管单次响应更快，Structured BEV 因为调用更多而等待了更长的 VLM 时间：

- Baseline 的 VLM 请求总时间：约 810.5 s（13:31）。
- Structured-BEV 的 VLM 请求总时间：约 1165.8 s（19:26）。

其余墙钟时间增加来自更多重规划循环带来的额外观测、检测、点云/TSDF 更新、frontier 评估与可视化工作。

## 建议的严格下一轮实验

建议对所有 36 个 scene 的 Episode 1 做统一设置的实验：两边使用相同 `tsdf_grid_size`（第一轮建议均为 0.1）、相同 planner/detector/extra-view/visualization/VLM 配置、独立且全新的输出目录，并尽可能保持相同的 VLM 服务状态。使用 `scripts/compare_vlm_timing.py` 对比生成的 `vlm_timing.json`。只有这样，聚合 success/SPL、总运行时间、决策事件数量和单请求延迟才能作为结构化 BEV 设计决策的依据。
