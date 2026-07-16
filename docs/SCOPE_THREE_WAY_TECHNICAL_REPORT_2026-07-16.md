# SCOPE 三分支技术与实验记录

**日期：** 2026-07-16  
**性质：** GOAT-Bench `val_unseen` 导航评测记录，不是训练（training）记录。  
**结果目录：**

- main 历史基线：`/mnt/data/SCOPE/results/exp_eval_goatbench`
- fix 基线：`/mnt/data/SCOPE/results/baseline_ceping`
- structured-BEV：`/mnt/data/SCOPE/results/_scope_bev_vlm_gussion_ceping`

**保留分支（2026-07-16 整理后）：**

- `main`：原始 10 cm TSDF 历史基线；
- `baseline/fix-tsdf05cm`：原 `fix/stale-snapshot-object-ids`，本次 5 cm TSDF 对照；
- `feat/structured-bev-tsdf05cm`：原 `feat/hsgm-structured-bev-vlm`，结构化 BEV 实验分支。

## 1. 结论摘要

本阶段实现的并不是用 HSGM 点云直接建图，而是在 **SCOPE 原有 TSDF 地图、frontier 评分和低层 TSDFPlanner 执行器** 上，加入 HSGM 风格的结构化 BEV 表达、Gaussian frontier evidence 和结构化 VLM 决策协议。

在 36 场景、每场景 `Episode 0`、共 278 个完全相同子任务的完整配对中：

- structured-BEV 相比同为 5 cm TSDF 的 `fix`，**Distance success +9.35 pp，Distance SPL +8.64 pp**；
- Snapshot success 也从 20.50% 提升到 22.30%，但相对旧 main 的 23.74% 仍低 1.44 pp；
- 因此，这一版的主要收益是“更容易到达目标附近/正确区域”，最终具体对象确认能力尚未超过旧 main；
- structured-BEV 比 `fix` 多耗时 3 小时 35 分，其中约 2 小时 17 分来自额外 VLM 请求，约 1 小时 18 分来自 BEV/Gaussian 生成、图像编码/读写及其他非 VLM 开销；
- `main` 与后两组的主要运行时差异是 TSDF 分辨率从 10 cm 改为 5 cm；5 cm 并非只让地图“更细”，还会显著增加 TSDF、frontier、路径规划和可视化开销。

## 2. 三组实验的范围与可比性

| 结果 | 代码/配置 | 评测范围 | TSDF |
|---|---|---:|---:|
| `exp_eval_goatbench` | main 历史基线 | 全数据集历史累计：10 个 episode、2,669 个子任务 | 0.1 m |
| `baseline_ceping` | `baseline/fix-tsdf05cm` | 36 场景 × Episode 0：278 个子任务 | 0.05 m |
| `_scope_bev_vlm_gussion_ceping` | `feat/structured-bev-tsdf05cm` | 36 场景 × Episode 0：278 个子任务 | 0.05 m |

因此有两种不同口径：

1. **main 的全数据集记录**用于保留历史总体结果；它包含跨多日、多次续跑的 10-episode 累计结果，不能直接与后两组的一次 36-scene/one-episode 运行作未配对的均值比较。
2. **三者共同的 278 个 task key** 才是本报告中 main/fix/structured-BEV 的主对比口径。该集合中的场景、episode 和子任务 ID 完全相同。

## 3. 分支与代码差别

### 3.1 main：原始 SCOPE 基线

- 使用 SCOPE 的 TSDF 地图、scene graph、snapshot、frontier 和 PotentialGraph；
- VLM 输入为问题/目标图、第一视角、筛选后的 snapshot 全图与物体 crop、以及**当前全部 frontier** 缩略图和已有 potential score；
- VLM 输出为兼容旧解析器的自由文本：`Snapshot i, Object j` 或 `Frontier i`；
- 默认 TSDF voxel 为 `0.1 m`；
- main 历史结果未包含本阶段新增的逐请求 VLM timing JSON。

