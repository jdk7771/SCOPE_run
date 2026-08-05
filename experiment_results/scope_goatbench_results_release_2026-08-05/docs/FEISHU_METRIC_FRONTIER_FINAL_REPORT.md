# Metric Frontier + Readable BEV：最终实验报告

> 适用方式：可直接粘贴或导入飞书文档的 Markdown。  
> 日期：2026-07-19  
> 当前分支：`feat/metric-frontier-readable-bev`（HEAD `f36b247`）  
> 评测集：GOAT-Bench val_unseen，split 1，36 个场景，278 个过滤后子任务。

---

## 1. 一句话结论

`feat/metric-frontier-readable-bev` 的 all-frontiers 版本完成了全部 278 个相同子任务。在四个结果中，它在 **snapshot success、distance success、snapshot SPL** 三项第一；distance SPL 为 `37.43%`，仅比最强对照 `feat/structured-bev-tsdf05cm` 的 `37.75%` 低 `0.32 pp`。

更准确的解释是：**本方法以一定的额外探索长度和运行成本，显著提高了找到正确目标的概率。** 它不是“每个成功任务都走得更短”，而是“更多任务能够成功完成”。

---

## 2. 实验结果与数据来源

四组结果使用相同的 278 个子任务 ID；统计直接读取各目录的 `*_0.0_1.0_1.pkl`，不是不同数据规模的均值拼接。

| 代码版本 | 结果目录 | 对应配置定位 |
| --- | --- | --- |
| `feat/metric-frontier-readable-bev`（all-frontiers） | `results/metric-frontier-readable-bev-all-frontiers` | 5 cm TSDF、structured BEV、全部 frontier。 |
| `feat/structured-bev-tsdf05cm`（feat） | `/mnt/data/SCOPE/results/_scope_bev_vlm_gussion_ceping` | 5 cm TSDF、structured BEV、`structured_bev_max_frontiers: 3`。 |
| `baseline/fix-tsdf05cm`（fix） | `/mnt/data/SCOPE/results/baseline_ceping` | 5 cm TSDF 的非 structured-BEV 基线。 |
| `main` | `/mnt/data/SCOPE/results/main_experience` | 原始 `exp_eval_goatbench` 配置：10 cm TSDF、没有 structured-BEV 配置。 |

### 2.1 全量核心指标

| 指标 | all-frontiers | feat | fix | main |
| Success by snapshot | **33.09%** | 22.30% | 20.50% | 23.74% |
| Success by distance | **56.83%** | 50.00% | 40.65% | 45.32% |
| SPL by snapshot | **23.18%** | 17.96% | 17.13% | 18.68% |
| SPL by distance | 37.43% | **37.75%** | 29.11% | 33.43% |

相对每项最强对照，all-frontiers 的变化为：

- Snapshot success：`+9.35 pp`；
- Distance success：`+6.83 pp`；
- Snapshot SPL：`+4.50 pp`；
- Distance SPL：`-0.32 pp`（与最佳值基本持平）。

### 2.2 运行时间与 VLM 开销

| 指标 | all-frontiers | feat | fix | main |
| --- | ---: | ---: | ---: | ---: |
| 端到端运行时间 | 20:09:44 | 19:14:47 | 15:39:34 | 10:23:45 |
| 成功 VLM 请求数 | 4,925 | 4,961 | 4,059 | 未保存可比 timing artifact |
| 单次成功 VLM 请求均值 | 7.784 s | 6.826 s | 6.318 s | 未保存可比 timing artifact |
| Decision 请求均值 | 14.364 s | 11.328 s | 未在本报告使用 | 未保存可比 timing artifact |
| 平均过滤后 snapshots | 5.51 | 3.73 | 未在本报告使用 | 未在本报告使用 |

运行时间和 API 时延是同一远端环境下的实测日志值，但并非严格的硬件基准：不同方法会发起不同数量的 VLM 请求、保留不同数量的 snapshots，也会有不同的探索轨迹。因此它们应被解释为真实的实验开销，而非单一算子性能。

---

## 3. “成功更多”与“路径更短”是两件事

与最接近的 `feat/structured-bev-tsdf05cm`（下文简称 feat）对照做逐任务配对，而不是只比较均值：

| 指标 | all-frontiers 胜 / 负 / 平 | exact McNemar p 值 |
| --- | ---: | ---: |
| Success by snapshot | 49 / 19 / 210 | 0.00036 |
| Success by distance | 45 / 26 / 207 | 0.03193 |

