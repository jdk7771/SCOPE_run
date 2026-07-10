# SCOPE 结果目录与 BEV 对照说明

一次 GOAT-Bench episode 的结果目录形如：

```text
results/exp_eval_goatbench/<scene_id>_ep_<episode_id>/
```

例如，`00800-TEEsavR23oF_ep_0` 表示场景 `00800-TEEsavR23oF` 的第 `0` 个评测 episode。

## 顶层目录

下面五类原有输出都会保留：

| 目录 | 内容 | 文件名中的步号 |
| --- | --- | --- |
| `snapshot/` | 每个候选观察方向的 RGB 或检测标注图 | `<global_step>-view_<view_id>.png` |
| `frontier/` | 面向每个 frontier 采集的视图 | `<step>_<frontier_id>.png` |
| `frontier_video/` | 将候选 frontier/snapshot 组成的决策拼图 | `<global_step>_<subtask_id>.png` |
| `potential_graph/` | potential graph、最终图和状态 | `potential_*`、`final_potential_*`、`potential_state_*` |
| `visualization/` | 每次导航决策后的两种 BEV 对照图 | 见下一节 |

`global_step` 是全 episode 的导航决策序号；`subtask_id` 是当前 GOAT-Bench 子任务编号。一次决策可以融合多个 RGB-D 观察，因此一张 BEV 不等于一张相机帧。

## 两种 BEV 对照

`visualization/` 内保存相同步号、同一子任务的一对图：

```text
visualization/
├── bev_before/
│   └── <global_step>_<subtask_id>.png
└── bev_semantic/
    └── <global_step>_<subtask_id>_bev.png
```

### `bev_before/`：原 SCOPE 规划 BEV

这是原有的 SCOPE top-down planner visualization，保留 snapshot 扇形、frontier 箭头、目标点和规划相关信息。

- 半透明小扇形：一个 `SnapShot` 的观测区域；圆心是拍摄位置，扇形覆盖该 snapshot 关联对象的方位，半径到最远关联对象。
- 紫色箭头/点：frontier 及其探索朝向。
- 红色边框：当前被选中的 frontier 或 snapshot。
- 白色轨迹：该 subtask 已执行的路径。
- 颜色块：来自 SCOPE 固定高度切片的 free、explored、obstacle 等规划状态。

它更适合理解 SCOPE 为什么选择某个 frontier，而不是用于精细查看家具轮廓。

### `bev_semantic/`：增强后的语义 BEV

这是从同一 TSDF 状态生成的清晰对照图：

- 地图底色：TSDF 的 observed/explored/free/obstacle 状态；它与 SCOPE 的规划地图使用同一底层状态。
- 彩色覆盖区域：ConceptGraph 中物体 3D oriented bounding box 投到地面的 footprint。
- `实例 ID: 类别名`：例如 `12: chair`。默认只画至少被观测到 2 次的实例，减少单帧误检带来的标签噪声。
- 橙色线和箭头：本 subtask 的实际执行轨迹与每一段移动方向。
- 蓝点 `START`：本 subtask 起点；红点：当前/最后位置。

该图不画 snapshot 扇形，避免遮住几何和对象标签。

## 分辨率：渲染分辨率与真实体素分辨率

当前默认配置为：

```yaml
tsdf_grid_size: 0.1
tsdf_bev_render_resolution: 0.025
```

这表示：

- TSDF 的真实三维体素仍为 **10 cm**；地图融合、frontier 和导航逻辑仍使用这一分辨率。
- `bev_semantic` 将二维图以 **2.5 cm/像素**渲染，以便清楚显示对象 footprint、标签和轨迹。
- 2.5 cm 渲染不会创造新的深度几何细节；它只提高输出图像和覆盖物的显示精度。

## 如果缩小真实 TSDF 体素

当前 SCOPE 是全局稠密 3D 体素实现。体素数量与体素边长的三次方成反比：

| 真实 TSDF 体素 | 相对 10 cm 的体素数 | 对 TSDF 内存与每帧投影更新的预估 |
| --- | ---: | --- |
| `10 cm` (`0.1 m`) | `1x` | 当前默认 |
| `5 cm` (`0.05 m`) | `8x` | 约 8 倍；通常仍可尝试，但会明显变慢 |
| `2.5 cm` (`0.025 m`) | `64x` | 约 64 倍；大场景很可能内存不足或更新过慢 |
| `0.25 cm` (`0.0025 m`) | `64,000x` | 当前实现不可行 |

SCOPE 除了 TSDF 本身，还为所有体素保存权重、探索状态、体素坐标和预计算相机点；每次 RGB-D 融合都会投影整张体素体。因此上表是保守估计：临时数组、内存带宽和缓存失效会使实际情况更差。

完整评测还会包含检测、分割和 VLM 调用；这些组件可能掩盖一部分总墙钟时间，但 TSDF 融合部分仍近似按上表变慢。建议保持 10 cm TSDF + 2.5 cm BEV 渲染；若需要真正的高分辨率几何，应改用局部稠密窗口、稀疏哈希体素或 HSGM 的点云式地图。
