# A-EQA：5 cm baseline vs semantic-BEV dedupe+smoothing

整理日期：2026-08-20  
性质：A-EQA 官方 184-question 子集上的 SCOPE 5 cm baseline 与 semantic-BEV dedupe+smoothing 对照  
状态：两组均已完成，184/184。

对应结果文件：

| 方法 | 代码分支 | 固定提交 | 正式结果目录 |
| --- | --- | --- | --- |
| 5 cm baseline | `feat/aeqa-baseline` | `c28b023` | `/data1/jiangdakun/scope_results/aeqa_baseline_5cm_184/` |
| semantic-BEV dedupe+smoothing | `feat/aeqa-semantic-bev-dedupe-smoothing` | `c72af42` | `/data1/jiangdakun/scope_results/aeqa_semantic_bev_dedupe_smoothing_5cm_184_gpu0_ollama/` |

## 1. 这个实验回答什么问题

本实验回答的是：

> 在同样使用 5 cm TSDF、同一份 A-EQA 184 题、同一 SCOPE 对象建图/snapshot/frontier/导航流程的前提下，向高层 VLM 决策额外输入经过 TSDF 支撑、实例去重和显示平滑的 semantic BEV，是否能提高 SCOPE 完成 A-EQA snapshot 目标的比例，并减少成功 episode 的探索距离？

这是一组有意义的 SCOPE 内部对照。它验证的是「结构化 semantic BEV（包含 dedupe+smoothing）」这一整组输入表示，而不是只将最后一个 dedupe/smoothing 函数单独开关的纯消融。

结论：semantic-BEV dedupe+smoothing 版本相对同条件 5 cm SCOPE baseline，将 snapshot/navigation success 从 79.89% 提升到 83.70%（+3.80 pp），并将成功 episode 的平均探索路径从 5.595 m 降至 4.098 m。逐题对照中，semantic 版本额外解决 13 题，同时仅在 6 题上由成功变为失败。这支持将 TSDF-supported、deduplicated 和 smoothed semantic BEV 作为高层 VLM 的空间上下文。

这里的 3.80 pp 是 snapshot/navigation success，而不是经过统一答案评测器得到的最终 QA accuracy；也不能将收益只归因于 dedupe+smoothing，因为输入给 VLM 的是包含 TSDF support、实例过滤、去重、平滑、轨迹和 frontier 对齐的整张结构化 semantic BEV。

## 2. 公平性检查

两组共享以下条件：

| 条件 | 设置 |
| --- | --- |
| 题目 | `/data1/jiangdakun/datasets/aeqa/aeqa_questions-184.json`，184 题 |
| 场景 | `/data1/jiangdakun/hm3d` |
| TSDF | 0.05 m |
| 探索预算 | 最多 50 steps；首步 7 views，后续每步 3 views |
| 检测/分割/表征 | YOLO-World、SAM、CLIP ViT-B/32 |
| 决策 VLM | `gemma3:27b`，OpenAI-compatible Ollama endpoint |
| 随机种子 | 3407 |

运行资源隔离：baseline 使用 GPU4 + Ollama `11435`，semantic 使用 GPU0 + Ollama `11436`。这避免了两组共享一个 Ollama 队列；两边仍使用相同 Gemma 模型和同一套调用参数。

## 3. 核心结果

| 指标 | 5 cm baseline | semantic-BEV dedupe+smoothing | 变化 |
| --- | ---: | ---: | ---: |
| 完成题数 | 184 | 184 | 0 |
| Snapshot/navigation success | 147 / 184 = 79.89% | **154 / 184 = 83.70%** | **+3.80 pp** |
| Fail | 37 / 184 = 20.11% | **30 / 184 = 16.30%** | **-3.80 pp** |
| 成功题平均探索路径 | 5.595 m | **4.098 m** | **-1.497 m（-26.8%）** |
| 成功题路径中位数 | 2.713 m | **2.623 m** | -0.090 m |
| 成功题路径标准差 | 7.922 m | **4.242 m** | -3.680 m |

结果说明：semantic 组多完成 7 题，同时其成功 episode 的平均探索路径更短。平均路径的改善部分来自少数 baseline 侧的长路径 episode，因此不能只看均值，下一节给出同题 paired 口径。

## 4. 同题 paired 对照

两组对同一 184 题运行，逐题成败关系如下：

| 同题结果 | 题数 |
| --- | ---: |
| 两组都成功 | 141 |
| baseline 成功、semantic 失败 | 6 |
| baseline 失败、semantic 成功 | **13** |
| 两组都失败 | 24 |

因此 semantic 相对 baseline 的净成功转换为 `13 - 6 = +7` 题。

只在两组都成功的 141 题上比较路径：

| 指标 | semantic - baseline |
| --- | ---: |
| 平均路径差 | **-1.862 m** |
| 中位路径差 | 0.000 m |

这说明整体平均路径优势不是单纯由成功集合不同造成；但中位数为 0，表明收益并不均匀，主要集中在一部分需要更长探索的题目。当前只有一次运行，且 Gemma 温度为 0.7；应将其视为稳定性与效率的积极信号，而不是单次运行即可完成统计显著性结论。

## 5. 结果文件与复核方法

每个 A-EQA 输出目录包含：

| 文件 | 含义 |
| --- | --- |
| `eval_*.yaml` | 该次运行的配置副本 |
| `log_0.00_1.00.log` / `tmux.log` | 完整运行日志 |
| `success_list*.pkl`、`fail_list*.pkl` | 每题是否以 snapshot 完成导航 |
| `path_length_list*.pkl` | 成功题的探索路径长度 |
| `gpt_answer*.json` | VLM 对选中 snapshot 给出的答案 |
| `n_filtered_snapshots*.json`、`n_total_snapshots*.json`、`n_total_frames*.json` | memory/snapshot 统计 |

本文件第 3/4 节由上述 success/fail/path-length 原始文件重算，合并时按 question id 去重。