all-frontiers 在 distance success 上比 feat 多成功 `158 - 139 = 19` 个任务。该优势不是几个异常任务抬高均值造成的：在成对比较中，成功更多的任务显著多于失败更多的任务。

但在双方都 distance-success 的 113 个子任务上：

| 条件 | all-frontiers distance SPL | feat distance SPL |
| --- | ---: | ---: |
| 双方都成功的 113 个任务 | 64.50% | 74.76% |
| 各自成功的全部任务 | 65.86%（158 个） | 75.50%（139 个） |

因此，all-frontiers 的策略倾向于进行更多探索来换取额外成功；这解释了为什么总体 distance SPL 与 feat 几乎持平，而非同步大幅领先。

### 3.1 分任务类型

| 类型 | 子任务数 | Distance success：all / feat | Distance SPL：all / feat | 解读 |
| --- | ---: | ---: | ---: | --- |
| image | 88 | 50.00% / 42.05% | 36.81% / 30.40% | 成功率和路径效率都提升。 |
| object | 99 | 72.73% / 65.66% | 44.05% / 49.73% | 更常找到对象，但成功时路径更长。 |
| description | 91 | 46.15% / 40.66% | 30.84% / 31.83% | 成功率提升，效率接近但略低。 |

---

## 4. 为什么同时对比 `main` 和 `feat/structured-bev-tsdf05cm`

这是一个有层次的消融链，而不是只挑一个弱基线：

```text
main
  10 cm TSDF；原始高层 VLM 输入
          │
          ├── baseline/fix-tsdf05cm
          │     5 cm TSDF；不加 structured BEV
          │
          └── feat/structured-bev-tsdf05cm
                5 cm TSDF + structured semantic / Gaussian BEV + top-3 frontier
                        │
                        └── feat/metric-frontier-readable-bev / all-frontiers
                              5 cm + 米制 frontier + 语义几何校验
                              + 可读、共坐标 BEV + 所有有效 frontier
```

### 4.1 `main` 是端到端基线

`main` 的评测配置是 `tsdf_grid_size: 0.1`，实验名为 `exp_eval_goatbench`。它回答的问题是：**完整新方法相对原始系统到底是否有端到端收益？**

all-frontiers 相对 main：

| 指标 | 提升 |
| --- | ---: |
| Success by snapshot | +9.35 pp |
| Success by distance | +11.51 pp |
| SPL by snapshot | +4.50 pp |
| SPL by distance | +4.00 pp |

这组对比对用户最重要，因为它包含真实使用时从原始系统升级到当前分支的总收益。

### 4.2 `feat/structured-bev-tsdf05cm` 是最近的机制基线

该分支是当前分支的直接祖先（当前分支从提交 `1623bd9` 继续开发）。它已经具备：

- `tsdf_grid_size: 0.05`；
- `structured_bev_for_vlm: true`；
- semantic BEV、Gaussian evidence BEV 和结构化 VLM 决策；
- `structured_bev_max_frontiers: 3`，即只给高层 VLM top-3 候选。

因此它控制了“5 cm TSDF”和“structured BEV 已经存在”这两个重要因素。all-frontiers 相对它的提升更能说明当前分支后续改动的价值：

| 指标 | all-frontiers - feat |
| --- | ---: |
| Success by snapshot | +10.79 pp |
| Success by distance | +6.83 pp |
| SPL by snapshot | +5.22 pp |
| SPL by distance | -0.32 pp |

这比只和 main 比更有诊断价值：它表明收益并不只是“把 TSDF 从 10 cm 改成 5 cm”或“第一次加入 BEV”带来的。

### 4.3 fix 的补充价值

`baseline/fix-tsdf05cm` 使用 5 cm TSDF、没有 structured-BEV 配置，distance success 为 `40.65%`，低于 main 的 `45.32%`。这表明**仅提高 TSDF 分辨率并不能保证提升**；结构化地图输入与后续 frontier 改动才是当前方法链中不可忽略的部分。

### 4.4 因果解释的边界

当前分支相对 `feat/structured-bev-tsdf05cm` 仍然是一次多改动更新，而不是只改一个开关。因此结果支持“这一组改动整体有效”，但不能仅凭一次运行把全部收益归因给某一个 commit 或某一张图。VLM 调用存在随机性；若需要可发表的单项因果结论，应固定模型参数并做多 seed / 多次 API 运行的 ablation。

---

## 5. `feat/metric-frontier-readable-bev` 的方法论改动

### 5.1 从 `main` 到 structured BEV 分支的基础能力

