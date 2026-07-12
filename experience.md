# SCOPE GOAT-Bench 实验记录与问题分析

日期：2026-06-19
服务器代码路径：`/mnt/data/SCOPE`
结果路径：`/mnt/data/SCOPE/results/exp_eval_goatbench`

## 1. 本次实验命令

本次实验运行命令为：

```bash
python run_goatbench_evaluation.py -cf cfg/eval_goatbench.yaml
```

因为没有显式指定 split 参数，脚本使用默认参数：

```text
--start_ratio 0.0
--end_ratio 1.0
--split 1
```

这意味着：本次实验覆盖了 val-unseen 中全部 36 个场景，但每个场景只跑了第 1 个 episode，最终得到 278 个 subtask 的结果。这不是完整的 GOAT-Bench 评测。

如果要用当前代码跑更完整的 GOAT-Bench，需要至少跑完 10 个 split：

```bash
for split in 1 2 3 4 5 6 7 8 9 10; do
  python run_goatbench_evaluation.py -cf cfg/eval_goatbench.yaml --split ${split}
done
```

代码里的 logger 会自动把 `success_by_snapshot_*.pkl`、`success_by_distance_*.pkl` 等分 split 文件聚合成不带后缀的总结果文件。

## 2. 本次运行配置

结果目录中保存的配置显示：

```text
scene_data_path: /mnt/data/hm3d
test_data_dir: data/goat_bench/val_unseen/content/
choose_every_step: true
egocentric_views: true
prefiltering: true
top_k_categories: 10
use_self_refine: true
yolo_model_name: yolov8x-world.pt
sam_model_name: sam_l.pt
success_distance: 1.0
prompt_h: 360
prompt_w: 360
save_visualization: true
```

服务器代码配置的是本地 Ollama 的 OpenAI-compatible 接口：

```text
END_POINT = "http://localhost:11435/v1"
OPENAI_KEY = "ollama"
model = "qwen3.5:27b"
```

这一点和 SCOPE 论文设置不同。SCOPE 论文默认使用的是：

```text
gpt-4o-2024-11-20
```

## 3. 本次结果

从 `result.md` 和汇总 pkl/json 文件统计得到：

```text
评测 subtask 数量: 278
success_by_snapshot: 11.51%
spl_by_snapshot: 7.64%
success_by_distance: 24.82%
spl_by_distance: 18.85%

image goal SR: 11.36%
object goal SR: 38.38%
description goal SR: 23.08%

平均 filtered snapshots: 0.8633
平均 total snapshots: 9.8453
平均 total frames: 42.6187
```

其中 `success_by_distance` 更接近 GOAT-Bench 官方导航成功定义：agent 是否停在目标物体 1 米以内。`success_by_snapshot` 更严格，反映的是 SCOPE 内部选择的 snapshot/object 是否正确。

这个结果明显低于 SCOPE 论文结果。论文中 GOAT-Bench subset 表格约为：

```text
SCOPE: SR 73.7, SPL 53.5
```

论文附录 full-run 结果约为：

```text
SCOPE: SR 66.8, SPL 46.5
```

不同表格对应的评测设置不完全一样，但本次结果和论文报告值差距非常大。

## 4. 主要失败证据

日志中有大量 VLM 失败：

```text
Raw VLM response: ...                         279 次
Failed to parse response after all retries    197 次
explore_step failed                           233 次
Self-refine rejected choice                    17 次
Self-refine unclear response                    2 次
```

另一个关键异常是 prefiltering 结果：

```text
191 / 278 个 subtask 的 filtered snapshots 数量为 0
```

也就是说，虽然场景里通常已经有 snapshot，但 VLM/prefiltering 阶段经常把候选 snapshot 全部过滤掉。后续 agent 只能继续探索 frontier，或者因为无法得到有效目标而失败。

日志里的典型失败模式：

```text
VLM API call attempt 1...
Raw VLM response: ...
...
Failed to parse response after all retries
explore_step failed and returned None
Subtask invalid: query_vlm_for_response failed
```

所以这次低成功率的主要原因不是 Habitat 或路径规划本身，而是 VLM 决策链路不稳定。

## 5. 为什么本地 qwen3.5:27b 很可能不够

SCOPE 对 VLM 依赖非常强。VLM 在流程中负责：

1. 在 `Snapshot i, Object j` 和 `Frontier i` 之间做选择。
2. 对 snapshot 类别做预过滤。
3. 估计 frontier 的 potential score。
4. 做 self-refinement 验证。
5. 同时理解 egocentric view、frontier image、snapshot image、object crop 等多图输入。

本次使用的本地 `qwen3.5:27b` 至少暴露出三个问题：

1. 经常返回空内容或无效内容，日志里显示为 `Raw VLM response: ...`。
2. 不能稳定遵守代码要求的严格输出格式，例如 `Snapshot i, Object j` 或 `Frontier i`。
3. 对多图、实例级目标匹配能力不足，尤其影响 image goal 和 description goal。