### 3.2 baseline/fix-tsdf05cm：稳定性修复 + VLM 计时

相对 main，核心行为修复在 `src/tsdf_planner.py`：

- snapshot 中的 object ID 可能因后续对象融合/去噪而不再存在于 `scene.objects`；
- main 仍可能访问失效 ID，导致无效导航目标、可视化错误或异常；
- fix 在设置 snapshot 导航目标和可视化时过滤失效 ID；若整个 cluster 都失效，则跳过该 snapshot 目标。

本阶段还新增了 `src/vlm_timing.py`，并在以下请求中记录每一次 `chat.completions.create` 的独立响应时间：

- `decision`
- `frontier_potential`
- `prefilter`
- `self_refine`

计时不包含重试等待、检测、TSDF、图像编码、磁盘写入或导航执行。除 stale-ID 防护外，fix **没有修改**原有 VLM prompt、全部 frontier 候选策略或低层导航逻辑。

> 注意：`fix` 分支的提交配置默认仍是 0.1 m；本次 `baseline_ceping` 运行时为了与 structured-BEV 对齐，保存的 YAML 将 `tsdf_grid_size` 改为了 **0.05 m**。

### 3.3 feat/structured-bev-tsdf05cm：结构化 BEV 决策层

该分支的关键改动位于 `run_goatbench_evaluation.py`、`src/query_vlm_goatbench.py`、`src/eval_utils_gpt_goatbench.py`、`src/tsdf_export.py` 和 `src/potential_graph.py`。

#### A. 地图与候选表达

每次高层 VLM 决策前，仍由 SCOPE 的 TSDFPlanner 更新地图和 frontier；随后新增两张 5 cm BEV：

1. **Semantic BEV（Input A）**
   - 当前 agent 位置和朝向；
   - 历史轨迹；
   - 已观测/可通行/已探索区域和障碍；
   - 由 SCOPE scene object 3D bbox 投影得到的稳定语义实例及文字标签；
   - 按现有 SCOPE potential 排序的 `F1/F2/F3` frontier candidates。

2. **Gaussian frontier-evidence BEV（Input B）**
   - 高斯中心是 candidate frontier/action endpoint；
   - 权重来自已有 PotentialGraph 的预测证据与当前子任务相关信息；
   - 宽度表达预测不确定性；
   - 用于让 VLM 同时参考地图上下文、候选 frontier 和预测证据。

这两张图是 **HSGM-style / structured-BEV 表达**，不是直接调用 `/mnt/data/HSGM_public` 的点云建图。真实建图、A* 路径规划和低层执行仍然是 SCOPE TSDF。

#### B. VLM 输入变化

structured-BEV 保留 snapshot/crop、第一视角和 frontier 缩略图，同时额外加入 Input A 与 Input B，并在 prompt 中说明图例和交叉使用方法。

另外，它不再把所有 frontier 交给高层 VLM：先使用已有 SCOPE PotentialGraph 对 frontier 排序，再仅提供最多 3 个候选 `F1/F2/F3`。低层执行仍使用 SCOPE 的原始 planner。

这意味着 structured-BEV 改变的不是“只多了两张图片”，还包括**高层决策的候选空间从全部 frontier 缩小到 top-3**。这可能降低选择难度，也可能排除排在第四名之后的正确 frontier。

#### C. VLM 输出变化与兼容性

旧格式：

```text
Snapshot i, Object j
或 Frontier i
```

新格式要求严格 JSON，例如：

```json
{
  "selected_candidate": "F1",
  "decision_type": "explore_frontier",
  "subtask_status": "not_completed",
  "reason": "F1 is likely to reveal evidence for the current subtask",
  "confidence": "medium"
}
```

或：

```json
{
  "selected_candidate": "object",
  "decision_type": "go_to_memory_node",
  "snapshot_index": 0,
  "object_index": 2,
  "subtask_status": "not_completed",
  "reason": "The selected crop matches the target evidence",
  "confidence": "high"
}
```

