# 小实验

这个目录用于保存过程性小实验。它们不是主结果，但可以保留实验目的、指标和原始 `json/pkl/yaml/log`，方便以后继续补充。

## 当前条目

| 小实验 | 对应分支 | 主要文档 | 做什么 | 结论 |
| --- | --- | --- | --- | --- |
| `小实验_batch输入新frontier评分/` | `feat/batch-frontier-potential-scoring` | `实验说明.md`、`对比结果.md` | 把新 frontier 的 potential scoring 从逐个 VLM 请求改成 batch 请求。 | batch-local frontier ID 修复后流程稳定一些，相比 reason1 和旧 pilot 请求数下降；但相对正式 baseline/fix 导航成功率没有提升，不作为主方法。 |
