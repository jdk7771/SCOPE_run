# GOAT-Bench val_unseen 全量评测总结

**状态：已完成。** 本次运行覆盖 `data/goat_bench/val_unseen/content/` 中的全部 36 个场景、360 个 lifelong episodes 和 2,669 个导航子任务。完成依据为 `results/exp_eval_goatbench/log_0.00_1.00_all.log` 末尾的 `All scenes finish`。

## 运行方式与断点恢复

执行入口：

```bash
cd /mnt/data/SCOPE
conda activate scope
python run_goatbench_full_evaluation.py -cf cfg/eval_goatbench.yaml
```

全量入口默认选择每个场景的全部 10 个 episode。它扫描已有的 `success_by_snapshot_0.0_1.0_*.pkl` checkpoint，将已完成子任务作为只读恢复索引，而不重复写入旧分片结果。

| Checkpoint 来源 | 已记录子任务数 |
| --- | ---: |
| 旧版单 episode 分片：`split=1..7` | 1,832 |
| 全量入口新增：`all` | 837 |
| 汇总 | 2,669 |

完成的恢复运行在日志中的耗时为 **20:39:38**。该目录的配置副本是 `results/exp_eval_goatbench/eval_goatbench.yaml`，SHA-256 为 `eb6ff6c248a16926f3cd4a4db3104ae5b49a8ffb7831cc60a0049bf4b3b10829`。

> 注意：评测日志没有记录 Git commit。运行结束后工作目录当前为 `fix/stale-snapshot-object-ids` / `c6a2646`，但这不能反推出评测进程启动时的精确 commit；后续运行应在启动日志中记录 `git rev-parse HEAD`。

## 汇总指标

| 指标 | 值 | 样本数 |
| --- | ---: | ---: |
| Success by snapshot | **23.98%** | 2,669 |
| Success by distance | **43.12%** | 2,669 |
| Image-goal success | 36.13% | 822 |
| Object-goal success | 50.96% | 991 |
| Description-goal success | 40.77% | 856 |

### SPL 说明

直接使用现有汇总器时，两个 SPL 均显示为 `nan`，因为 2,669 条记录中有 16 条非有限值。排除这 16 条后，有限值子集的诊断均值为：

| 指标 | 有限样本 | 均值 |
| --- | ---: | ---: |
| SPL by snapshot | 2,653 / 2,669 | 18.67% |
| SPL by distance | 2,653 / 2,669 | 31.14% |

这些有限值均值仅用于诊断；在修复非有限 SPL 的产生原因前，不应把它们当作正式的全量 SPL 报告值。

## 运行统计与输出

| 统计项 | 平均值 |
| --- | ---: |
| VLM prefilter 后 snapshot 数 | 4.62 |
| Snapshot 总数 | 13.63 |
| Frame 总数 | 61.09 |

主要输出位于 `results/exp_eval_goatbench/`：

- 聚合指标：`success_by_*.pkl`、`spl_by_*.pkl`、`*_by_task.pkl`
- 每个 episode 的 `frontier/`、`frontier_video/`、`potential_graph/`、`snapshot/`、`visualization/`
- 完整 VLM 输入记录：`vlm_full_inputs/`

结果目录当前约 **130 GB**；`/mnt/data` 剩余约 **24 GB**（使用率约 96%）。开始新的大规模可视化评测前，应先归档或清理不需要的图片/输入记录，以避免磁盘写满。

## 后续建议

1. 在 SPL 计算前防御零距离、无路径或无效 GT 距离，并在聚合器中显式报告无效样本数。
2. 每次运行开始时写入 Git commit、配置 hash、数据集计数和命令行参数，形成完整可追溯性。
3. 若只关心定量结果，可关闭或单独归档 `save_visualization` 与 `vlm_full_inputs`，显著降低磁盘占用。