这和 SCOPE 论文中的 VLM 对比结果一致。论文中模型对比显示：

```text
Qwen-Omni-Turbo: SR 17.27, SPL 1.10
Gemini-2.0-Flash: SR 59.35, SPL 43.36
GPT-4o: SR 62.95, SPL 48.34
```

因此，本次结果差基本符合预期：本地 Qwen 27B 作为 SCOPE 的 VLM 后端，很可能达不到论文中 GPT-4o 的能力要求。

## 6. 推荐解决方案

### 最推荐：使用 GPT-4o 复现论文

如果目标是复现 SCOPE 论文结果，优先使用：

```text
gpt-4o-2024-11-20
```

也就是把接口和模型改成 OpenAI GPT-4o：

```text
END_POINT = OpenAI-compatible GPT endpoint
OPENAI_KEY = valid API key
model = "gpt-4o-2024-11-20"
```

这是最接近论文设置、最有可能复现论文结果的方案。

### 次优选择：Gemini 2.0 Flash

如果考虑成本或 API 可用性，可以尝试：

```text
gemini-2.0-flash
```

论文中 Gemini 2.0 Flash 的结果明显好于 Qwen-family VLM，虽然仍低于 GPT-4o。

预期趋势：

```text
Gemini-2.0-Flash 明显优于 Qwen-family VLM
GPT-4o 仍然是最稳妥的复现选择
```

### 如果必须使用本地模型

如果必须坚持本地部署，需要换更强的多模态模型，并且先做小规模 sanity check。可以考虑的方向：

```text
Qwen2.5-VL-72B-Instruct 或更新的大参数 Qwen-VL
InternVL3 / InternVL3.5 大模型版本
LLaVA-OneVision 大模型版本
```

但不要直接跑完整 GOAT-Bench。应该先测试模型是否能稳定输出以下格式之一：

```text
Snapshot i, Object j
Frontier i
```

如果这个格式都不能稳定满足，完整评测大概率仍然会失败并浪费大量时间。

## 7. 后续建议

1. 先把 VLM 后端换成 GPT-4o 或 Gemini 2.0 Flash。
2. 先跑一个小范围实验，不要直接跑全量。
3. 跑完小范围后优先检查日志中的这些指标：

```text
Raw VLM response: ...
Failed to parse response after all retries
explore_step failed
Average number of filtered snapshots
```

4. 如果解析失败仍然很多，需要先改 prompt 或 parser，而不是继续跑完整评测。
5. 小范围结果正常后，再跑 `--split 1` 到 `--split 10`。

## 8. 总结

本次实验流程基本跑通，并产生了完整的 split 1 结果，但结果很差。核心原因不是 GOAT-Bench 命令本身，而是本地 `qwen3.5:27b` 作为 VLM 后端时，无法稳定完成 SCOPE 所需的多图理解、候选过滤、frontier 评估和严格格式输出。

如果目标是复现论文，建议优先换成 GPT-4o。如果 API 成本或可用性有限，可以尝试 Gemini 2.0 Flash。如果必须本地运行，需要换更强的多模态模型，并先做格式输出和多图选择能力测试。

## 9. 2026-07-09 可视化阶段 KeyError 记录

运行 tmux 会话 `scop`（工作目录 `/mnt/data/SCOPE`）时，split 4 在 `00891-cvZr5TUy5C5_3_5` 附近崩溃：

```text
Traceback (most recent call last):
  File "/mnt/data/SCOPE/run_goatbench_evaluation.py", line 732, in <module>
    main(cfg, start_ratio=args.start_ratio, end_ratio=args.end_ratio, split=args.split)
  File "/mnt/data/SCOPE/run_goatbench_evaluation.py", line 513, in main
    return_values = tsdf_planner.agent_step(...)
  File "/mnt/data/SCOPE/src/tsdf_planner.py", line 814, in agent_step
    obj_vox = self.habitat2voxel(objects[obj_id]["bbox"].center)
KeyError: 169
```

原因：VLM 先选择了 snapshot 中的 object `169`（bathtub），随后 `scene.periodic_cleanup_objects()` 做 filtering/merging，`scene.objects` 中该 object id 被删除或合并，但 `self.max_point.cluster` 仍保留旧 id。之后 `agent_step()` 在保存 BEV/top-down 可视化时继续访问 `objects[169]`，导致 `KeyError`。

影响范围：这是 `save_visualization=True` 时的绘图崩溃，不是 VLM 决策、导航目标计算或最终评测逻辑本身报错。

处理：在 `src/tsdf_planner.py` 的可视化绘制循环中加入 guard：如果 snapshot/max_point 的 `obj_id` 已经不在 `objects` 中，则跳过该点的绘制。这样只会少画已被 cleanup 删除的 object marker，不改变导航、VLM 输入、potential score 或成功率计算。