`main...feat/structured-bev-tsdf05cm` 引入了：

- 5 cm TSDF；
- semantic BEV 与 frontier future-evidence Gaussian BEV；
- 与高层 VLM 决策相结合的 structured JSON 输出；
- 任务相关的对象标签、frontier 得分可视化和 prompt 说明；
- VLM 请求分类计时。

### 5.2 当前分支相对 structured BEV 分支的新增改动

| 改动 | 代码位置 | 方法论意义 |
| --- | --- | --- |
| 米制 frontier 阈值 | `cfg/eval_goatbench.yaml`、`src/tsdf_planner.py` | 以 `0.10 m` 邻域、`0.10 m` 聚类半径、`0.20 m²` 最小面积等物理量生成 frontier；体素尺寸变化后仍保持同一物理含义。 |
| 所有 frontier 进入高层 VLM | `run_goatbench_evaluation.py` | `structured_bev_max_frontiers: 0` 表示不截断；PotentialGraph 只排序 F1..Fn，不删除候选。 |
| 语义 footprint 的 TSDF 校验 | `src/tsdf_export.py` | 原始 ConceptGraph 3D OBB 不直接画入 VLM 图；过大、无 TSDF 支撑、或覆盖执行轨迹的假设被过滤。 |
| 共坐标、裁剪后的可读 BEV | `src/tsdf_export.py` | semantic 与 Gaussian 图使用相同 crop；只显示对决策有帮助的已验证语义、轨迹、agent 和 F1..Fn。 |
| 稳定的对象 / snapshot 映射 | `src/query_vlm_goatbench.py`、相关评测代码 | 防护 stale snapshot object ID，避免 VLM 选择已失效对象。 |
| 完整 VLM 输入审计 | `src/eval_utils_gpt_goatbench.py` | 每次调用保存文本、图片次序、源 BEV 路径和 `content_*.png`。 |

这些改动的重点不是“绘制更漂亮的图”，而是让高层 VLM 同时拥有可信的几何上下文、完整候选空间和可回溯的输入证据。

---

## 6. 实际送入 VLM 的新增内容

每次高层决策的图片顺序是：

```text
任务图（若有）
→ 当前 egocentric RGB
→ Input A：Structured semantic BEV
→ Input B：Frontier future-evidence Gaussian BEV
→ 全部 F1..Fn frontier thumbnails
→ snapshots 与各 object crops
```

| 新输入 | 内容 | 作用 |
| --- | --- | --- |
| Input A：semantic BEV | 未知/可通行/探索/障碍状态、TSDF 支撑的语义 footprint、类别标签、轨迹、agent 朝向、F1..Fn。 | 把物体上下文、已探索空间和候选位置放入一个可读坐标系。 |
| Input B：Gaussian evidence BEV | 与 Input A 同一裁剪与坐标系；按 F 标签着色的 frontier future-evidence 与启发式不确定性。 | 让 VLM 将 SCOPE 分数作为证据，而不是强制命令。 |
| 全部 frontier thumbnails | 不再只显示 top-3；显示所有有效 F1..Fn。 | 避免正确 frontier 因低于 top-3 而永远不可选。 |
| 审计 bundle | `content_order.md`、`manifest.json`、每张实际输入图。 | 复盘 VLM 在某次决策中真正看到了什么。 |

### 6.1 真实 VLM 输入图示例

下面两张图来自完成实验中保存的真实请求：场景 `00880-Nfvxx8J5NCo`、子任务 `0_4`。它们分别是该 VLM payload 的 `content_005.png` 与 `content_007.png`，不是事后重绘。

**Input A — Structured semantic BEV**

![Input A：实际送入 VLM 的 semantic BEV](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/content_005.png)

**Input B — Frontier future-evidence Gaussian BEV**

![Input B：实际送入 VLM 的 Gaussian evidence BEV](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/content_007.png)

该次请求的完整图片与文字顺序见：

- [content_order.md](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/content_order.md)
- [manifest.json](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/manifest.json)

> 飞书使用提示：若通过 Markdown 导入后飞书无法解析仓库相对图片路径，请将上面两张 PNG 从对应路径拖入文档；图片本身就是实际 VLM 输入文件。

---

## 7. 最终判断与后续建议

1. 当前分支的整体方向是有效的：在完全相同的 278 个任务上，成功率提升明确，且 snapshot SPL 同步提升。
2. 最值得优化的不是继续提高成功率，而是降低 object / description 成功任务的路径长度，缩小与 feat 的 distance SPL 差距。
3. 优先建议的下一轮消融是固定 5 cm 与 structured BEV，只分别改变：
   - `structured_bev_max_frontiers: 3` vs `0`；
   - 米制 frontier 阈值开/关；
   - TSDF footprint 校验开/关。
