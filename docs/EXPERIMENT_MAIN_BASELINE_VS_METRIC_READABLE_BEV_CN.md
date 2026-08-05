# 大实验：baseline/fix-tsdf05cm vs feat/metric-frontier-readable-bev

整理日期：2026-08-05  
性质：GOAT-Bench 5 cm TSDF baseline 与 readable-BEV 主方法的正式对照  
对应结果文件：

| 方法 | 分支 | 结果目录 |
| --- | --- | --- |
| baseline/fix 0.05 m | `baseline/fix-tsdf05cm` | `artifacts/baseline_metric_control_splits1_3/` |
| metric readable-BEV | `feat/metric-frontier-readable-bev` | `artifacts/metric_readable_bev_all_frontiers_splits1_3/` |

## 1. 这个实验回答什么问题

这个实验回答的是：

> 在同样使用 5 cm TSDF 和相同 GOAT-Bench episode split 的前提下，加入 readable structured-BEV 输入、Gaussian evidence BEV、米制 frontier 设定和结构化输出后，是否比非 BEV baseline 更好？

这是目前最重要的大实验。它不是只看一个 episode，而是完成了 `split 1/2/3` 三个 episode。

## 2. 两个方法分别做了什么

### baseline/fix-tsdf05cm

这是当前公平 baseline：

- 5 cm TSDF。
- 修复 stale snapshot object ID，避免 snapshot 指向已经失效的 object。
- 记录 VLM timing。
- 不向高层 VLM 额外输入 semantic BEV / Gaussian evidence BEV。
- 结果目录：`artifacts/baseline_metric_control_splits1_3/`

注意：`main` 是 10 cm TSDF 历史基线；`baseline/fix-tsdf05cm` 相对 `main` 的主要变化可以理解为 5 cm TSDF、稳定性修复和计时记录。它本身不是新方法，主要用作 5 cm 对照。

### feat/metric-frontier-readable-bev

这是当前验证最充分的主方法：

- 5 cm TSDF。
- frontier 参数改为米制，例如 0.10 m 邻域、0.10 m 聚类半径、0.20 m² 最小 frontier 面积。
- 高层 VLM 决策前生成两张结构化 BEV：
  - semantic BEV：地图状态、agent、轨迹、TSDF 支撑的语义 footprint、frontier 标记。
  - Gaussian evidence BEV：和 semantic BEV 同 crop/同坐标，显示 frontier future-evidence。
- VLM 输出结构化 JSON，再映射回原 SCOPE 的 snapshot/frontier 执行接口。
- 结果目录：`artifacts/metric_readable_bev_all_frontiers_splits1_3/`

## 3. 结果如何保存

每个结果目录中保留：

| 文件 | 说明 |
| --- | --- |
| `eval_goatbench.yaml` | 运行配置。 |
| `log_0.00_1.00_{1,2,3}.log` | 三个 episode split 的日志和最终耗时。 |
| `success_by_snapshot_0.0_1.0_{1,2,3}.pkl` | task 级 snapshot success。 |
| `success_by_distance_0.0_1.0_{1,2,3}.pkl` | task 级 distance success。 |
| `spl_by_snapshot_0.0_1.0_{1,2,3}.pkl` | task 级 snapshot SPL。 |
| `spl_by_distance_0.0_1.0_{1,2,3}.pkl` | task 级 distance SPL。 |
| `success_by_task_0.0_1.0_{1,2,3}.pkl` | image/object/description 三类 success。 |
| `spl_by_task_0.0_1.0_{1,2,3}.pkl` | image/object/description 三类 SPL。 |
| `vlm_timing.json` | VLM 请求耗时。 |

总表也已写入：

- `metrics/metrics_summary.csv`
- `metrics/metrics_summary.json`

## 4. 三个 episode 的核心指标

| Episode split | 任务数 | 方法 | Snapshot success | Distance success | Snapshot SPL | Distance SPL | 完成段耗时 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| split 1 | 278 | baseline/fix | 20.50% | 44.24% | 16.29% | 31.66% | 14:02:41 |
| split 1 | 278 | metric readable-BEV | **33.09%** | **56.83%** | **23.18%** | **37.43%** | 20:09:44 |
| split 2 | 255 | baseline/fix | 19.22% | 38.43% | 13.75% | 26.37% | 13:35:03 |
| split 2 | 255 | metric readable-BEV | **21.96%** | **41.18%** | **15.92%** | **29.12%** | 20:35:10 |
| split 3 | 277 | baseline/fix | 15.16% | 36.82% | 11.38% | 25.33% | 17:24:40 |
| split 3 | 277 | metric readable-BEV | **25.27%** | **45.49%** | **18.78%** | **30.60%** | 06:29:45 |

## 5. 三 episode 合并结果

| 指标 | baseline/fix 0.05 m | metric readable-BEV | 提升 |
| --- | ---: | ---: | ---: |
| Snapshot success | 18.27% | **26.91%** | **+8.64 pp** |
| Distance success | 39.88% | **48.02%** | **+8.14 pp** |
| Snapshot SPL | 13.84% | **19.39%** | **+5.55 pp** |
| Distance SPL | 27.86% | **32.49%** | **+4.63 pp** |

结论：

