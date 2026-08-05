# 小实验：feat/batch-frontier-potential-scoring

整理日期：2026-08-05  
性质：frontier potential scoring 调用方式小实验  
对应结果文件：

| 方法 | 分支 | 结果目录 |
| --- | --- | --- |
| 5 cm baseline pilot | `baseline/fix-tsdf05cm` | `artifacts/baseline_ceping_split1/` |
| 当前 5 cm baseline/fix 对照 | `baseline/fix-tsdf05cm` | `artifacts/baseline_metric_control_splits1_3/` |
| batch 小实验第 1 次 | `feat/batch-frontier-potential-scoring` | `artifacts/batch_frontier_reason1/` |
| batch 小实验第 2 次 | `feat/batch-frontier-potential-scoring` | `artifacts/batch_frontier_reason2/` |

## 1. 这个实验回答什么问题

这个实验只回答一个小问题：

> 把每一步新 frontier 的 potential scoring 从“每个 frontier 单独一次 VLM 请求”改成“多个 frontier 合成一次 batch 请求”，是否可行？会不会减少调用、保持行为稳定？

它不是主方法，不涉及 readable-BEV 的 semantic/Gaussian BEV 输入，也不是最终导航策略。

## 2. 方法改了什么

原 baseline 的 frontier potential scoring 逻辑大致是：

```text
task + frontier_0 image -> frontier_0 score
task + frontier_1 image -> frontier_1 score
task + frontier_2 image -> frontier_2 score
```

batch 分支改成：

```text
task + F_0 image + F_1 image + F_2 image
-> JSON 返回 F_0/F_1/F_2 的 potential scores
```

关键实现点：

- 每个 batch 请求内部使用局部 `F_0..F_{n-1}`。
- 解析后再把局部 `F_i` 映射回 planner 的原始 frontier ID。
- 这样可以避免 VLM 返回自然局部编号时，被错误解释成全局 frontier 编号。
- 只改变 frontier potential scoring 的请求方式；最终 snapshot/frontier decision 仍沿用 baseline 逻辑。

## 3. 结果如何保存

每个结果目录中保留：

| 文件 | 说明 |
| --- | --- |
| `eval_goatbench.yaml` | 运行配置；batch 目录里应有 `batch_frontier_potential: true`。 |
| `log_0.00_1.00_1.log` | split 1 运行日志和耗时。 |
| `success_by_snapshot_0.0_1.0_1.pkl` | task 级 snapshot success。 |
| `success_by_distance_0.0_1.0_1.pkl` | task 级 distance success。 |
| `spl_by_snapshot_0.0_1.0_1.pkl` | task 级 snapshot SPL。 |
| `spl_by_distance_0.0_1.0_1.pkl` | task 级 distance SPL。 |
| `success_by_task_0.0_1.0_1.pkl` | 按 image/object/description 拆分的 success。 |
| `spl_by_task_0.0_1.0_1.pkl` | 按 image/object/description 拆分的 SPL。 |
| `vlm_timing.json` | VLM 请求耗时；batch 结果里还有 `stage_summary.frontier_potential_batch_step`。 |

## 4. 核心指标

| 结果 | 任务数 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 耗时 | VLM 成功请求 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| baseline_ceping split 1 | 278 | **20.50%** | 40.65% | **17.13%** | **29.11%** | 15:39:34 | 4,059 |
| baseline_metric_control split 1 | 278 | **20.50%** | **44.24%** | 16.29% | **31.66%** | **14:02:41** | 4,422 |
| batch reason1 | 278 | 19.78% | 40.65% | 15.34% | 28.41% | 17:21:19 | 4,841 |
| batch reason2 | 278 | 17.99% | 40.65% | 15.54% | 28.88% | 14:45:41 | **3,511** |

说明：

- `baseline_ceping` 是旧 5 cm baseline pilot。
- `baseline_metric_control split 1` 是当前 readable-BEV 大实验使用的正式 5 cm baseline/fix 对照。
- batch 小实验最好同时和这两个 baseline 看：一个看历史 pilot，一个看当前正式 baseline/fix。

## 5. batch stage 结果

`vlm_timing.json` 中的 `stage_summary.frontier_potential_batch_step` 更能说明 batch 逻辑是否稳定：

| 结果 | batch stages | 成功 stages | 失败 stages | total frontier items | 成功 stage 平均耗时 |
| --- | ---: | ---: | ---: | ---: | ---: |
| batch reason1 | 1,285 | 161 | 1,124 | 2,098 | 9.135 s |
| batch reason2 | 618 | 614 | 4 | 983 | 6.683 s |

解释：

- 第一次 `baseline_all—new-frontier_reason` 失败 stage 很多，说明 batch 请求/解析/编号映射还不稳定。
- 第二次 `baseline_all—new-frontier_reason2` 修复 batch-local frontier ID 后，stage 成功率明显正常。
- 第二次 VLM 成功请求数降到 3,511，比 baseline_ceping 的 4,059 更少。

## 6. 结论

这个分支的结论是：

- batch frontier potential scoring 在修复局部编号映射后是可行的。
- 它可以减少部分 VLM 请求，并让 batch stage 成功率变正常。
- 但它没有带来导航成功率提升：
  - Distance success 仍为 40.65%。
  - 低于当前正式 baseline/fix split 1 的 44.24%。
  - 也明显低于 readable-BEV 主方法 split 1 的 56.83%。

所以 `feat/batch-frontier-potential-scoring` 应定位为小实验/效率探索，不应作为主方法。

## 7. 推荐后续动作

如果继续研究 batch，可以做：

1. 固定与 `baseline_metric_control` 完全相同的配置，只切换 `batch_frontier_potential`。
2. 重跑 split 1/2/3，避免只看一次 split 1。
3. 把 batch 是否减少 API 成本、是否影响最终成功率分开报告。

如果目标是提高 GOAT-Bench 成功率，优先继续 `feat/metric-frontier-readable-bev` 和 `feat/semantic-bev-dedupe-smoothing`，不要把 batch 小实验当主线。

