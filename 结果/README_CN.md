# SCOPE GOAT-Bench 结果

整理日期：2026-08-05

这个文件夹是中文整理入口，只放最重要、最需要复查的大实验结果：

```text
baseline/fix-tsdf05cm
vs
feat/metric-frontier-readable-bev
```

完整归档仍保留在仓库的 `experiment_results/scope_goatbench_results_release_2026-08-05/`。这里新建 `结果/` 的目的，是让人不用先理解英文目录名，也能直接找到大实验结论和对应原始指标文件。

## 目录怎么读

| 路径 | 内容 |
| --- | --- |
| `对比结果.md` | 大实验的中文结论、split 1/2/3 指标、三 split 合并指标。 |
| `大实验指标汇总.csv` | 只包含大实验两组方法的核心指标表，方便直接用表格软件打开。 |
| `大实验指标汇总.json` | 和 CSV 对应的结构化 JSON 版本。 |
| `JSON和PKL结果文件说明.md` | 说明 `json/pkl/yaml/log` 各自保存了什么，怎么读。 |
| `大实验/01_基线_fix-tsdf05cm/` | baseline/fix 5 cm TSDF 对照的说明和原始指标文件。 |
| `大实验/02_可读BEV_metric-frontier-readable-bev/` | readable-BEV 主方法的说明和原始指标文件。 |

## 最重要结论

`feat/metric-frontier-readable-bev` 是当前验证最充分的主实验分支。它和 `baseline/fix-tsdf05cm` 都使用 5 cm TSDF，并且都跑完了 split 1/2/3。

三 split 合并后：

| 指标 | baseline/fix 0.05 m | metric readable-BEV | 提升 |
| --- | ---: | ---: | ---: |
| Snapshot success | 18.27% | 26.91% | +8.64 pp |
| Distance success | 39.88% | 48.02% | +8.14 pp |
| Snapshot SPL | 13.84% | 19.39% | +5.55 pp |
| Distance SPL | 27.86% | 32.49% | +4.63 pp |

一句话：readable-BEV 在三个 episode split 上四项核心指标都高于 5 cm baseline/fix，可以作为当前主结果。

## 这里保留了什么

这里保留的是可复查指标文件：

- `*.pkl`：task 级 success 和 SPL，可重新计算均值。
- `*.json`：snapshot/frame 数量统计、VLM timing。
- `*.yaml`：运行配置。
- `*.log`：运行日志和最终耗时。
- `*.csv`、`*.json` 汇总表：已经整理好的核心结果。

这里没有放原始图片、视频、模型权重或压缩包。
