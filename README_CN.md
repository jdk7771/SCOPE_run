# SCOPE GOAT-Bench 分支说明和介绍

整理日期：2026-08-05  
GitHub 仓库：`https://github.com/jdk7771/SCOPE_run`  
仓库内结果文件夹：`experiment_results/scope_goatbench_results_release_2026-08-05`  
服务器原始 release 包：`/mnt/data/scope_goatbench_results_release_2026-08-05`

## 快速入口

如果只想看最重要的大实验结果，请先打开：

```text
结果/结果说明.md
```

`结果/` 是重新整理后的中文入口目录。`结果/大结果/` 放主实验对比、汇总表和对应的 `json/pkl/yaml/log` 原始指标文件；`结果/小实验/` 放过程性小实验。完整归档仍保留在 `experiment_results/scope_goatbench_results_release_2026-08-05/`。

## 1. 先看哪几个文件

| 文件 | 作用 |
| --- | --- |
| `docs/RESULTS_STORAGE_INDEX_CN.md` | 说明每个 `json/pkl/yaml/log` 是怎么保存的，以及每个 artifact 目录对应哪个实验。 |
| `docs/EXPERIMENT_MAIN_BASELINE_VS_METRIC_READABLE_BEV_CN.md` | 大实验文档：`baseline/fix-tsdf05cm` vs `feat/metric-frontier-readable-bev`。 |
| `metrics/metrics_summary.csv` | 所有结果的总表，适合直接打开查看。 |
| `metrics/metrics_summary.json` | 和 CSV 相同内容的 JSON 版本。 |
| `manifest.json` | 每个 artifact 来源路径、分支、核心代码 ref、已复制文件和 timing 汇总。 |

本 release 是 compact 结果包，只保存指标、日志、配置和 timing；没有保存完整图片/VLM 输入图。

## 2. 当前需要关注的分支

| 分支 | 核心代码 ref | 做什么 | 已保存实验 | 主要结果文件 |
| --- | --- | --- | --- | --- |
| `main` | `6abe091` | 原始 SCOPE 历史基线，默认 10 cm TSDF。原始结果目录已删除，只保留文字归档。 | 历史全数据集指标；split 1/2 归档指标。 | `artifacts/main_experience_deleted_archive/README.md` |
| `baseline/fix-tsdf05cm` | `8d4a4c9` | 5 cm TSDF baseline/fix；修 stale snapshot object ID，记录 VLM timing。可理解为当前 5 cm 非 BEV 对照。 | 正式 split 1/2/3 对照；旧 split 1 pilot。 | `artifacts/baseline_metric_control_splits1_3/`、`artifacts/baseline_ceping_split1/` |
| `feat/metric-frontier-readable-bev` | `f36b247` | 当前验证最充分的主方法：米制 frontier、共坐标 semantic/Gaussian BEV、全部 frontier 输入 VLM。 | split 1/2/3 三个完整 episode。 | `artifacts/metric_readable_bev_all_frontiers_splits1_3/` |
| `feat/semantic-bev-dedupe-smoothing` | `81bf1e2` | readable-BEV 后续清理：同类语义实例去重、BEV 显示平滑。 | 一个完整 split 1；两个 `00803` 单场景检查。 | `artifacts/dedupe_smoothing_check_00803/`、`artifacts/dedupe_check_00803/` |

`feat/structured-bev-tsdf05cm` 是较早的 structured-BEV 过程分支，不是当前重点结果；本文档不把它放进主实验对比。

## 3. 如何对比

