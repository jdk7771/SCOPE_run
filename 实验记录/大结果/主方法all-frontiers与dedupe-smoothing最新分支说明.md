# 主方法 all-frontiers 与 dedupe/smoothing 最新分支说明

整理日期：2026-08-05

## 1. 大结果代码是不是 all-frontiers

是。`实验记录/大结果/` 里的主方法大结果对应的是 `feat/metric-frontier-readable-bev` 的 all-frontiers 版本。

| 项目 | 内容 |
| --- | --- |
| 大结果主方法分支 | `feat/metric-frontier-readable-bev` |
| 核心代码 ref | `f36b247` |
| 原始结果路径 | `/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-all-frontiers` |
| 当前保存路径 | `实验记录/大结果/02_可读BEV_metric-frontier-readable-bev/原始结果文件/` |
| 配置证据 | `eval_goatbench.yaml` 里 `exp_name: "metric-frontier-readable-bev-all-frontiers"`，且 `structured_bev_max_frontiers: 0` |

这里的 `structured_bev_max_frontiers: 0` 表示不截断 frontier 候选，也就是把当前所有有效 frontier 都提供给高层 VLM。SCOPE PotentialGraph 仍负责给 frontier 排序并提供 Gaussian evidence 分数，但不再把候选空间裁成早期 top-k。

因此，大结果里的 readable-BEV 主方法应写成：

```text
feat/metric-frontier-readable-bev, all-frontiers, split 1/2/3 完整验证
```

## 2. 大结果验证了什么

大结果验证的是：

```text
baseline/fix-tsdf05cm
vs
feat/metric-frontier-readable-bev, all-frontiers
```

两个方法都使用 5 cm TSDF，且都完成 GOAT-Bench split 1/2/3。三 split 合计 810 个 task：

| 指标 | baseline/fix 0.05 m | metric readable-BEV all-frontiers | 提升 |
| --- | ---: | ---: | ---: |
| Snapshot success | 18.27% | **26.91%** | **+8.64 pp** |
| Distance success | 39.88% | **48.02%** | **+8.14 pp** |
| Snapshot SPL | 13.84% | **19.39%** | **+5.55 pp** |
| Distance SPL | 27.86% | **32.49%** | **+4.63 pp** |

结论：`feat/metric-frontier-readable-bev` 是当前系统验证最充分的主结果分支。

## 3. 最新候选分支做了什么

`feat/semantic-bev-dedupe-smoothing` 可以理解为在 `feat/metric-frontier-readable-bev` 的 all-frontiers 主方法基础上做的 BEV 可读性后续清理。它的功能提交是：

```text
81bf1e2 feat: deduplicate and smooth semantic BEV instances
```

该分支和 `feat/metric-frontier-readable-bev` 的共同基础是 `f36b247`，也就是 all-frontiers 主方法代码。后续主要改动集中在 3 个文件：

| 文件 | 作用 |
| --- | --- |
| `cfg/eval_goatbench.yaml` | 新增 semantic BEV 同类实例去重半径和显示平滑配置。 |
| `run_goatbench_evaluation.py` | 把新增配置传给 BEV 渲染函数。 |
| `src/tsdf_export.py` | 实现同类语义实例去重和显示层平滑。 |

具体做了两类操作：

1. 同类语义实例去重：对 ConceptGraph 中相互重叠或距离很近的同类对象轨迹做去重，避免同一个物理物体在 semantic BEV 里重复显示多个相同标签。默认配置是 `tsdf_bev_semantic_same_class_merge_radius_m: 0.55`。

2. BEV 显示平滑：对 TSDF 支撑的 semantic footprint 做显示层平滑，让 5 cm 栅格边缘更圆滑、更容易读。默认配置是 `tsdf_bev_semantic_display_smoothing_m: 0.05`。这个平滑是 display-only：不改变原始 TSDF、object mask、低层 planner 或导航执行逻辑。

它没有改变的部分：

- 仍然是 5 cm TSDF。
- 仍然使用 readable semantic BEV + Gaussian evidence BEV。
- 仍然是 all-frontiers 候选空间。
- 没有替换低层 SCOPE planner。
- 没有改变 GOAT-Bench success/SPL 评价方式。

## 4. 做了什么实验验证

`feat/semantic-bev-dedupe-smoothing` 目前做过的验证比主方法少：

| 方法 | 范围 | Snapshot success | Distance success | Snapshot SPL | Distance SPL |
| --- | --- | ---: | ---: | ---: | ---: |
| metric readable-BEV all-frontiers | split 1，278 tasks | **33.09%** | **56.83%** | 23.18% | 37.43% |
| dedupe+smoothing | split 1，278 tasks | 31.29% | 56.47% | **24.49%** | **40.29%** |

另外还保留了两个 `00803` 单场景检查结果，用于人工检查 dedupe/smoothing 的 BEV 显示效果。对应 compact artifact 在：

```text
experiment_results/scope_goatbench_results_release_2026-08-05/artifacts/dedupe_smoothing_check_00803/
experiment_results/scope_goatbench_results_release_2026-08-05/artifacts/dedupe_check_00803/
```

## 5. 当前定位

`feat/metric-frontier-readable-bev` 是主结果分支：它是 all-frontiers，并且 split 1/2/3 都完整跑过。

`feat/semantic-bev-dedupe-smoothing` 是最新代码候选：它在主方法基础上清理同类语义实例重复显示、让 BEV 更平滑。split 1 结果和主方法接近，SPL 更高但 success 略低；因为还没有 split 2/3 完整结果，所以目前不能说它已经替代 `feat/metric-frontier-readable-bev`。
