---
license: mit
language:
- zh
- en
pretty_name: SCOPE GOAT-Bench Branch Experiment Results
tags:
- robotics
- embodied-ai
- navigation
- goat-bench
- vlm
- bev
---

# SCOPE GOAT-Bench 分支与实验结果说明

本数据集包是 `https://github.com/jdk7771/SCOPE_run` 的 compact 实验结果归档，整理日期为 2026-08-05。

完整中文说明见 [README_CN.md](README_CN.md)。核心文档如下：

- [README_CN.md](README_CN.md)：分支、实验和结果文件总览。
- [docs/RESULTS_STORAGE_INDEX_CN.md](docs/RESULTS_STORAGE_INDEX_CN.md)：说明每个 `json/pkl/yaml/log` 如何保存。
- [docs/EXPERIMENT_MAIN_BASELINE_VS_METRIC_READABLE_BEV_CN.md](docs/EXPERIMENT_MAIN_BASELINE_VS_METRIC_READABLE_BEV_CN.md)：大实验，`baseline/fix-tsdf05cm` vs `feat/metric-frontier-readable-bev`。
- [docs/EXPERIMENT_BATCH_FRONTIER_POTENTIAL_CN.md](docs/EXPERIMENT_BATCH_FRONTIER_POTENTIAL_CN.md)：小实验，`feat/batch-frontier-potential-scoring` vs 5 cm baseline/fix。

核心结论：

- `feat/metric-frontier-readable-bev` 是当前验证最充分的主实验分支，已完成 split 1/2/3 三个 GOAT-Bench episode。
- `feat/batch-frontier-potential-scoring` 是 frontier potential batch 化小实验，结果已保留，但不作为主方法。
- `feat/semantic-bev-dedupe-smoothing` 是 readable-BEV 的最终代码候选；目前只有 split 1 完整运行和单场景检查，仍需补 split 2/3。

## 文件结构

```text
.
|-- README.md
|-- README_CN.md
|-- manifest.json
|-- metrics/
|   |-- metrics_summary.csv
|   `-- metrics_summary.json
|-- artifacts/
|   |-- baseline_ceping_split1/
|   |-- baseline_metric_control_splits1_3/
|   |-- batch_frontier_reason1/
|   |-- batch_frontier_reason2/
|   |-- metric_readable_bev_all_frontiers_splits1_3/
|   |-- dedupe_check_00803/
|   |-- dedupe_smoothing_check_00803/
|   `-- main_experience_deleted_archive/
`-- docs/
```

`metrics/metrics_summary.csv` 是主入口。每个 `artifacts/*` 目录保留 compact 结果文件：配置、日志、pkl 指标、`vlm_timing.json` 和已有说明文档。

本包不包含完整可视化图片和 VLM 输入图片，因为原始结果目录合计超过 150GB。

## 主要指标

三 episode 合计，`feat/metric-frontier-readable-bev` 相对当前 5 cm 非 BEV baseline：

| 指标 | baseline/fix 0.05 m | metric readable-BEV | 提升 |
| --- | ---: | ---: | ---: |
| Snapshot success | 18.27% | **26.91%** | **+8.64 pp** |
| Distance success | 39.88% | **48.02%** | **+8.14 pp** |
| Snapshot SPL | 13.84% | **19.39%** | **+5.55 pp** |
| Distance SPL | 27.86% | **32.49%** | **+4.63 pp** |

详细分支解释、batch 小实验指标、dedupe/smoothing 验证状态见 [README_CN.md](README_CN.md)。
