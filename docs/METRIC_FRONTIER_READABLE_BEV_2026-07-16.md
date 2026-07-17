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
- agent 使用小蓝点标位置、细红箭头标朝向，不再用大面积三角形遮挡地图。
- 删除不直接服务决策的 `R#`、`C`、object tracker ID；标签仅显示类别名。
- 标签使用短引线；语义位置在 2026-07-17 的几何一致性修复后不再直接绘制原始 3D bbox 面积。
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

## 同日回归修复

第一次可读性改动后，实际检查发现三项不符合需求的回归，已在同一分支修正：

- inspection semantic BEV 错误地关闭了 context fill，导致物品名称可能全部消失；现在与决策图一致，稳定显示最多 8 个高置信物品类别名；
- VLM 显示层不应把障碍按 0.3 m 膨胀成大块黑色；现在黑色只表示实际障碍 voxel。规划器的碰撞膨胀逻辑未改；
- Gaussian 虽仍作为 VLM Input B 生成，但此前只位于 `potential_graph/vlm_bev/`；现在会把**同一文件**额外复制到 `visualization/bev_gaussian/`，与 semantic BEV 同级保存，便于逐步核查。

## 2026-07-17：语义几何一致性修复

在 `00848-ziup5kvtCCR_ep_0` 的第 1/2 步实际检查中，发现 `bathtub` 等语义框覆盖了绿色可通行区，且橙色历史轨迹直接穿过框。这不是图层顺序问题：轨迹本来就在语义图层之上；它说明 ConceptGraph 合并后的 3D OBB 不能直接充当 TSDF 语义占据区域。原实现还有一个裁剪缺陷：crop 只包含 TSDF、轨迹、agent 和 frontier，未包含对象，导致裁剪外对象的名称被强行夹到图边。

本次修改如下：

- 原始 OBB 只作为**校验假设**，不再直接绘制其俯视多边形；通过校验后，在 OBB 内提取局部 TSDF 障碍支撑、以 0.10 m 轻微膨胀并保留接近追踪中心的连通区域。最终画出的是有形状的紧凑语义区域和类别名称，不是圆点，也不是原始 OBB。
- 丢弃面积超过 `6.0 m²`、最大跨度超过 `4.0 m` 的 OBB；这会过滤报告中的巨大倾斜 `bathtub` 框。
- 锚点必须在 0.40 m 范围内同时接近已观测 TSDF 与实际障碍表面；没有物理支撑的 tracker 假设不输入 VLM。
- 若历史轨迹落在 OBB 内，丢弃该静态对象假设，避免向 VLM 展示“轨迹可穿过实体”的矛盾信息。
- 裁剪范围仅加入通过校验的语义区域中心，因此不会再出现裁剪外对象标签贴在边缘的情况。
- Prompt 同步修改，明确彩色区域由 TSDF 支撑、边界是近似语义 footprint，不是原始 OBB 或精确实例分割；Gaussian BEV、frontier 排分、JSON 决策协议和下层执行逻辑均未改变。

已用最小合成测试验证：带物理支撑的紧凑 `chair` 会保留；面积异常、且包含执行轨迹的 `bathtub` 会被过滤。旧结果图片不会被回写；需重新运行 episode 后生成新的 VLM 输入和 inspection 图。
