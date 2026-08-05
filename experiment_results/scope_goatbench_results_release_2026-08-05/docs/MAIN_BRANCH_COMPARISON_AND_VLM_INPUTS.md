# `feat/metric-frontier-readable-bev` 相对 `main` 的改动与 VLM 图像输入

> 生成日期：2026-07-18  
> 对比分支：`main...feat/metric-frontier-readable-bev`（HEAD: `f36b247`）  
> 当前实验输出：`results/metric-frontier-readable-bev-all-frontiers`

## 结论

该分支不是只改变可视化。它把**物理尺度的 frontier 生成**、**给高层 VLM 的两张结构化 BEV 图**、以及**不截断的 frontier 候选空间**组合成新的决策输入；底层 SCOPE 导航执行仍沿用原有路径。

相对 `main`，当前运行配置从 `exp_eval_goatbench` 改为 `metric-frontier-readable-bev-all-frontiers`，TSDF 由 `0.10 m` 改为 `0.05 m`，并开启 `structured_bev_for_vlm: true` 和 `structured_bev_max_frontiers: 0`。其中 `0` 的含义是向 VLM 暴露全部有效 frontier，而不是只取 top-k。

工作区还有一个未跟踪目录 `tmp0k5zf9g_/`；本文不把它视为该分支相对 `main` 的代码改动。

## 主要改动

| 范围 | 相对 `main` 的变化 | 对决策的影响 |
| --- | --- | --- |
| TSDF / frontier | 规划体素从 10 cm 改为 5 cm；frontier 的邻域、未知比例、DBSCAN 聚类半径和最小面积改用米制配置，再按当前体素大小换算。 | 保持 5 cm 分辨率时仍使用一致的物理尺度，而不是复用 10 cm 下的像素阈值。 |
| VLM 候选空间 | `PotentialGraph` 仍按 SCOPE 分数排序 F1..Fn，但 `structured_bev_max_frontiers: 0` 不再用该分数截断候选。 | 高层 VLM 可在所有有效 frontier 中选择；SCOPE 分数是证据和排序，不是强制动作。 |
| Semantic BEV（新增） | 新增 `src/tsdf_export.py`，在每次高层决策前导出裁剪后的语义地图。图中包含未知/可通行/探索/障碍、轨迹、当前朝向、F1..Fn 以及物体类别。 | VLM 可把目标相关上下文、已探索区域和 frontier 位置放在同一坐标系里判断。 |
| 语义几何校验 | ConceptGraph 的原始 3D OBB 只作候选假设；过大、没有 TSDF 障碍支撑、或与执行轨迹冲突的对象会被过滤。保留下来的内容渲染为紧凑的 TSDF 支撑 footprint。 | 避免把可穿越轨迹上的巨大 tracker box 当成真实障碍/物体证据输入 VLM。 |
| Gaussian evidence BEV（新增） | 对每个候选 frontier 画 future-evidence 高斯层；颜色与 semantic BEV 的 F 标签一致，半径是启发式不确定性。 | VLM 能结合地图上下文和 SCOPE 的 future-evidence 进行选择；该半径不是校准概率。 |
| Prompt / 协议 | 决策 prompt 加入两张 BEV 的图例和约束；前沿缩略图紧跟两张 BEV，之后才是 snapshots 与 object crops。输出采用结构化 JSON，并兼容映射回原有的 snapshot/frontier 选择。 | 减少 F 标签与缩略图被 snapshots 分隔的情况，同时不改变低层执行接口。 |
| 可追溯性与计时 | 每次实际 VLM 调用保存完整输入 bundle（图片、文本顺序、源 BEV 路径）；新增按 decision / prefilter / self-refine 等类型记录 API 请求时延的 `vlm_timing.json`。 | 可以复查 VLM 当时真正看到了哪些图，也能单独比较模型调用开销。 |
| 稳定性 | 合入 stale snapshot object-ID 防护，并保留原有 frontier、snapshot、potential graph 等结果目录。 | 降低 snapshot 指向已失效对象的风险，且不丢失原始审计信息。 |

## 关键配置差异

当前 `cfg/eval_goatbench.yaml` 的决定性新增/变化项如下：

