# 已删除 `main_experience` 结果归档

**建立日期：** 2026-07-22  
**原结果目录：** `/mnt/data/SCOPE/results/main_experience`  
**状态：** 原始目录已删除；未发现回收站或同名备份。本文档保存删除前已读取、或在项目历史技术报告中已记录的数值。它不是原始 pkl、日志或图片的替代品。

## 1. 恢复范围与可信度

- 原目录在删除前包含 `log_0.00_1.00_{1..7}.log`、各 split 的 `*_by_*.pkl`、`*_all.pkl`、运行配置和过程图片。
- 删除后，该路径在 XFS 文件系统上不存在，未发现 Trash 或备份目录；原始图片、逐任务 pkl、日志细节和可视化不能在此目录中恢复。
- 下文标记为“直接读取记录”的指标，是删除前在本轮会话中从对应 pkl 读取的结果。
- 下文标记为“历史报告记录”的指标，来自仍保留的 `docs/SCOPE_THREE_WAY_TECHNICAL_REPORT_2026-07-16.md`。
- 因为结果目录没有保存可追溯 git SHA，`main` 分支归属依据原目录名称、用户说明与历史报告；不要把本文档当作可重放的 commit-level provenance。

## 2. main 历史运行配置

历史 main 使用原始 SCOPE 决策流程：TSDF、scene graph、snapshots、frontier 和 PotentialGraph；VLM 接收目标、第一视角、snapshot/object crop 和 frontier 缩略图，输出旧式文本选择。

- TSDF grid size：`0.1 m`
- 候选：旧式全部 frontier 缩略图/文本选择
- VLM 协议：`Snapshot i, Object j` 或 `Frontier i`
- 这是历史主分支基线；它与后来的 5 cm 物理尺度归一化 fix 并不属于完全相同的地图/候选配置。

## 3. main 全数据集历史汇总

来源：**历史报告记录**。范围为 10 个 episode、2,669 个子任务。SPL 有 16 个 NaN，因此 SPL 在 2,653 个有效值上计算。

| 指标 | main 历史全数据集 |
|---|---:|
| Snapshot success | 23.98% |
| Snapshot SPL | 18.67% |
| Distance success | 43.12% |
| Distance SPL | 31.14% |

> 这是一份跨多日、多次续跑的历史累计结果，不能直接与一次只跑一个 split 的结果作未配对比较。

## 4. 与当前评测任务一致的 main 分 split 结果

### 4.1 Split 1：Episode 0，278 个子任务

来源：**直接读取记录**，且同样记录在历史报告中。任务 key 与当前 metric/fix split 1 完全一致。

| 指标 | main (0.1 m) | 精确计数（如适用） |
|---|---:|---:|
| Snapshot success | 23.74% | 66 / 278 |
| Snapshot SPL | 18.68% | — |
| Distance success | 45.32% | 126 / 278 |
| Distance SPL | 33.43% | — |

### 4.2 Split 2：Episode 1，255 个子任务

来源：**删除前直接读取记录**。任务 key 与当前 metric/fix split 2 完全一致。

| 指标 | main (0.1 m) | 精确计数（如适用） |
|---|---:|---:|
| Snapshot success | 23.92% | 61 / 255 |
| Snapshot SPL | 17.71% | — |
| Distance success | 41.96% | 107 / 255 |
| Distance SPL | 28.72% | — |

### 4.3 Split 1 + Split 2 合并，533 个子任务

Snapshot/Distance success 由上面的整数成功数精确汇总；SPL 是根据已记录的两位小数 split 均值加权计算，因此仅作近似参考。

| 指标 | main 合并结果 |
|---|---:|
| Snapshot success | 23.83% (127 / 533) |
| Distance success | 43.71% (233 / 533) |
| Snapshot SPL | 约 18.22% |
| Distance SPL | 约 31.18% |

## 5. 历史 main、当前公平 fix 与当前 metric 的关系

### 5.1 当前正式公平对照

当前正式 baseline 是：

```text
/mnt/data/SCOPE/results/baseline_of_metric-frontier-readable-bev
branch: baseline/fix-tsdf05cm
TSDF: 0.05 m，使用物理尺度 frontier 归一化
```

