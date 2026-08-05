# SCOPE GOAT-Bench 分支与实验结果说明

整理日期：2026-08-05  
GitHub 仓库：`https://github.com/jdk7771/SCOPE_run`  
结果 release 包：`/mnt/data/scope_goatbench_results_release_2026-08-05`

## 1. 先说结论

当前分支可以按两个维度理解：

1. **验证最充分的好代码**：`feat/metric-frontier-readable-bev`
   - 这是目前最可靠的主实验分支。
   - 它在 GOAT-Bench `split 1/2/3` 三个 episode 上都跑完了完整评测。
   - 相对当前 5 cm 非 BEV baseline，三 episode 合计 Snapshot success 提升 `+8.64 pp`，Distance success 提升 `+8.14 pp`。

2. **最终代码候选**：`feat/semantic-bev-dedupe-smoothing`
   - 它是在 `feat/metric-frontier-readable-bev` 上做的 BEV 可读性清理：同类语义实例去重、显示层平滑。
   - 代码层面可以理解为 readable-BEV 的后续最终候选版本。
   - 但实验验证还不如 `feat/metric-frontier-readable-bev` 系统：目前只看到一个完整 split 1 运行和一个 `00803` 单场景检查。
   - split 1 上它和 `feat/metric-frontier-readable-bev` 效果非常接近：Distance success `56.47%` vs `56.83%`，Snapshot success 略低，SPL 略高。因此它不能被称为“多 episode 已验证最终结果”，更准确叫“最终代码候选，尚需 split 2/3 系统验证”。

3. **过程分支**：`feat/structured-bev-tsdf05cm`
   - 这是较早的 structured-BEV/top-3 frontier 过程代码。
   - 它证明了 semantic BEV + Gaussian evidence BEV 这条路线有价值，但已经被 `feat/metric-frontier-readable-bev` 继承和改进。
   - 它保留为机制对照和历史过程，不建议作为最终主分支。

4. **小实验分支**：`feat/batch-frontier-potential-scoring`
   - 这是 frontier potential 评分 batch 化的小实验，不是主方法。
   - 它的意义主要是测试“把多个新 frontier 的 potential scoring 合成一次 VLM 请求”是否可行，以及 local `F_i` 到全局 frontier ID 的映射是否稳定。
   - 实验结果应该保留，但结论是：batch 修复后调用更稳定、请求数减少一些，但成功率没有超过主 baseline，也不是最终方法。

## 2. 分支谱系和定位

```text
main
+-- baseline/fix-tsdf05cm
|   `-- feat/batch-frontier-potential-scoring
`-- feat/structured-bev-tsdf05cm
    `-- feat/metric-frontier-readable-bev
        `-- feat/semantic-bev-dedupe-smoothing
```

| 分支 | 结果代码 ref | 当前 GitHub ref | 定位 | 是否推荐作为主结果 |
| --- | --- | --- | --- | --- |
| `main` | `6abe091` | `2cd946d` | 原始 SCOPE 10 cm TSDF 历史基线。原始结果目录已删除，只保留归档数值。 | 只作历史基线 |
| `baseline/fix-tsdf05cm` | `8d4a4c9` | `6fa225e` | 5 cm TSDF 非 BEV 对照，修 stale snapshot object ID，加入 VLM timing。 | 推荐作公平 baseline |
| `feat/batch-frontier-potential-scoring` | `dbbab92` | `586b9ff` | frontier potential batch 化小实验。 | 保留结果，不作主方法 |
| `feat/structured-bev-tsdf05cm` | `1623bd9` | `c2df3d2` | 初版 structured-BEV/top-3 frontier 过程分支。 | 历史机制对照 |
| `feat/metric-frontier-readable-bev` | `f36b247` | `ea7468e` | readable-BEV 主实验：米制 frontier、共坐标 BEV、TSDF 支撑语义 footprint、全部 frontier 输入 VLM。 | **当前验证最充分的主方法** |
| `feat/semantic-bev-dedupe-smoothing` | `81bf1e2` + README ref `efc08e5` | `efc08e5` | readable-BEV 后续清理：同类实例去重、显示平滑。 | 最终代码候选，但还缺 split 2/3 验证 |

注：`当前 GitHub ref` 里有些只是 README/文档提交；实验结果对应的核心代码 ref 以“结果代码 ref”为准。

## 3. 核心对照：metric readable-BEV vs 5 cm baseline