```yaml
exp_name: metric-frontier-readable-bev-all-frontiers
tsdf_grid_size: 0.05
tsdf_bev_render_resolution: 0.05
tsdf_bev_min_object_detections: 2
tsdf_bev_max_labeled_instances: 8
tsdf_bev_crop_padding_m: 1.5
tsdf_bev_min_crop_size_m: 6.0
structured_bev_for_vlm: true
structured_bev_max_frontiers: 0  # 不截断，全部有效 frontier 都进 VLM
structured_bev_fill_context_instances: true
planner:
  frontier_neighbor_radius_m: 0.10
  frontier_cluster_eps_m: 0.10
  min_frontier_area_m2: 0.20
```

旧的像素阈值仍留作兼容 fallback；当前评测 YAML 使用上述米制 frontier 字段。

## 实际新增到 VLM 的图片

在当前实现中，高层决策的主要内容顺序为：任务图（若有） → 当前 egocentric RGB → **Input A semantic BEV** → **Input B Gaussian evidence BEV** → 全部 F1..Fn frontier 缩略图 → snapshots 与每个 object crop。

| 新输入 | 生成位置 | 图中内容 | 代码路径 |
| --- | --- | --- | --- |
| Input A：structured semantic BEV | `<episode>/potential_graph/vlm_bev/*_semantic_bev.png` | TSDF 地图状态、经过校验的物体 footprint/类别、轨迹、当前位姿、候选 F1..Fn。 | `src/tsdf_export.py::save_bev_visualization` |
| Input B：frontier future-evidence BEV | `<episode>/potential_graph/vlm_bev/*_evidence_gaussian_bev.png` | 与 Input A 完全相同的裁剪坐标系；按候选 F 标签着色的 evidence / 启发式不确定性层。 | `src/tsdf_export.py::save_frontier_gaussian_bev` |
| 审计副本 | `<episode>/visualization/bev_gaussian/` | 与实际送入 VLM 的 Gaussian 图片完全相同，仅额外复制供人工检查。 | `run_goatbench_evaluation.py` |
| 完整 prompt bundle | `results/.../vlm_full_inputs/<request>/` | `content_order.md`、`manifest.json` 和按照实际顺序保存的 `content_*.png`。 | `src/eval_utils_gpt_goatbench.py::_save_vlm_input_bundle` |

### 一次真实调用的新增输入示例

以下图片来自正在运行的 `00880-Nfvxx8J5NCo`、子任务 `0_4` 的保存 bundle `1784357960035_00880-Nfvxx8J5NCo_0_4`。它们不是事后重画图：分别就是 VLM payload 的 `content_005.png`（Input A）和 `content_007.png`（Input B）。相应的 `content_order.md` 还记录了随后三张 frontier 图、四组 snapshots/object crops 及其文本顺序。

**Input A — Structured semantic BEV**

![Exact semantic BEV sent to VLM](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/content_005.png)

**Input B — Frontier future-evidence BEV**

![Exact Gaussian evidence BEV sent to VLM](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/content_007.png)

同一轮请求的可审计输入顺序见 [content_order.md](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/content_order.md)，源文件路径与 bundle 图片的一一对应关系见 [manifest.json](../results/metric-frontier-readable-bev-all-frontiers/vlm_full_inputs/1784357960035_00880-Nfvxx8J5NCo_0_4/manifest.json)。

## 保持不变的边界

- 高层 VLM 选择的仍是现有 snapshot 或 frontier；输出仍会转换回原有的执行接口。
- SCOPE PotentialGraph 的评分仍用于排序和 evidence 表达，但在当前配置下不负责删掉低排名 frontier。
- 低层路径规划、TSDF 融合、frontier 执行和最终物理验证没有被结构化图片替换。
- 输出图片和 VLM 输入 bundle 是新增的审计信息；它们不等同于对结果做事后可视化重建。

## 涉及的主要文件

- `cfg/eval_goatbench.yaml`
- `run_goatbench_evaluation.py`
- `src/tsdf_export.py`（新增）
- `src/tsdf_planner.py`
- `src/query_vlm_goatbench.py`
- `src/eval_utils_gpt_goatbench.py`
- `src/potential_graph.py`、`src/potential_estimation_gpt_goal.py`
- `src/vlm_timing.py`（新增）
- `run_goatbench_all_splits.py`、`scripts/compare_vlm_timing.py`

## 全量实验结果（已完成）