4. 每组至少重复多个 seed 或 VLM 调用轮次。当前结果是强的单次端到端证据，但不是多次随机试验的最终置信区间。

---

## 8. Episode 目录案例：`00800-TEEsavR23oF_ep_0`

路径：`results/metric-frontier-readable-bev-all-frontiers/00800-TEEsavR23oF_ep_0`。这是一个适合复盘完整过程的 episode：共有 **5 个子任务**、**40 个执行/记录步**，其中 **28 次**需要高层 VLM 决策，因此保存了 28 组实际结构化 BEV 输入和 28 份完整 prompt bundle。

| 目录 | 实际数量 | 内容与用途 |
| --- | ---: | --- |
| `snapshot/` | 140 张 PNG | 原始 snapshot / keyframe RGB 视图；`i-view_j.png` 表示第 i 个 snapshot 的第 j 个朝向。是 snapshot 与 object crop 的源视觉证据。 |
| `frontier/` | 37 张 PNG | planner 生成的单个 frontier 第一视角候选图。文件会跨步复用，不等于每次决策都恰有 37 个候选。 |
| `frontier_video/` | 40 张 PNG | 每个执行步的一张候选拼图，标注 `Chosen` 或 `Snapshot Chosen`；用于人工回看最终选择，不是完整 prompt。 |
| `potential_graph/vlm_inputs/` | 41 张 PNG，且每张配套 JSON / TXT | 给 frontier-potential estimation 调用的单个 frontier 图、任务 metadata 和返回文本；它服务于 SCOPE potential 打分。 |
| `potential_graph/vlm_bev/` | 56 张 PNG = 28 semantic + 28 Gaussian | **高层 VLM 的实际新增输入**。每次需要新决策时，保存一对 `*_semantic_bev.png`（Input A）和 `*_evidence_gaussian_bev.png`（Input B）。 |
| `visualization/bev_gaussian/` | 28 张 PNG | `vlm_bev` 内 Gaussian Input B 的审计副本，与实际 VLM 输入相同。 |
| `visualization/bev_semantic/` | 40 张 PNG | 每次执行动作后的语义 BEV 检查图；因为它按执行步保存，数量可以多于高层 VLM 决策次数。要查看决策时的精确 Input A，应看 `potential_graph/vlm_bev/`。 |
| `visualization/bev_before/` | 40 张 PNG | 原有 top-down 调试图，额外叠加轨迹和评测目标标记；**不属于 VLM 输入**，也不应被当作模型可见信息。 |
| `potential_graph/potential_*.png` | 40 张 PNG | 每个执行步后的四宫格 PotentialGraph：Potential Score、Exploration Value、Visit Count、Smoothed Potential。 |
| `potential_graph/potential_after_frontier_*.png` | 41 张 PNG | 每次新 frontier 得到 potential-estimation 后的即时 PotentialGraph。 |
| `potential_graph/final_potential_*.png` | 5 张 PNG | 每个子任务结束时的最终 PotentialGraph。 |
| `potential_graph/potential_state_*.pkl` | 5 个文件 | 每个子任务结束时保存的可恢复图状态，不是图片。 |

文件名前缀 `<global_step>_00800-TEEsavR23oF_0_<subtask>` 中，`global_step` 跨整个 episode 递增，`subtask` 是当前 episode 0 内的子任务编号。因此同一子任务可能有多次高层选择或多步执行。

以下是该 episode 的第一组真实 VLM BEV 输入：

**Input A — semantic BEV**

![00800 episode: exact semantic BEV input](../results/metric-frontier-readable-bev-all-frontiers/00800-TEEsavR23oF_ep_0/potential_graph/vlm_bev/0_00800-TEEsavR23oF_0_0_semantic_bev.png)

**Input B — Gaussian evidence BEV**

![00800 episode: exact Gaussian evidence input](../results/metric-frontier-readable-bev-all-frontiers/00800-TEEsavR23oF_ep_0/potential_graph/vlm_bev/0_00800-TEEsavR23oF_0_0_evidence_gaussian_bev.png)

完整 VLM prompt（包含任务图、egocentric 图、两张 BEV、frontier thumbnails、snapshots 和 object crops）保存在 episode 目录之外的：`results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/*_00800-TEEsavR23oF_*`。该 episode 共保存 28 个这样的 bundle。
