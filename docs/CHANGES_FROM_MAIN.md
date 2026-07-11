# 本分支相对 `main` 的改动说明

分支：`feat/semantic-bev-comparison`。

本文只记录相对 `main` 的功能性改动；不包含工作区中用户自行修改但尚未提交的文件。

## 1. 保留原始输出，并新增对照 BEV

- 原本的 top-down 图仍会在每个导航决策步保存，但移动到
  `visualization/bev_before/`，用于和原始 SCOPE 行为逐帧对比。
- 新增 `visualization/bev_semantic/`。它不参与导航决策，仅保存更易检查的
  TSDF BEV：地图状态、3D 物体实例与轨迹。
- 原有 `frontier/`、`frontier_video/`、`snapshot/`、`potential_graph/` 输出均保留。

## 2. 语义 BEV

新增 `src/tsdf_export.py`，以与 `TSDFPlanner.agent_step()` 一致的高度切片和坐标
约定生成 BEV：灰色为可通行但未探索区域、绿色为已探索可通行区域、黑色为障碍。

- 轨迹为橙色，带方向箭头；起点标为 `S`，当前位置为红点。
- 物体来自 ConceptGraph 的 3D bounding box，投影到地面 footprint。
- 仅考虑检测次数达到 `tsdf_bev_min_object_detections` 的实例。
- 不通过缩小渲染像素伪造几何细节；当前渲染分辨率与真实 TSDF 体素大小相同。

### 任务相关物体标注

原始 VLM 预筛会为当前任务返回按相关性排序的类别列表。
本分支将该列表带到 BEV 渲染：

- `tsdf_bev_max_labeled_instances: 10`：优先填色并标注任务相关类别的实例，再按
  检测稳定性补足其他实例；若稳定实例少于 N，则显示全部稳定实例。
- `tsdf_bev_show_irrelevant_object_outlines: false`：默认不显示其他实例。设为
  `true` 时，它们只画无标签的细灰轮廓，供审计使用。
- 这些选项只改变保存图，不改变 VLM 输入、前沿评分或导航动作。

## 3. 前沿未来证据高斯图

新增 `potential_graph/gaussian_bev/<step>_<subtask>_gaussian_bev.png`。
每个 frontier 的中心是其可执行端点：

- 强度：`potential_score`、`semantic_richness`、`explorability` 的加权证据，再乘
  `goal_relevance`；
- 宽度：由低证据和四项评分分歧构造的启发式不确定性（不是模型直接给出的概率方差）；
- 弱于全图峰值 3% 的高斯值透明，露出原始灰/绿/黑地图状态；
- 色条仅说明非透明的未来证据层。

为生成该图，`PotentialGraph` 额外缓存每个 frontier 的直接 VLM 评分；缓存仅用于
保存与恢复及可视化，不取代原本的 potential graph 更新与 VLM 最终选择。

## 4. 配置与行为边界

本分支在 `cfg/eval_goatbench.yaml` 新增/使用以下 BEV 选项：

```yaml
tsdf_grid_size: 0.1
tsdf_bev_render_resolution: 0.1
tsdf_bev_min_object_detections: 2
tsdf_bev_trajectory_arrow_stride: 1
tsdf_bev_max_labeled_instances: 10
tsdf_bev_show_irrelevant_object_outlines: false
```

除已有的 potential graph 评分机制外，本分支没有修改传感器输入、RGB-D 到 TSDF 的融合、
路径规划、frontier 生成或最终 VLM 选择策略；新增内容是诊断输出和其所需的评分缓存。