这个对照最重要，也最适合写进论文/汇报主表。两个结果都使用 5 cm TSDF，且 split 1/2/3 的 task ID 对齐。

| Episode split | 任务数 | 方法 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 耗时 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| split 1 | 278 | baseline/fix | 20.50% | 44.24% | 16.29% | 31.66% | 14:02:41 |
| split 1 | 278 | metric readable-BEV | **33.09%** | **56.83%** | **23.18%** | **37.43%** | 20:09:44 |
| split 2 | 255 | baseline/fix | 19.22% | 38.43% | 13.75% | 26.37% | 13:35:03 |
| split 2 | 255 | metric readable-BEV | **21.96%** | **41.18%** | **15.92%** | **29.12%** | 20:35:10 |
| split 3 | 277 | baseline/fix | 15.16% | 36.82% | 11.38% | 25.33% | 17:24:40 |
| split 3 | 277 | metric readable-BEV | **25.27%** | **45.49%** | **18.78%** | **30.60%** | 06:29:45 |

三 episode 合计：

| 指标 | baseline/fix 0.05 m | metric readable-BEV | 提升 |
| --- | ---: | ---: | ---: |
| Snapshot success | 18.27% | **26.91%** | **+8.64 pp** |
| Distance success | 39.88% | **48.02%** | **+8.14 pp** |
| Snapshot SPL | 13.84% | **19.39%** | **+5.55 pp** |
| Distance SPL | 27.86% | **32.49%** | **+4.63 pp** |

解释：

- `feat/metric-frontier-readable-bev` 的收益不是单个 episode 偶然带来的，split 1/2/3 三个 episode 方向一致。
- split 1 提升最大；split 2 提升较小但仍为正；split 3 也有明显收益。
- 代价是 VLM 输入更复杂，运行时间通常更长。

## 4. `feat/metric-frontier-readable-bev` 做了什么

相对 baseline/fix，它不是只改可视化，而是改了高层 VLM 决策输入：

- 使用 5 cm TSDF。
- frontier 检测参数改成米制配置，例如 0.10 m 邻域、0.10 m 聚类半径、0.20 m² 最小面积。
- 每次高层 VLM 决策前生成两张 BEV：
  - semantic BEV：未知/可通行/已探索/障碍、轨迹、agent 朝向、TSDF 支撑的语义 footprint、候选 `F1..Fn`。
  - Gaussian evidence BEV：与 semantic BEV 同 crop/同坐标，显示每个 frontier 的 future-evidence 和启发式不确定性。
- `structured_bev_max_frontiers: 0`，表示把所有有效 frontier 都输入高层 VLM，而不是只给 top-3。
- VLM 输出 structured JSON，再映射回原来的 snapshot/frontier 执行接口。

因此它是目前最重要的“好代码 + 多 episode 验证”分支。

## 5. `feat/structured-bev-tsdf05cm` 的作用

这个分支是过程代码，主要用于证明 structured-BEV 方向可行。历史报告记录的 split 1 指标如下：

| 分支 | 任务数 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `feat/structured-bev-tsdf05cm` | 278 | 22.30% | 50.00% | 17.96% | **37.75%** | 19:14:47 |

它的特点：

- 已经加入 semantic BEV + Gaussian evidence BEV。
- 早期实现默认只给高层 VLM top-3 frontier。
- 后来被 `feat/metric-frontier-readable-bev` 改进：米制 frontier、更可读 BEV、TSDF 支撑语义 footprint、全部 frontier 候选。

所以它应该保留为历史/机制对照，而不是最终主代码。

## 6. `feat/semantic-bev-dedupe-smoothing` 的定位

这个分支是在 `feat/metric-frontier-readable-bev` 之后做的 BEV 渲染清理：

- 合并重叠或距离很近的同类 ConceptGraph tracks，减少一个物体在 BEV 上重复出现多个同名标签。
- 对语义 footprint 做显示层平滑，让 5 cm voxel 边缘更自然。
- 注意：这是 display-only smoothing，不替换 TSDF/object mask，也不改变底层 planner。

已有结果：

| 结果目录 | 范围 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 说明 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `metric-frontier-readable-bev-dedupe-smoothing-check-00803` split 1 | 278 tasks | 31.29% | 56.47% | **24.49%** | **40.29%** | 一次完整 split 1 |
| `metric-frontier-readable-bev-dedupe-check-00803` split 2 | 6 tasks | 50.00% | 66.67% | 45.04% | 61.70% | 单场景 `00803` 检查 |
| `metric-frontier-readable-bev-dedupe-smoothing-check-00803` split 2 | 6 tasks | 50.00% | 50.00% | 46.65% | 46.65% | 单场景 `00803` 检查 |

