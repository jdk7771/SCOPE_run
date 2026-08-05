# 时间和 VLM 调用核实

整理日期：2026-08-05

这份文件专门核实运行时间和 VLM 调用时间。之前文档里有一个重要问题：把某些 `vlm_timing.json` 的 split 3 统计拿去解释 split 1，且没有区分“最终完成段”和“中断后续跑累计”。这里重新按日志逐个 split 计算。

## 核实口径

| 口径 | 含义 |
| --- | --- |
| 完成段运行时间 | 日志最后一次从 `00:00:00` 开始并出现 `All scenes finish` 的运行时间。这个口径对应最终生成结果文件的完成段。 |
| log 累计尝试时间 | 同一个 `log_*.log` 里所有时间段相加；如果中途停掉又续跑，前一段也计入。这个口径更接近真实占用机器和 API 的尝试成本。 |
| VLM 成功请求 | 日志末尾 `VLM timing summary` 记录的成功请求数。若续跑时 timing 文件被重置，这个数只覆盖最后完成段。 |
| 全 log HTTP POST | 从整个 log 中统计 `HTTP Request: POST` 行。它会包含中断段、失败/未进入 timing summary 的请求，因此比 `VLM 成功请求` 更接近“实际发出去过多少请求”。 |
| API 响应总时长 | 由日志末尾 `VLM timing summary` 的分类型统计估算，只统计成功请求的 API 响应时间，不包含本地图像处理、导航执行、retry sleep，也不一定包含中断段。 |

## 大实验逐 split 核实

| 方法 | split | 完成段运行时间 | log 累计尝试时间 | 中断/续跑情况 | VLM 成功请求 | 全 log HTTP POST | API 响应总时长 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| baseline/fix | 1 | 14:02:41 | 15:14:15 | 前面有 01:11:34 中断段；续跑时跳过 2 个已完成 scene。 | 3,461 | 3,729 | 06:06:04 |
| baseline/fix | 2 | 13:35:03 | 13:35:03 | 无明显续跑。 | 3,447 | 3,447 | 05:58:36 |
| baseline/fix | 3 | 17:24:40 | 17:24:40 | 无明显续跑。 | 4,422 | 4,422 | 07:39:36 |
| metric readable-BEV | 1 | 20:09:44 | 20:09:44 | 无明显续跑；HTTP POST 比 timing summary 多 11 次。 | 4,925 | 4,936 | 10:38:56 |
| metric readable-BEV | 2 | 20:35:10 | 20:35:10 | 无明显续跑。 | 5,254 | 5,254 | 10:57:27 |
| metric readable-BEV | 3 | 06:29:45 | 28:42:41 | 前面有 22:12:56 中断段；续跑时跳过 27 个已完成 scene。 | 1,599 | 6,678 | 03:45:56 |

## 大实验合计

| 方法 | 完成段合计 | log 累计尝试合计 | VLM 成功请求合计 | 全 log HTTP POST 合计 | API 响应总时长合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline/fix | 45:02:24 | 46:13:58 | 11,330 | 11,598 | 19:44:16 |
| metric readable-BEV | 47:14:39 | 69:27:35 | 11,778 | 16,868 | 25:22:19 |
| 差值，metric - baseline | +02:12:15 | +23:13:37 | +448 | +5,270 | +05:38:03 |

结论要分开说：

- 如果只看最终完成段，readable-BEV 比 baseline/fix 多 02:12:15。
- 如果把中断后续跑也算进去，readable-BEV 比 baseline/fix 多 23:13:37，主要来自 readable-BEV split 3 的 22:12:56 中断段。
- readable-BEV split 3 的 `06:29:45` 不能单独理解成整次 split 3 的真实尝试成本；它只是最后续跑完成段。
- `vlm_timing.json` 对 split 3 可用，但对续跑前中断段不完整；因此 API 响应总时长是基于当前可恢复 timing summary 的下界/完成段统计，不是完整 API 花费。

## 小实验逐项核实

| 方法 | 范围 | 完成段运行时间 | log 累计尝试时间 | VLM 成功请求 | 全 log HTTP POST | API 响应总时长 | 说明 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 当前 baseline/fix split 1 | 大实验正式 baseline 的 split 1 | 14:02:41 | 15:14:15 | 3,461 | 3,729 | 06:06:04 | 有 01:11:34 中断段；不能用 split 3 的 4,422 来代表 split 1。 |
| 旧 baseline_ceping split 1 | 早期 5 cm baseline pilot | 15:39:34 | 15:39:34 | 4,059 | 4,060 | 07:07:25 | 历史参考，不是正式大实验 baseline。 |
| batch reason1 | 第一次 batch 小实验 | 17:21:19 | 17:21:19 | 4,841 | 4,844 | 08:10:19 | batch stage 大量失败。 |
| batch reason2 | 第二次 batch 小实验 | 14:45:41 | 14:45:41 | 3,511 | 3,511 | 06:23:52 | 修复 batch-local frontier ID 后稳定。 |

小实验结论也要修正：

- `batch reason2` 相比当前正式 baseline/fix split 1 的最终完成段，多 43 分钟；相比 baseline/fix 的 log 累计尝试时间，少 28 分 34 秒。
- `batch reason2` 的 VLM 成功请求是 3,511；当前正式 baseline/fix split 1 的 VLM 成功请求是 3,461，不是 4,422。因此不能说 reason2 比正式 baseline/fix split 1 少 911 次成功请求。
- 如果看全 log HTTP POST，reason2 为 3,511，正式 baseline/fix split 1 为 3,729，reason2 少 218 次；但 baseline/fix 的 3,729 包含中断段，所以这个对比不是完全公平的完成段对比。
- reason2 相比 reason1 明显更稳定：VLM 成功请求少 1,330 次，运行时间少 02:35:38，batch 失败 stage 从 1,124 降到 4。
- reason2 相比旧 baseline_ceping pilot 也更省：VLM 成功请求少 548 次，运行时间少 53:53。

## 最终建议的时间写法

大实验汇报建议写：

> 主指标使用最终完成结果计算；时间成本同时报告两个口径。按最终完成段，readable-BEV 三个 split 合计 47:14:39，baseline/fix 为 45:02:24，主方法多 02:12:15。若把同一 log 中中断后续跑的尝试也算入，readable-BEV 为 69:27:35，baseline/fix 为 46:13:58，主方法多 23:13:37，其中主要来自 readable-BEV split 3 的 22:12:56 中断段。

小实验汇报建议写：

> batch reason2 修复局部 frontier ID 后，batch stage 成功率显著提高；但相对当前正式 baseline/fix split 1，成功率/SPL 没有提升，VLM 成功请求数也不是严格更少。它可以作为“batch scoring 可行性和稳定性小实验”保留，不作为主方法。
