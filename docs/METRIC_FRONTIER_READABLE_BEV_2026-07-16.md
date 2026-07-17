# Metric Frontier + Readable BEV 改动记录

- 日期：2026-07-16（America/New_York）
- 分支：`feat/metric-frontier-readable-bev`
- 基线：`feat/structured-bev-tsdf05cm`
- 兼容修复：合入 `fix/stale-snapshot-object-ids` 的 stale snapshot object-ID 防护。

## 改动目的

原 structured-BEV 仍以 5 cm TSDF 的像素尺度复用 10 cm 的前沿检测参数；同时实际送入 VLM 的 semantic / Gaussian BEV 存在大面积白色空白、agent 过大、对象标签含 `R#` / `C` / tracker ID、两图画布不一致等问题。本分支保留 5 cm TSDF 规划精度，但将前沿规则和 VLM 图表达改为物理尺度、可读且可追溯的形式。

## 1. 物理尺度前沿

`cfg/eval_goatbench.yaml` 新增并启用：

```yaml
frontier_neighbor_radius_m: 0.10
frontier_area_unknown_fraction_min: 1.00
frontier_area_unknown_fraction_max: 1.00
frontier_edge_unknown_fraction_min: 0.50
frontier_edge_unknown_fraction_max: 0.75
frontier_cluster_eps_m: 0.10
min_frontier_area_m2: 0.20
```

`TSDFPlanner.update_frontier_map()` 据此将物理阈值换算为当前 voxel 单位：

- 0.05 m 时 DBSCAN `eps=2 voxel`，保持 0.10 m 聚类半径；
- 最小 frontier 面积为 `ceil(0.20 / voxel_size²)`，即 0.05 m 时为 80 voxel；
- 未知邻域使用固定 0.10 m 半径与比例阈值，而非固定 3×3 像素计数。

旧的 `eps`、`min_frontier_area`、`frontier_area_*` 配置仍保留为旧 YAML 的兼容 fallback；本分支的评测 YAML 使用新物理字段。

## 2. Semantic BEV

- 浅蓝：未知 / 未观测；灰：已观测可通行；绿：已探索可通行；黑：障碍。
- 按已知地图、trajectory、agent、F1–F3 自动裁剪，并保留 1.5 m 边缘、最小 6 m 画幅，避免整张 TSDF volume 的空白占据视觉 token。
- agent 从原约 0.7 m、带 `Agent` 文字的红色三角形缩小为约 0.30 m 的无文字朝向标记。
- 删除不直接服务决策的 `R#`、`C`、object tracker ID；标签仅显示类别名。
- 语义框填充透明度降低，标签使用短引线，避免误把 3D bbox 投影当作实心可行走障碍。
- F1/F2/F3 在两张图中保持相同且不同的候选颜色。
- trajectory 方向箭头默认每 4 个记录点绘制一次，减少长轨迹遮挡。

## 3. Gaussian BEV

- 与 semantic BEV 共享完全相同的裁剪边界、输出尺寸和坐标系；不再使用 title / colorbar 挤占地图面积。
- 每个候选使用与 semantic 图一致的 F 颜色，减少相邻 Gaussian 重叠后难以归属的问题。
- 中心显示简短的 `F# / weight / sigma`；半径表示基于 direct frontier 分数得到的**启发式**不确定性，Prompt 不再称其为校准概率。

## 4. VLM 输入与兼容性

- VLM 内容顺序调整为：semantic BEV → Gaussian BEV → F1/F2/F3 frontier thumbnail → snapshots / crops。
- 更新 Prompt，显式说明浅蓝 unknown、简化对象标签、两图同坐标及 Gaussian 不确定性的启发式性质。
- 下层导航、SCOPE frontier 排分、structured JSON 输出协议与 `subtask_status` 解析均保持兼容。
- 所有实际 VLM 输入仍保存至既有 `vlm_full_inputs` 机制，可追溯源 BEV 路径。

## 5. 验证状态

已在远程 `scope` Python 环境完成：

```text
python -m py_compile src/tsdf_planner.py src/tsdf_export.py \
  src/eval_utils_gpt_goatbench.py run_goatbench_evaluation.py
```

并使用合成 TSDF 运行两种 BEV 导出；semantic 与 Gaussian 输出均为 `960×960`，确认同画布裁剪逻辑可执行。尚未运行完整 GOAT-Bench，因此本分支的成功率变化需要新的对照实验确认。

## 推荐对照实验

1. `main`，TSDF=0.1 m；
2. `baseline/fix-tsdf05cm`，TSDF=0.05 m、旧像素前沿；
3. 本分支，TSDF=0.05 m、物理尺度前沿和可读 BEV。

建议固定 VLM 温度或至少重复多个运行，以避免 `temperature=0.7` 的调用随机性被错误归因给 TSDF 分辨率。