和 `feat/metric-frontier-readable-bev` split 1 比：

| 方法 | Snapshot success | Distance success | Snapshot SPL | Distance SPL |
| --- | ---: | ---: | ---: | ---: |
| metric readable-BEV split 1 | **33.09%** | **56.83%** | 23.18% | 37.43% |
| dedupe+smoothing split 1 | 31.29% | 56.47% | **24.49%** | **40.29%** |

结论：

- dedupe+smoothing 不是明显坏掉，结果非常接近 readable-BEV 主分支。
- 它在 split 1 的 SPL 更高，但 Snapshot/Distance success 略低。
- 因为没有 split 2/3 完整验证，不能说它已经替代 `feat/metric-frontier-readable-bev` 成为“实验最强版本”。
- 更准确的说法：它是最终代码候选，需要继续跑 split 2/3 才能定论。

## 7. `feat/batch-frontier-potential-scoring` 小实验结果

这个分支只关注 frontier potential scoring 的调用方式：

```text
旧方式：每个 frontier 单独一次 VLM potential scoring
batch 方式：同一步新 frontier 合成一次 VLM 请求，返回多个 F_i 分数
```

两次结果如下：

| 结果目录 | 任务数 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 耗时 | VLM 成功请求 | batch stage |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `baseline_all—new-frontier_reason` | 278 | 19.78% | 40.65% | 15.34% | 28.41% | 17:21:19 | 4,841 | 161 / 1,285 成功 |
| `baseline_all—new-frontier_reason2` | 278 | 17.99% | 40.65% | 15.54% | 28.88% | 14:45:41 | 3,511 | 614 / 618 成功 |

对照参考：

| 对照 | 任务数 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `baseline_ceping` | 278 | 20.50% | 40.65% | 17.13% | 29.11% | 15:39:34 |
| `baseline_of_metric-frontier-readable-bev` split 1 | 278 | 20.50% | 44.24% | 16.29% | 31.66% | 14:02:41 |

结论：

- 第一次 batch 小实验失败 stage 很多，说明解析/映射不稳定。
- 第二次修复 batch-local frontier ID 后，batch stage 成功率明显正常，VLM 成功请求数下降到 3,511。
- 但任务成功率没有提升，Distance success 仍为 40.65%，低于正式 readable-BEV baseline split 1 的 44.24%。
- 所以该分支应保留为 latency/API 调用小实验，不作为主方法。

## 8. main 历史结果

`main` 是原始 SCOPE 基线，默认 10 cm TSDF。原始 `main_experience` 结果目录已删除，目前只保留文字归档：

| 范围 | Snapshot success | Distance success | Snapshot SPL | Distance SPL |
| --- | ---: | ---: | ---: | ---: |
| 历史全数据集，2,669 tasks | 23.98% | 43.12% | 18.67% | 31.14% |
| split 1，278 tasks | 23.74% | 45.32% | 18.68% | 33.43% |
| split 2，255 tasks | 23.92% | 41.96% | 17.71% | 28.72% |

这个结果可以作为历史参考，但不如当前 `baseline/fix-tsdf05cm` 与 `feat/metric-frontier-readable-bev` 的对照公平，因为 TSDF 分辨率和 frontier 设定不同，而且 main 的原始 pkl/图片已经不在。

## 9. 结果 release 包结构

已整理 compact release：

```text
/mnt/data/scope_goatbench_results_release_2026-08-05
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

每个 `artifacts/*` 目录只保留 compact 结果文件：

- `eval_goatbench.yaml`
- `log_*.log`
- `*_by_*.pkl`
- `vlm_timing.json`
- 已存在的 README/报告文件

没有包含完整可视化图片和 VLM 输入图片，因为原始结果目录合计超过 150GB。若需要上传完整图片，建议单独创建一个 large-folder dataset。

## 10. 推荐后续动作

1. 把 `feat/metric-frontier-readable-bev` 作为当前已验证主结果写进论文/汇报。
2. 把 `feat/semantic-bev-dedupe-smoothing` 作为最终代码候选继续跑 split 2/3。
3. `feat/batch-frontier-potential-scoring` 只作为小实验保留，指标已经归档。
4. 若要正式采用 dedupe+smoothing，需要补齐与 metric readable-BEV 相同的 split 1/2/3 对照。