`metric-frontier-readable-bev-all-frontiers` 已在日志中输出 `All scenes finish`，共完成 278/278 个子任务，耗时 `20:09:44`。以下四组实验的子任务 ID 完全一致，因此可直接横向比较：

| 指标 | all-frontiers（本分支） | scope-bev | baseline | exp |
| --- | ---: | ---: | ---: | ---: |
| Success by snapshot | **33.09%** | 22.30% | 20.50% | 23.74% |
| Success by distance | **56.83%** | 50.00% | 40.65% | 45.32% |
| SPL by snapshot | **23.18%** | 17.96% | 17.13% | 18.68% |
| SPL by distance | 37.43% | **37.75%** | 29.11% | 33.43% |

结论：本分支在 snapshot success、distance success、snapshot SPL 三项第一。相对相应的最强对照分别提升 `+9.35 pp`、`+6.83 pp`、`+4.50 pp`；distance SPL 只比 `scope-bev` 低 `0.32 pp`，基本持平。

按任务类型，image 的 success / SPL 都是第一；object 与 description 的 success 也都是第一，但 SPL 仍分别低于 `scope-bev` 和 `exp` 的最佳值。这说明该分支显著提高了找到正确目标的概率，但在部分对象/描述任务中仍有路径效率优化空间。

本次运行共记录 4,925 次成功 VLM 请求，单次成功请求平均 `7.784 s`；其中 decision 调用平均 `14.364 s`。这些时延仅统计 API 请求本身，不包含图片准备、重试等待和导航计算。

## 成对任务的深入检查

下面的比较不是把不同数据集的均值放在一起，而是对每个相同的子任务 ID 逐一比较。278 个任务的组成是 image 88、object 99、description 91。

### 相对最强效率对照 `scope-bev`

| 二元指标 | all-frontiers 胜 / 负 / 平 | exact McNemar p 值 |
| --- | ---: | ---: |
| Success by snapshot | 49 / 19 / 210 | 0.00036 |
| Success by distance | 45 / 26 / 207 | 0.03193 |

这说明相对 `scope-bev` 的成功率提升并非只由少数任务的均值造成：在 distance success 上，本分支多赢 19 个任务，最终多成功 `158 - 139 = 19` 个。

但 distance SPL 的细节也解释了为什么总体只差 `-0.32 pp`：

- 在双方都 distance-success 的 113 个任务上，本分支的平均 distance SPL 为 `64.50%`，`scope-bev` 为 `74.76%`。
- 仅在各自成功的任务中计算，本分支为 `65.86%`（158 个成功），`scope-bev` 为 `75.50%`（139 个成功）。

因此更准确的表述是：**本分支用更长的探索路径换来了更多成功**；它没有在每个已成功任务上都找到更短路径。这是合理的候选空间扩大代价，但仍是后续可优化的方向。

### 分任务类型

| 类型 | Success by distance：all-frontiers / scope-bev | Distance SPL：all-frontiers / scope-bev | 观察 |
| --- | ---: | ---: | --- |
| image（88） | 50.00% / 42.05% | 36.81% / 30.40% | 成功率和效率都提升。 |
| object（99） | 72.73% / 65.66% | 44.05% / 49.73% | 更常找到对象，但成功路径更长。 |
| description（91） | 46.15% / 40.66% | 30.84% / 31.83% | 成功率提升，效率基本持平但略低。 |

### 运行开销

| 项目 | all-frontiers | scope-bev | 变化 |
| --- | ---: | ---: | ---: |
| 总耗时 | 20:09:44 | 19:14:47 | +54:57 |
| 单次成功 VLM 请求均值 | 7.784 s | 6.826 s | +14.0% |
| decision 请求均值 | 14.364 s | 11.328 s | +26.8% |
| 平均过滤后 snapshots | 5.51 | 3.73 | +1.77 |

增加的 BEV 图、更多有效 frontier 以及更多保留 snapshot 与更高 success 一起带来额外 VLM 成本。这里的成对 p 值只描述这一次评测中任务级差异的稳定性；它**不是**多随机种子 / 多次 VLM 采样的置信结论。当前分支同时改变了 TSDF 分辨率、frontier 物理阈值、候选空间与 VLM 图片输入，不能把全部收益单独归因给任一项改动。
