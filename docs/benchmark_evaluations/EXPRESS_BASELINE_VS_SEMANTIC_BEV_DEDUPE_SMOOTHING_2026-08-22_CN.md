# EXPRESS-Bench：5 cm baseline vs semantic-BEV dedupe+smoothing

整理日期：2026-08-22  
性质：EXPRESS-Bench 完整 2,044 题上的 SCOPE 5 cm baseline 与 semantic-BEV dedupe+smoothing 对照  
状态：两组均已完成，2,044 / 2,044。

对应结果文件：

| 方法 | 代码工作分支 | 正式结果目录 |
| --- | --- | --- |
| 5 cm baseline | `feat/express-baseline`（基于 `baseline/fix-tsdf05cm`） | `/data1/jiangdakun/scope_results/express_baseline_5cm/` |
| semantic-BEV dedupe+smoothing | `feat/express-semantic-bev-dedupe-smoothing`（基于 `feat/semantic-bev-dedupe-smoothing`） | `/data1/jiangdakun/scope_results/express_semantic_bev_dedupe_smoothing_5cm/` |

## 1. 这个实验回答什么问题

本实验回答的是：

> 在同样的 5 cm SCOPE、同一份 EXPRESS-Bench 2,044 题、相同对象建图/snapshot/frontier/导航流程下，将 TSDF-supported、实例去重和显示平滑后的 semantic BEV 作为额外 VLM 图像上下文，是否能提高最终问答质量，并改善探索效率？

结论：该版本显著减少了探索开销，但没有提升当前本地 judge 下的最终答案正确性。semantic-BEV 将平均探索步数从 6.965 降至 5.121（-26.5%），成功作答 episode 的平均路径从 6.598 m 降至 5.034 m（-23.7%），完整运行时间从 62:22:50 降至 48:21:19（-22.5%）。但 `C` 从 31.81 降至 31.10，严格正确率 `C*` 从 34.39% 降至 33.51%。

因此，本次完整对照支持“semantic-BEV 使 SCOPE 更早作出决策、探索更高效”，但不支持“当前直接注入整张 BEV 图可提高 EXPRESS 的最终答案质量”。它检验的是完整 structured semantic BEV 上下文（含 TSDF support、实例过滤、dedupe、smoothing、轨迹和 frontier 对齐），不是只开关某一个 dedupe/smoothing 函数的纯消融。

`C/C*/E_path` 使用相同的本地 `gemma3:27b` judge 重算，适合两组内部配对比较；它不是 EXPRESS 官方 GPT-4o-mini judge 的 leaderboard 成绩。

## 2. 公平性检查

两组共享以下条件：

| 条件 | 设置 |
| --- | --- |
| 题目 | `/data1/liuyaxuan/EXPRESS-Bench/EXPRESS-Bench/data/express-bench.json`，2,044 题 |
| 场景 | `/data1/jiangdakun/hm3d` |
| TSDF | 0.05 m |
| 探索预算 | 最多 50 steps；首步 7 views，后续每步 3 views |
| 检测/分割/表征 | YOLO-World、SAM、CLIP ViT-B/32 |
| 决策 VLM | `gemma3:27b`，温度 0.7 |
| 随机种子 | 3407 |

baseline 使用 GPU1 + Ollama `11437`；dedupe 使用 GPU2 + Ollama `11438`。两个 endpoint 都加载相同的 `gemma3:27b`，仅用于避免共享队列。对于 EXPRESS 实际执行路径，dedupe 版本的功能性额外变化是：每个决策轮将 semantic BEV 作为额外图片发送给同一 VLM；其余探索配置相同。

## 3. 完整结果

| 指标 | 5 cm baseline | semantic-BEV dedupe+smoothing | 变化 |
| --- | ---: | ---: | ---: |
| 完成题数 | 2,044 | 2,044 | 0 |
| `C`（本地 judge 的分级答案信用） | **31.81** | 31.10 | -0.71 |
| `C*`（本地 judge 严格答案正确率） | **34.39%** | 33.51% | -0.88 pp |
| `E_path`（路径效率折扣后的答案信用） | 31.96 | **32.17** | +0.21 |
| `d_T`（结束时距目标的平均测地距离） | **5.901 m** | 6.031 m | +0.130 m |
| 选择 snapshot 作答 | 1,319 / 2,044 = 64.53% | **1,321 / 2,044 = 64.63%** | +0.10 pp |
| 平均探索 steps | 6.965 | **5.121** | **-1.844（-26.5%）** |
| 成功作答题平均探索路径 | 6.598 m | **5.034 m** | **-1.564 m（-23.7%）** |
| 成功作答题路径中位数 | 3.773 m | **3.227 m** | -0.546 m |
| 平均过滤后 snapshots | 2.070 | **1.899** | -0.171 |
| 完整 wall-clock 运行时间 | 62:22:50 | **48:21:19** | **-14:01:31（-22.5%）** |

`E_path` 的微小提升来自更短探索路径；它不足以抵消 `C` 和 `C*` 的下降。`d_T` 越低越好，dedupe 组略高。两组选择 snapshot 作答的比例几乎相同，但 dedupe 更常以较少 steps 结束 episode。

## 4. 同题 paired 对照

两组对同一完整 2,044 题运行。按本地 judge 的严格正确性逐题对照：

| 同题答案结果 | 题数 |
| --- | ---: |
| 两组都正确 | 557 |
| baseline 正确、dedupe 错误 | **146** |
| baseline 错误、dedupe 正确 | 128 |
| 两组都错误 | 1,213 |

dedupe 相对 baseline 的净严格正确转换为 `128 - 146 = -18` 题。这与 `C*` 低 0.88 pp 一致。

按“是否选择 snapshot 作答”逐题对照：

| 同题 snapshot 结果 | 题数 |
| --- | ---: |
| 两组都选择 snapshot | 1,245 |
| baseline 选择、dedupe 未选择 | 74 |
| baseline 未选择、dedupe 选择 | **76** |
| 两组都未选择 | 649 |

两组 snapshot 作答数只相差 2 题；答案差异主要来自选择了不同 snapshot/路径后给出的回答，而不是 dedupe 大幅提高或降低了停止作答的频率。

## 5. 结果文件与复核方法

每个 EXPRESS 输出目录包含：

| 文件 | 含义 |
| --- | --- |
| `eval_express_*.yaml` | 该次运行的配置副本 |
| `tmux.log` / `log_0.00_1.00.log` | 完整运行日志；首列为累计 wall-clock |
| `express_records.jsonl` | 每题答案、judge 结果、steps、路径、目标距离的原始记录 |
| `express_metrics.json` | 全量 `C/C*/E_path/d_T` 汇总 |
| `success_list*.pkl`、`fail_list*.pkl`、`path_length_list*.pkl` | SCOPE snapshot/路径原始记录 |
| `runtime_status_2026-08-22.json` | 最终 wall-clock 与完成题数 |

本文件第 3/4 节由两组 `express_records.jsonl` 以 question id 对齐后重算。`C` 是每题本地 judge 的 0–5 分答案信用（错误归零）；`C*` 是严格正确率；`E_path` 进一步以最短路径与实际探索路径的比率折扣，并仅对有有效路径长度的作答 episode 计算。