- `feat/metric-frontier-readable-bev` 在 split 1/2/3 四项指标全部高于 baseline/fix。
- 三 episode 合并后，Snapshot success 和 Distance success 均提升约 8 个百分点。
- 这说明 readable-BEV 的收益不是单个 episode 偶然造成的。
- 代价是 VLM 输入更复杂，运行耗时更长。

## 6. 运行时间和 VLM 调用时间

时间这里必须分两个口径看，详细核实见 `../结果/时间和VLM调用核实.md`。

| 方法 | split 1 完成段 | split 2 完成段 | split 3 完成段 | 完成段合计 | log 累计尝试合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline/fix | 14:02:41 | 13:35:03 | 17:24:40 | 45:02:24 | 46:13:58 |
| metric readable-BEV | 20:09:44 | 20:35:10 | 06:29:45 | 47:14:39 | 69:27:35 |

如果只看最终完成段，readable-BEV 比 baseline/fix 多 2:12:15，平均每个 task 多约 9.8 秒。这个口径适合描述最终结果文件对应的完成运行。

但它不是完整尝试成本：baseline/fix split 1 前面有 01:11:34 中断段；metric readable-BEV split 3 前面有 22:12:56 中断段，续跑时跳过 27 个已完成 scene。若把同一 log 中中断后续跑也计入，readable-BEV 比 baseline/fix 多 23:13:37。

VLM 调用也要按日志末尾 summary 和全 log HTTP POST 分开看：

| 方法 | VLM 成功请求合计 | 全 log HTTP POST 合计 | API 响应总时长合计 | 说明 |
| --- | ---: | ---: | ---: | --- |
| baseline/fix | 11,330 | 11,598 | 19:44:16 | split 1 的 timing summary 不含前 01:11:34 中断段的 268 次 HTTP POST。 |
| metric readable-BEV | 11,778 | 16,868 | 25:22:19 | split 3 的 timing summary 只覆盖最后 06:29:45 完成段，不含前 22:12:56 中断段的大量请求。 |

因此汇报时应写：主方法更准，但不是更快；若考虑中断/续跑产生的真实尝试成本，readable-BEV 的时间和请求开销明显更高。`vlm_timing.json` 记录每次 `chat.completions.create` 的 API 响应时间，不包含本地图像准备、导航执行和 retry sleep，也不一定覆盖中断段。

## 7. 按任务类型拆分

### split 1

| 类型 | baseline/fix Distance success | metric readable-BEV Distance success |
| --- | ---: | ---: |
| image | 37.50% | **50.00%** |
| object | 54.55% | **72.73%** |
| description | 39.56% | **46.15%** |

### split 2

| 类型 | baseline/fix Distance success | metric readable-BEV Distance success |
| --- | ---: | ---: |
| image | 29.55% | **34.09%** |
| object | 54.44% | 51.11% |
| description | 29.87% | **37.66%** |

### split 3

| 类型 | baseline/fix Distance success | metric readable-BEV Distance success |
| --- | ---: | ---: |
| image | 27.71% | **37.35%** |
| object | 42.86% | **60.00%** |
| description | 38.20% | 35.96% |

任务类型拆分说明：这些数值来自 `success_by_task_*.pkl` 中的 `image/object/description` 列表。

## 8. 和 main 的关系

`main` 是原始 SCOPE 历史基线，默认 10 cm TSDF。原始 `main_experience` 目录已经删除，只保留文字归档：

| 范围 | Snapshot success | Distance success | Snapshot SPL | Distance SPL |
| --- | ---: | ---: | ---: | ---: |
| 历史全数据集，2,669 tasks | 23.98% | 43.12% | 18.67% | 31.14% |
| split 1，278 tasks | 23.74% | 45.32% | 18.68% | 33.43% |
| split 2，255 tasks | 23.92% | 41.96% | 17.71% | 28.72% |

这部分只作为历史参考，不作为当前最公平主对照。原因是：

- `main` 是 10 cm TSDF。
- 当前 baseline/fix 和 metric readable-BEV 都是 5 cm TSDF。
- `main` 原始 pkl、图片、日志目录已删除，无法完整复算。

因此正式结论应主要使用本文件第 4/5 节的 baseline/fix vs metric readable-BEV 对照。

## 9. 推荐结论写法

可以在汇报中写：

> 在三个 GOAT-Bench episode split 上，`feat/metric-frontier-readable-bev` 相对 5 cm 非 BEV baseline/fix 在四项核心指标上均取得提升。三 episode 合并后，Snapshot success 从 18.27% 提升到 26.91%，Distance success 从 39.88% 提升到 48.02%。该结果说明，把米制 frontier、共坐标 semantic/Gaussian BEV 和结构化输出加入高层 VLM 决策，对导航成功率有稳定帮助。

不要写：

> 该提升只来自 Gaussian BEV。

因为该分支同时改变了 frontier 物理参数、VLM 输入图和结构化输出协议，当前实验验证的是整组改动的总效应。

## 10. 后续要做什么

1. 保留 `feat/metric-frontier-readable-bev` 作为当前主结果分支。
2. 如果要把 `feat/semantic-bev-dedupe-smoothing` 作为最终代码，需要补跑 split 2/3。
3. 若要做更细消融，应单独控制变量，例如：
   - 只开 semantic BEV；
   - semantic + Gaussian；
   - 米制 frontier 参数 vs 旧像素参数。
