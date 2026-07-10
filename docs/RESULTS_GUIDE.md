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

## Frontier 评分高斯图

完成当前 step 的 frontier 评分后，系统还会保存：

```text
potential_graph/gaussian_bev/<global_step>_<subtask_id>_gaussian_bev.png
```

它以同一张 SCOPE BEV 为底图，并只在可通行区域叠加候选 frontier 的高斯场：

- 白色圆点 `F<i>`：候选 frontier/action endpoint。
- 高斯强度 `w`：由预测的未来证据潜力（overall potential、semantic richness、explorability）与当前子任务 goal relevance 相乘得到。
- 高斯宽度 `σ`：当前 VLM 没有提供校准的不确定性，因此采用显式代理；预测证据越低、各诊断项分歧越大，`σ` 越宽。
- 颜色越亮：该位置附近累积的加权未来证据越高。

这张图用于解释评分分布，不会参与或替代当前的 VLM 选择策略。

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

这是从同一 TSDF 状态生成的语义对照图：

- 地图底色与 `bev_before` 使用同一套切片和颜色：白色为未知/不可通行，灰色为已见但未探索的可通行区，浅绿色为已探索可通行区，黑色为约 1.8 m 高度处的障碍。
- 彩色覆盖区域：ConceptGraph 中物体 3D oriented bounding box 投到地面的 footprint。
- `实例 ID: 类别名`：例如 `12: chair`。默认只画至少被观测到 2 次的实例，减少单帧误检带来的标签噪声。
- 橙色线和箭头：本 subtask 的实际执行轨迹与每一段移动方向。
- 蓝点 `START`：本 subtask 起点；红点：当前/最后位置。

该图不画 snapshot 扇形，避免遮住几何和对象标签。

## 分辨率：渲染分辨率与真实体素分辨率

当前默认配置为：

```yaml
tsdf_grid_size: 0.1
tsdf_bev_render_resolution: 0.1
```

这表示：

- TSDF 的真实三维体素为 **10 cm**；地图融合、frontier、导航和两种 BEV 的底图都使用这一分辨率。
- `bev_semantic` 的价值是实例 footprint、类别标签和轨迹箭头，而不是更高的几何分辨率。
- 将 `tsdf_bev_render_resolution` 设为 2.5 cm 只会把每个 10 cm 栅格放大为 4×4 个相同像素，不会创造新的深度几何细节，因此默认保持 10 cm。

## 如果缩小真实 TSDF 体素

当前 SCOPE 是全局稠密 3D 体素实现。体素数量与体素边长的三次方成反比：

| 真实 TSDF 体素 | 相对 10 cm 的体素数 | 对 TSDF 内存与每帧投影更新的预估 |
| --- | ---: | --- |
| `10 cm` (`0.1 m`) | `1x` | 当前默认 |
| `5 cm` (`0.05 m`) | `8x` | 约 8 倍；通常仍可尝试，但会明显变慢 |
| `2.5 cm` (`0.025 m`) | `64x` | 约 64 倍；大场景很可能内存不足或更新过慢 |
| `0.25 cm` (`0.0025 m`) | `64,000x` | 当前实现不可行 |

SCOPE 除了 TSDF 本身，还为所有体素保存权重、探索状态、体素坐标和预计算相机点；每次 RGB-D 融合都会投影整张体素体。因此上表是保守估计：临时数组、内存带宽和缓存失效会使实际情况更差。

完整评测还会包含检测、分割和 VLM 调用；这些组件可能掩盖一部分总墙钟时间，但 TSDF 融合部分仍近似按上表变慢。建议保持 10 cm TSDF；若需要真正的高分辨率几何，应改用局部稠密窗口、稀疏哈希体素或 HSGM 的点云式地图。