当前 metric 是：

```text
/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-all-frontiers
branch: feat/metric-frontier-readable-bev
TSDF: 0.05 m，semantic BEV + evidence BEV + SCOPE-ranked frontiers + JSON 协议
```

### 5.2 Split 1（278 tasks）

| 指标 | 历史 main 0.1 m | 当前 fix 0.05 m | 当前 metric 0.05 m |
|---|---:|---:|---:|
| Snapshot success | 23.74% | 20.50% | **33.09%** |
| Snapshot SPL | 18.68% | 16.29% | **23.18%** |
| Distance success | 45.32% | 44.24% | **56.83%** |
| Distance SPL | 33.43% | 31.66% | **37.43%** |

当前 metric 相对当前 fix：Snapshot success +12.59 pp、Distance success +12.59 pp、Snapshot SPL +6.89 pp、Distance SPL +5.77 pp。配对 Snapshot 结果：metric 独赢 47、fix 独赢 12、两者都成功 45、两者都失败 174。

### 5.3 Split 2（255 tasks）

| 指标 | 历史 main 0.1 m | 当前 fix 0.05 m | 当前 metric 0.05 m |
|---|---:|---:|---:|
| Snapshot success | **23.92%** | 19.22% | 21.96% |
| Snapshot SPL | **17.71%** | 13.75% | 15.92% |
| Distance success | **41.96%** | 38.43% | 41.18% |
| Distance SPL | 28.72% | 26.37% | **29.12%** |

当前 metric 相对当前 fix：Snapshot success +2.74 pp、Distance success +2.75 pp、Snapshot SPL +2.17 pp、Distance SPL +2.75 pp。配对 Snapshot 结果：metric 独赢 23、fix 独赢 16、两者都成功 33、两者都失败 183。

### 5.4 当前 fix 与 metric 的 Split 1 + 2 合并结果（533 tasks）

| 指标 | 当前 fix 0.05 m | 当前 metric 0.05 m | metric - fix |
|---|---:|---:|---:|
| Snapshot success | 19.89% | **27.77%** | +7.88 pp |
| Snapshot SPL | 15.07% | **19.70%** | +4.63 pp |
| Distance success | 41.46% | **49.34%** | +7.88 pp |
| Distance SPL | 29.13% | **33.46%** | +4.33 pp |

两 split 合并的 Snapshot 配对计数：metric 独赢 70、fix 独赢 28、两者都成功 78、两者都失败 357。

## 6. `baseline_ceping` 的定位（避免混淆）

`/mnt/data/SCOPE/results/baseline_ceping` 确实使用了 `tsdf_grid_size: 0.05`，但它是 2026-07-15 的旧 pilot。其配置缺少当前 fix 的物理尺度 frontier 参数，例如 `frontier_neighbor_radius_m`、`frontier_cluster_eps_m` 与 `min_frontier_area_m2`。因此它不能替代 `baseline_of_metric-frontier-readable-bev` 作为当前 metric 的正式公平对照。

## 7. 可使用与不可使用的结论

可以使用：

- main 的全数据集历史汇总；
- main 在 split 1/2 的四项核心指标；
- 当前 5 cm fix 与 metric 的完整 paired comparison；
- “当前 metric 在两个已完成 split 上均优于当前 5 cm fix”的结论。

不可再从原始结果恢复：

- main 的逐任务成功标签、逐场景统计、任务类型拆分；
- main 的 Episode 3–7 分 split 指标和各 split 原始 pkl；
- main 的截图、轨迹、VLM 输入与日志时间线；
- 从被删除目录追溯 git SHA 或重新计算显著性检验。

## 8. 审计来源

- 历史报告：`/mnt/data/SCOPE/docs/SCOPE_THREE_WAY_TECHNICAL_REPORT_2026-07-16.md`
- 当前 fix 结果：`/mnt/data/SCOPE/results/baseline_of_metric-frontier-readable-bev`
- 当前 metric 结果：`/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-all-frontiers`
- 原始 main 目录（已删除）：`/mnt/data/SCOPE/results/main_experience`

## 9. 2026-07-23：当前 metric all-frontier 与 fix 的三 Episode 正式对照

