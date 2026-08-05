# 结果文件保存说明与索引

整理日期：2026-08-05  
结果根目录：`/mnt/data/scope_goatbench_results_release_2026-08-05`

## 1. 这个文件夹保存了什么

这个 release 是 compact 结果包，目的是保存每个实验的可复算指标和审计信息，而不是保存完整图片。

保留内容：

| 类型 | 文件名示例 | 作用 |
| --- | --- | --- |
| 配置 | `eval_goatbench.yaml` | 保存本次运行使用的关键配置，例如 `exp_name`、`tsdf_grid_size`、是否启用 `structured_bev_for_vlm`、是否启用 `batch_frontier_potential`。 |
| 日志 | `log_0.00_1.00_1.log` | 保存运行过程和最终耗时，例如 `All scenes finish`。文件名最后的 `1/2/3` 对应 GOAT-Bench episode split。 |
| success 指标 | `success_by_snapshot_0.0_1.0_1.pkl`、`success_by_distance_0.0_1.0_1.pkl` | 每个 task 的成功标记。`snapshot` 是严格对象/snapshot 成功，`distance` 是距离成功。 |
| SPL 指标 | `spl_by_snapshot_0.0_1.0_1.pkl`、`spl_by_distance_0.0_1.0_1.pkl` | 每个 task 的 SPL 值。 |
| 任务类型指标 | `success_by_task_0.0_1.0_1.pkl`、`spl_by_task_0.0_1.0_1.pkl` | 按 `image/object/description` 三类保存的列表。 |
| VLM timing | `vlm_timing.json` | 每次 VLM API 请求的耗时；batch 小实验还包含 batch stage 成功/失败统计。 |
| snapshot/frame 统计 | `n_total_snapshots_*.json`、`n_filtered_snapshots_*.json`、`n_total_frames_*.json` | 记录运行中 snapshot 和 frame 数量。 |
| 总表 | `metrics/metrics_summary.csv`、`metrics/metrics_summary.json` | 已从 pkl/json 汇总出的表格，方便直接读数。 |
| manifest | `manifest.json` | 记录每个 artifact 来源路径、分支、核心代码 ref、已复制文件和 timing 汇总。 |

没有保留完整可视化图片、frontier 缩略图、`vlm_full_inputs` 图片 bundle。原始图片结果超过 150GB；如果需要公开完整图片，应该单独做一个 large artifact。

## 2. 结果目录索引

| Artifact 目录 | 来源分支 | 原始路径 | 保存内容 | 用途 |
| --- | --- | --- | --- | --- |
| `artifacts/baseline_metric_control_splits1_3/` | `baseline/fix-tsdf05cm` | `/mnt/data/SCOPE/results/baseline_of_metric-frontier-readable-bev` | split 1/2/3 的 pkl、json、yaml、log、timing | 大实验 baseline，对比 readable-BEV 主方法 |
| `artifacts/metric_readable_bev_all_frontiers_splits1_3/` | `feat/metric-frontier-readable-bev` | `/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-all-frontiers` | split 1/2/3 的 pkl、json、yaml、log、timing | 大实验主方法 |
| `artifacts/baseline_ceping_split1/` | `baseline/fix-tsdf05cm` | `/mnt/data/SCOPE/results/baseline_ceping` | split 1 的旧 5 cm baseline pilot | batch 小实验的历史参考，不是当前正式主对照 |
| `artifacts/batch_frontier_reason1/` | `feat/batch-frontier-potential-scoring` | `/mnt/data/SCOPE_batch_frontier_potential/results/baseline_all—new-frontier_reason` | 第一次 batch frontier potential 小实验 | batch 初版，stage 失败较多 |
| `artifacts/batch_frontier_reason2/` | `feat/batch-frontier-potential-scoring` | `/mnt/data/SCOPE_batch_frontier_potential/results/baseline_all—new-frontier_reason2` | 第二次 batch frontier potential 小实验 | batch-local frontier ID 修复后的小实验 |
| `artifacts/dedupe_smoothing_check_00803/` | `feat/semantic-bev-dedupe-smoothing` | `/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-dedupe-smoothing-check-00803` | split 1 完整运行 + `00803` 单场景检查 | readable-BEV 后续清理候选，尚未系统验证 |
| `artifacts/dedupe_check_00803/` | `feat/semantic-bev-dedupe-smoothing` | `/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-dedupe-check-00803` | `00803` 单场景检查 | dedupe/smoothing 单场景对照 |
| `artifacts/main_experience_deleted_archive/` | `main` | `/mnt/data/SCOPE/results/main_experience_deleted_archive` | 删除归档 README | 原始 main 结果已删除，只能保留文字归档指标 |

## 3. 怎么读 pkl

每个 `*_by_snapshot_*.pkl`、`*_by_distance_*.pkl` 是 task 级字典或列表，均值乘 100 就是百分比指标。

例如：

```python
import pickle
import numpy as np

path = "artifacts/metric_readable_bev_all_frontiers_splits1_3/success_by_distance_0.0_1.0_1.pkl"
with open(path, "rb") as f:
    data = pickle.load(f)

values = list(data.values()) if isinstance(data, dict) else list(data)
score = np.nanmean(values) * 100
print(score)
```

`success_by_task_*.pkl` 和 `spl_by_task_*.pkl` 的结构是：

```python
{
    "image": [...],
    "object": [...],
    "description": [...]
}
```

分别对三类列表取均值即可得到任务类型拆分结果。

## 4. 怎么读 VLM timing

`vlm_timing.json` 的核心字段：

| 字段 | 含义 |
| --- | --- |
| `records` | 每次 `chat.completions.create` 尝试。 |
| `records[*].call_type` | 请求类型，例如 `decision`、`frontier_potential`、`frontier_potential_batch`、`prefilter`、`self_refine`。 |
| `records[*].response_seconds` | 单次 API 请求耗时，不包含本地图片准备、导航执行和 retry sleep。 |
| `stage_summary` | batch 小实验的阶段级统计，例如一个 batch step 是否成功、包含多少 frontier。 |

batch 小实验中，`frontier_potential_batch_step` 是更重要的 stage 指标；它记录一次 batch 处理多个 frontier 是否完整成功。

## 5. 推荐阅读顺序

1. `各分支说明.md`：先看分支和实验总览。
2. `docs/EXPERIMENT_MAIN_BASELINE_VS_METRIC_READABLE_BEV_CN.md`：看大实验，baseline/fix vs readable-BEV。
3. `docs/EXPERIMENT_BATCH_FRONTIER_POTENTIAL_CN.md`：看小实验，batch frontier potential。
4. `metrics/metrics_summary.csv`：查所有结果的原始汇总行。
5. `artifacts/*`：需要复算指标或审计日志时再进入。
