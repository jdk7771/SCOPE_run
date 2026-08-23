# SCOPE：A-EQA 与 EXPRESS-Bench 的 baseline vs dedupe+smoothing 总结

整理日期：2026-08-22  
比较对象：5 cm SCOPE baseline vs semantic-BEV dedupe+smoothing  
状态：A-EQA（184 题）与 EXPRESS-Bench（2,044 题）均已完成。

## 1. 数据集与本次运行范围

| Benchmark | 本次数据 | 场景与任务 | 本次规模 |
| --- | --- | --- | ---: |
| A-EQA | `/data1/jiangdakun/datasets/aeqa/aeqa_questions-184.json` | 在 HM3D 场景中主动探索、选择可回答问题的 snapshot，再输出答案 | 184 questions |
| EXPRESS-Bench | `/data1/liuyaxuan/EXPRESS-Bench/EXPRESS-Bench/data/express-bench.json` | 具身空间问答；机器人探索 HM3D 场景后回答物体、属性、状态和空间关系问题 | 2,044 questions |

两者均使用服务器上的 HM3D 场景：`/data1/jiangdakun/hm3d`。A-EQA 本次的 184 题是服务器已安装且完成运行的 evaluation split；EXPRESS 使用 `express-bench.json` 的完整 2,044 题。

## 2. A-EQA：关键结果（184 题）

| 指标 | 5 cm baseline | semantic-BEV dedupe+smoothing | 变化 |
| --- | ---: | ---: | ---: |
| Snapshot/navigation success | 147 / 184 = 79.89% | **154 / 184 = 83.70%** | **+3.80 pp** |
| Fail | 37 / 184 = 20.11% | **30 / 184 = 16.30%** | **-3.80 pp** |
| 成功题平均探索路径 | 5.595 m | **4.098 m** | **-1.497 m（-26.8%）** |
| 成功题路径中位数 | 2.713 m | **2.623 m** | -0.090 m |

同题配对结果：两组均成功 141 题；baseline 独自成功 6 题；dedupe 独自成功 13 题；两组均失败 24 题。即 dedupe 净多完成 7 题。

本组结果说明 semantic-BEV 在 A-EQA 的 snapshot/navigation 过程上有正向效果。不过该 success 是 SCOPE 是否选到 snapshot 并完成导航，**不是统一外部答案评测器给出的最终 QA accuracy**；不能将 +3.80 pp 解释为最终答案准确率提升。

结果目录：

| 方法 | 结果目录 |
| --- | --- |
| baseline | `/data1/jiangdakun/scope_results/aeqa_baseline_5cm_184/` |
| dedupe+smoothing | `/data1/jiangdakun/scope_results/aeqa_semantic_bev_dedupe_smoothing_5cm_184_gpu0_ollama/` |

## 3. EXPRESS-Bench：关键结果（完整 2,044 题）

| 指标 | 5 cm baseline | semantic-BEV dedupe+smoothing | 变化 |
| --- | ---: | ---: | ---: |
| `C`（本地 judge 分级答案信用） | **31.81** | 31.10 | -0.71 |
| `C*`（本地 judge 严格答案正确率） | **34.39%** | 33.51% | -0.88 pp |
| `E_path`（路径效率折扣后的答案信用） | 31.96 | **32.17** | +0.21 |
| `d_T`（结束时距目标平均测地距离） | **5.901 m** | 6.031 m | +0.130 m |
| 选择 snapshot 作答 | 1,319 / 2,044 = 64.53% | **1,321 / 2,044 = 64.63%** | +0.10 pp |
| 平均探索 steps | 6.965 | **5.121** | **-1.844（-26.5%）** |
| 成功作答题平均探索路径 | 6.598 m | **5.034 m** | **-1.564 m（-23.7%）** |
| 完整 wall-clock 运行时间 | 62:22:50 | **48:21:19** | **-14:01:31（-22.5%）** |

按本地 judge 的严格正确性逐题配对：两组都正确 557 题；baseline 独自正确 146 题；dedupe 独自正确 128 题；两组都错误 1,213 题。dedupe 的净正确转换为 `128 - 146 = -18` 题。

EXPRESS 的结论是：semantic-BEV 使 SCOPE 更早结束探索，因而路径更短、`E_path` 和 wall-clock 更好；但当前直接将整张 BEV 注入 VLM 并未提高答案质量，`C` 与 `C*` 均略低。

`C/C*/E_path` 使用同一个本地 `gemma3:27b` judge，适合本次配对内部比较；它**不是** EXPRESS 官方 GPT-4o-mini judge 的 leaderboard 成绩。

结果目录：

| 方法 | 结果目录 |
| --- | --- |
| baseline | `/data1/jiangdakun/scope_results/express_baseline_5cm/` |
| dedupe+smoothing | `/data1/jiangdakun/scope_results/express_semantic_bev_dedupe_smoothing_5cm/` |

## 4. 合并结论

semantic-BEV dedupe+smoothing 没有在两个 benchmark 上给出同方向的结果：

| Benchmark | 主要正向信号 | 主要限制 |
| --- | --- | --- |
| A-EQA | Snapshot/navigation success +3.80 pp；成功题路径 -26.8% | 尚未以统一答案 judge 测最终 QA accuracy |
| EXPRESS-Bench | 平均 steps -26.5%；路径 -23.7%；wall-clock -22.5%；`E_path` +0.21 | `C` -0.71，`C*` -0.88 pp；未提升最终答案质量 |

当前证据支持：该 semantic-BEV 能改变策略并降低探索成本；但“每轮直接添加整张 semantic-BEV 图片”尚不足以稳定提升跨 benchmark 的最终问答正确性。后续若要验证其语义价值，应在独立分支中测试问题相关对象筛选、按需注入 BEV、或将 BEV 用于 frontier/目标打分，而不是仅作为额外图片上下文。

## 5. 详细报告

- `docs/benchmark_evaluations/AEQA_BASELINE_VS_SEMANTIC_BEV_DEDUPE_SMOOTHING_2026-08-20_CN.md`
- `docs/benchmark_evaluations/EXPRESS_BASELINE_VS_SEMANTIC_BEV_DEDUPE_SMOOTHING_2026-08-22_CN.md`
