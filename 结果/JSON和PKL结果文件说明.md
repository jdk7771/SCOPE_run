# JSON 和 PKL 结果文件说明

这个文件说明 `结果/大实验/*/原始结果文件/` 下面的文件各自保存了什么。

## 文件类型

| 文件 | 含义 |
| --- | --- |
| `eval_goatbench.yaml` | 运行配置，记录本次实验使用的参数。 |
| `log_0.00_1.00_1.log` | split 1 的运行日志。 |
| `log_0.00_1.00_2.log` | split 2 的运行日志。 |
| `log_0.00_1.00_3.log` | split 3 的运行日志。 |
| `success_by_snapshot_*.pkl` | 每个 task 是否达到 snapshot success。 |
| `success_by_distance_*.pkl` | 每个 task 是否达到 distance success。 |
| `spl_by_snapshot_*.pkl` | 每个 task 的 snapshot SPL。 |
| `spl_by_distance_*.pkl` | 每个 task 的 distance SPL。 |
| `success_by_task_*.pkl` | 按 `image/object/description` 三类保存 success 列表。 |
| `spl_by_task_*.pkl` | 按 `image/object/description` 三类保存 SPL 列表。 |
| `n_total_snapshots*.json` | 每个 task 的总 snapshot 数。 |
| `n_filtered_snapshots*.json` | 每个 task 过滤后的 snapshot 数。 |
| `n_total_frames*.json` | 每个 task 的 frame 数。 |
| `vlm_timing.json` | VLM 请求耗时和调用统计。 |

## 文件名里的 split

文件名结尾的 `0.0_1.0_1`、`0.0_1.0_2`、`0.0_1.0_3` 分别对应 GOAT-Bench split 1/2/3。

例如：

```text
success_by_distance_0.0_1.0_1.pkl  -> split 1 distance success
success_by_distance_0.0_1.0_2.pkl  -> split 2 distance success
success_by_distance_0.0_1.0_3.pkl  -> split 3 distance success
```

不带 split 后缀的文件，例如 `success_by_distance.pkl`，是该结果目录下多个 split 的合并版本。

## 怎么重新计算一个指标

以 readable-BEV split 1 的 distance success 为例：

```python
import pickle
import numpy as np

path = "结果/大实验/02_可读BEV_metric-frontier-readable-bev/原始结果文件/success_by_distance_0.0_1.0_1.pkl"

with open(path, "rb") as f:
    data = pickle.load(f)

values = list(data.values()) if isinstance(data, dict) else list(data)
score = np.nanmean(values) * 100
print(score)
```

输出应接近：

```text
56.83
```

## 怎么读任务类型拆分

`success_by_task_*.pkl` 和 `spl_by_task_*.pkl` 的结构是：

```python
{
    "image": [...],
    "object": [...],
    "description": [...]
}
```

对每个列表取均值并乘以 100，就得到对应任务类型的百分比。

## 这次没有保留什么

这个中文结果目录只保留可复查指标和日志，没有保留：

- 原始图片。
- VLM 输入图片 bundle。
- 视频。
- 模型权重。
- 压缩包。

如果以后要公开原始图片，建议单独放到 Hugging Face Dataset 或 GitHub Release，不要塞进代码仓库。