解析器会将 JSON 正规化回 SCOPE 内部原有的 `frontier i` 或 `snapshot i, object j`，因此下层执行接口兼容。

**当前限制：** `subtask_status` 已被要求、校验、记录，但尚未接入下游的“提前结束/跳过子任务”控制逻辑；它目前不是实际改变任务完成状态的开关。

#### D. 可追溯性与过程图片

structured-BEV 会保存：

- `visualization/bev_semantic/`：每步记录用 semantic BEV；
- `potential_graph/gaussian_bev/`：Gaussian evidence 图；
- `potential_graph/vlm_bev/`：决策前生成、真正供 VLM 读取的 BEV；
- `vlm_full_inputs/`：每次 VLM 请求的 manifest、文本顺序和 `content_*.png`。

`visualization/bev_semantic/*.png` 是过程可视化副本；要追溯某次 VLM 实际收到的两张 BEV，应以对应 `vlm_full_inputs/*/manifest.json`、`content_order.md` 和 `content_*.png` 为准。

### 3.4 一个必须说明的分支问题

`feat/structured-bev-tsdf05cm`（原 `feat/hsgm-structured-bev-vlm`）从早于 fix 的共同祖先分出；当前 structured 分支没有包含 fix 的 stale snapshot object-ID 防护，相关 `TSDFPlanner` 代码回到了旧行为。

这不是 structured-BEV 的设计需要，而是分支同步缺失。它可能影响 snapshot 目标导航的稳定性，是后续继续做消融和正式比较前应补回的兼容性修复。

## 4. 结果对比

### 4.1 main 的全数据集历史记录（仅作历史总体参考）

`exp_eval_goatbench` 共 2,669 个子任务。SPL 有 16 个 NaN，因此 SPL 均值在 2,653 个有效值上计算。

| 指标 | main 全数据集 |
|---|---:|
| Snapshot success | 23.98% |
| Snapshot SPL | 18.67% |
| Distance success | 43.12% |
| Distance SPL | 31.14% |

### 4.2 278 个完全相同子任务的配对对比（主结论）

| 指标 | main, 0.1 m | fix, 0.05 m | structured-BEV, 0.05 m |
|---|---:|---:|---:|
| Snapshot success | 23.74%（66/278） | 20.50%（57/278） | 22.30%（62/278） |
| Snapshot SPL | 18.68% | 17.13% | 17.96% |
| Distance success | 45.32%（126/278） | 40.65%（113/278） | 50.00%（139/278） |
| Distance SPL | 33.43% | 29.11% | 37.75% |

structured-BEV 相比 fix（两者同为 0.05 m）：

- Snapshot success：**+1.80 pp**（+5 个成功）；
- Snapshot SPL：**+0.83 pp**；
- Distance success：**+9.35 pp**（+26 个成功）；
- Distance SPL：**+8.64 pp**。

structured-BEV 相比旧 main：

- Snapshot success：**-1.44 pp**（-4 个成功）；
- Snapshot SPL：**-0.72 pp**；
- Distance success：**+4.68 pp**（+13 个成功）；
- Distance SPL：**+4.32 pp**。

### 4.3 结果解释

1. **distance 指标的收益明确。** structured-BEV 相对同分辨率 fix 有较大的 distance success/SPL 提升，说明全局地图、轨迹、语义上下文和 frontier evidence 有助于 agent 到达更可能的目标区域。
2. **snapshot/object 确认仍是短板。** structured-BEV 相对 fix 已有小幅恢复，但仍略低于旧 main。新增全局地图信息可能帮助探索，也可能分散 VLM 对细粒度 object crop 的注意力。
3. **不能将所有变化归因于 BEV。** structured 分支还修改了 top-3 frontier 候选、JSON 协议，并缺少 stale-ID 修复；因此现有结果是“structured-BEV 系统”的结果，而不是单独 semantic BEV 的纯消融结果。
4. **main 与 0.05 m 两组不完全公平。** main 使用 0.1 m，且历史 VLM 运行并非确定性；严格比较 structured-BEV 贡献时，应以 fix 0.05 m 为主要对照。