| 对比 | 性质 | 该看哪个文档 | 该看哪些结果文件 | 结论 |
| --- | --- | --- | --- | --- |
| `baseline/fix-tsdf05cm` vs `feat/metric-frontier-readable-bev` | 大实验/主实验 | `docs/EXPERIMENT_MAIN_BASELINE_VS_METRIC_READABLE_BEV_CN.md` | `artifacts/baseline_metric_control_splits1_3/`、`artifacts/metric_readable_bev_all_frontiers_splits1_3/` | readable-BEV 在 split 1/2/3 四项核心指标都高于 baseline/fix。 |
| `feat/semantic-bev-dedupe-smoothing` vs `feat/metric-frontier-readable-bev` | 最终代码候选的初步检查 | 本 README 第 5 节 | `artifacts/dedupe_smoothing_check_00803/`、`artifacts/metric_readable_bev_all_frontiers_splits1_3/` | split 1 结果接近，但 dedupe/smoothing 缺 split 2/3 完整验证。 |
| `main` vs 5 cm baseline/fix | 历史参考 | `artifacts/main_experience_deleted_archive/README.md` | `artifacts/main_experience_deleted_archive/`、`artifacts/baseline_metric_control_splits1_3/` | `main` 是 10 cm TSDF 历史结果；当前正式对照以 5 cm baseline/fix 为准。 |

## 4. 大实验结论

大实验是当前最重要的结果：

```text
baseline/fix-tsdf05cm
vs
feat/metric-frontier-readable-bev
```

两个方法都使用 5 cm TSDF，并且都完成 split 1/2/3。三 episode 合计：

| 指标 | baseline/fix 0.05 m | metric readable-BEV | 提升 |
| --- | ---: | ---: | ---: |
| Snapshot success | 18.27% | **26.91%** | **+8.64 pp** |
| Distance success | 39.88% | **48.02%** | **+8.14 pp** |
| Snapshot SPL | 13.84% | **19.39%** | **+5.55 pp** |
| Distance SPL | 27.86% | **32.49%** | **+4.63 pp** |

逐 split 结果：

| Split | 任务数 | baseline/fix Snapshot | metric Snapshot | baseline/fix Distance | metric Distance |
| --- | ---: | ---: | ---: | ---: | ---: |
| split 1 | 278 | 20.50% | **33.09%** | 44.24% | **56.83%** |
| split 2 | 255 | 19.22% | **21.96%** | 38.43% | **41.18%** |
| split 3 | 277 | 15.16% | **25.27%** | 36.82% | **45.49%** |

一句话结论：`feat/metric-frontier-readable-bev` 是当前验证最充分的好代码，可以作为主实验结果。

## 5. dedupe/smoothing 的定位

`feat/semantic-bev-dedupe-smoothing` 可以理解为 readable-BEV 的最终代码候选，但目前系统验证不够。

| 方法 | 范围 | Snapshot success | Distance success | Snapshot SPL | Distance SPL |
| --- | --- | ---: | ---: | ---: | ---: |
| metric readable-BEV | split 1，278 tasks | **33.09%** | **56.83%** | 23.18% | 37.43% |
| dedupe+smoothing | split 1，278 tasks | 31.29% | 56.47% | **24.49%** | **40.29%** |

结论：

- 它没有明显退化，split 1 效果和主方法非常接近。
- 它的 SPL 更高，但 success 略低。
- 因为还没有 split 2/3 完整结果，不能说它已经替代 `feat/metric-frontier-readable-bev`。

## 6. 结果文件结构

```text
experiment_results/scope_goatbench_results_release_2026-08-05
|-- README.md
|-- README_CN.md
|-- manifest.json
|-- metrics/
|   |-- metrics_summary.csv
|   `-- metrics_summary.json
|-- artifacts/
|   |-- baseline_ceping_split1/
|   |-- baseline_metric_control_splits1_3/
|   |-- metric_readable_bev_all_frontiers_splits1_3/
|   |-- dedupe_check_00803/
|   |-- dedupe_smoothing_check_00803/
|   `-- main_experience_deleted_archive/
`-- docs/
    |-- RESULTS_STORAGE_INDEX_CN.md
    `-- EXPERIMENT_MAIN_BASELINE_VS_METRIC_READABLE_BEV_CN.md
```

每个 `artifacts/*` 目录都保留 compact 结果：

- `eval_goatbench.yaml`
- `log_*.log`
- `success_by_*.pkl`
- `spl_by_*.pkl`
- `n_total_*.json`
- `n_filtered_*.json`
- `vlm_timing.json`

完整说明见 `docs/RESULTS_STORAGE_INDEX_CN.md`。