### 9.1 对照定义

这是当前最可复现、也最适合论文主表的对照：两个结果目录使用完全相同的 GoatBench task ID，均为 0.05 m TSDF。

- **fix 对照组**：`/mnt/data/SCOPE` 的 `baseline/fix-tsdf05cm`，commit `8d4a4c9`，结果目录为 `/mnt/data/SCOPE/results/baseline_of_metric-frontier-readable-bev`。
- **metric 方法**：`/mnt/data/SCOPE_metric_frontier_bev` 的 `feat/metric-frontier-readable-bev`，commit `f36b247`，结果目录为 `/mnt/data/SCOPE_metric_frontier_bev/results/metric-frontier-readable-bev-all-frontiers`。

metric 除沿用 5 cm 的物理尺度 frontier 设定外，新增语义/高斯 BEV、向 VLM 提供所有 frontier（`F1..Fn`）、frontier 排序与 JSON 决策/解析协议。因此下表报告的是**完整 metric 方法相对 fix 的总效应**，不能单独归因于 Gaussian BEV。

### 9.2 各 Episode 指标

| Episode（命令 split） | 任务数 | 方法 | Snapshot success | Distance success | Snapshot SPL | Distance SPL |
|---|---:|---|---:|---:|---:|---:|
| ep_0（split 1） | 278 | fix | 20.50% | 44.24% | 16.29% | 31.66% |
| ep_0（split 1） | 278 | metric | **33.09%** | **56.83%** | **23.18%** | **37.43%** |
| ep_1（split 2） | 255 | fix | 19.22% | 38.43% | 13.75% | 26.37% |
| ep_1（split 2） | 255 | metric | **21.96%** | **41.18%** | **15.92%** | **29.12%** |
| ep_2（split 3） | 277 | fix | 15.16% | 36.82% | 11.38% | 25.33% |
| ep_2（split 3） | 277 | metric | **25.27%** | **45.49%** | **18.78%** | **30.60%** |

metric 在三个独立 episode 上四项核心指标都高于 fix。其中 ep_1 的绝对提升较小（Snapshot +2.74 pp），但方向仍一致；ep_0 与 ep_2 的增益更明显。

### 9.3 三 Episode 合并结果（810 tasks）

| 指标 | fix 0.05 m | metric all-frontier | metric - fix |
|---|---:|---:|---:|
| Snapshot success | 18.27% | **26.91%** | **+8.64 pp** |
| Distance success | 39.88% | **48.02%** | **+8.14 pp** |
| Snapshot SPL | 13.84% | **19.39%** | **+5.55 pp** |
| Distance SPL | 27.86% | **32.49%** | **+4.63 pp** |

三 episode 合并后，metric 在 Snapshot success 上提高 8.64 个百分点、Distance success 上提高 8.14 个百分点；SPL 也同步提高。这说明当前结果并非只由单个 episode 驱动，三个已完成 episode 的方向一致。

### 9.4 逐任务配对 Snapshot 结果（同一 task ID）

| Episode | metric 独赢 | fix 独赢 | 两者都成功 | 两者都失败 |
|---|---:|---:|---:|---:|
| ep_0 | 47 | 12 | 45 | 174 |
| ep_1 | 23 | 16 | 33 | 183 |
| ep_2 | 37 | 9 | 33 | 198 |
| **合计（810）** | **107** | **37** | **111** | **555** |

“metric 独赢”表示 metric 成功而 fix 失败；“fix 独赢”反之。三 episode 合计中 metric 净多成功 70 个 task（107 vs 37）。配对统计与均值指标的方向相同。

### 9.5 结果读取说明

- Snapshot/Distance success 是对应成功标记的均值；SPL 由每个 task 的 SPL 数值在有效 task 上取均值。
- `split 1/2/3` 在该评测中分别对应源数据的 `ep_0/ep_1/ep_2`。它们在同一环境资产下可能有不同起点、朝向和子任务序列，不能把它们理解为只换了一个目标。
- 评测设置 `clear_up_memory_every_subtask: false`：记忆会在**同一 episode 的子任务之间**保留；不会从 split 1 传到 split 2 或 split 3。