## 5. 运行时间与 VLM 时间

### 5.1 总运行时间

| 运行 | 范围 | 总时间 | 说明 |
|---|---|---:|---|
| main Episode 0 | 36 场景 | 约 9 小时 29 分 | 根据该历史 Episode 0 输出目录首末时间估计；main 无统一单次 timing 记录 |
| fix 0.05 m | 36 场景 | 15 小时 39 分 34 秒 | `log_0.00_1.00_1.log` 最终值 |
| structured-BEV 0.05 m | 36 场景 | 19 小时 14 分 47 秒 | `log_0.00_1.00_1.log` 最终值 |

main 的完整 10-episode 历史评测跨多次中断和续跑，日历跨度约三周；按结果目录连续时间块估算，累计活动时间约五天。因此它不适合作为单次端到端时间的严格基准。

从 main 0.1 m 到 fix 0.05 m 的显著变慢，主要来自网格分辨率：0.1 m 到 0.05 m 使 2D 网格面积理论上约增 4 倍、3D TSDF 体素数理论上最高约增 8 倍，并带动 TSDF 融合、frontier、路径规划和可视化变慢。

### 5.2 VLM 计时（fix vs structured-BEV）

| 调用类型 | fix：次数 / 均值 | structured：次数 / 均值 |
|---|---:|---:|
| decision | 1,466 / 11.464 s | 2,087 / 11.328 s |
| frontier_potential | 1,051 / 4.651 s | 1,229 / 4.856 s |
| prefilter | 776 / 1.688 s | 1,122 / 2.097 s |
| self_refine | 766 / 3.449 s | 523 / 3.639 s |
| 合计 | 4,059 / 25,646.448 s（约 7:07:26） | 4,961 / 33,865.882 s（约 9:24:26） |

structured-BEV 比 fix：

- 多 902 次 VLM 请求；
- 多约 2 小时 17 分的 VLM API 等待；
- 虽然单次 `decision` 均值略低（11.328 s vs 11.464 s），但 decision 次数增加 621 次，仍是主要增量；
- 总运行时间多 3 小时 35 分，余下约 1 小时 18 分来自 semantic/Gaussian BEV 的渲染、保存、读取、编码、完整输入留档及轨迹差异造成的非 VLM 开销。

## 6. 后续建议

1. 在 structured 分支补回 stale snapshot object-ID 修复，再继续正式比较；
2. 保持 0.05 m 的 fix 作为主要对照，避免把 TSDF 分辨率与 BEV 贡献混在一起；
3. 做最小消融：`fix` → `top-3 frontier only` → `+ semantic BEV` → `+ Gaussian BEV` → `+ JSON protocol`；
4. 若目标是提升 Snapshot success，应减少地图文本/候选信息对 object crop 判断的干扰，或在“已接近候选对象”阶段切换为以 snapshot/crop 为主的确认 prompt；
5. 将 `subtask_status` 真正接入任务完成控制前，不能把它当作已经实现的层级终止机制。

## 7. 复现与审计位置

```bash
# fix 0.05 m 评测（已完成）
cd /mnt/data/SCOPE
git checkout baseline/fix-tsdf05cm
python run_goatbench_evaluation.py -cf cfg/eval_goatbench.yaml

# structured-BEV（对应分支）
git checkout feat/structured-bev-tsdf05cm
python run_goatbench_evaluation.py -cf cfg/eval_goatbench.yaml
```

结果和实际运行配置分别保存在各结果目录内的 `eval_goatbench.yaml`、`log_0.00_1.00_1.log`、`*_by_*.pkl` 和（后两组）`vlm_timing.json`。structured-BEV 的每次 VLM 实际图像输入可在 `vlm_full_inputs/` 中审计。
