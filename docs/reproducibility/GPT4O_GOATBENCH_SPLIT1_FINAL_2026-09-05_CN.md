# SCOPE GPT-4o：GOAT-Bench Split 1 最终复现结果

## 设置

- 基准：GOAT-Bench `val_unseen`，Split 1，36 episodes / 278 tasks。
- VLM：`gpt-4o-2024-11-20`；官方 `cfg/eval_goatbench.yaml`。
- 核心参数：10 cm TSDF、1280 × 1280 RGB-D、HFOV 120°、成功阈值 1 m。
- 两个任务分片（`0.00–0.50`、`0.50–1.00`）完成后按 task ID 合并；合计为 **278/278**，没有缺失任务。
- 除仅影响保存图片的 stale snapshot-ID 防护外，未修改 TSDF 融合、frontier、VLM 决策、规划或指标实现。

## 最终结果

| 指标 | 本次 GPT-4o 复现 |
| --- | ---: |
| Snapshot success | 43.88% |
| Snapshot SPL | 34.29% |
| Distance success | **71.58%** |
| Distance SPL | **50.85%** |

## 与论文对比

论文在其 GOAT-Bench subset 上报告 SCOPE 的 Distance success / SPL 为 73.7% / 53.5%。本次同为 Split 1 的单次 GPT-4o 运行结果如下。

| Distance 指标 | 论文 SCOPE | 本次复现 | 差值（复现 − 论文） |
| --- | ---: | ---: | ---: |
| Success | 73.70% | 71.58% | -2.12 pp |
| SPL | 53.50% | 50.85% | -2.65 pp |

结论：该单次、全量 278-task 复现与论文数值接近，但略低约 2–3 pp。Snapshot 指标并非论文该表的报告项，故只保留本次结果，不做论文差值比较。单次 API 采样不代表多次运行中的最优值。

结果文件位于服务器 `/home/jiangdakun/projects/SCOPE_run_paper_gpt4o/results/exp_eval_goatbench/`；应以两个带分片后缀的原始 pkl 合并结果或最终 278-task 聚合 pkl 为准。
