# 项目说明

本项目是 CCM/CM 科研文献监测系统，用于持续检索、筛选、分级并汇总相关 PubMed 文献。

# 固定文献优先级

## S 级

- CM/CCM + QSM 固定为 S 级。
- CM RCT、clinical trial 或 trial readiness 固定为 S 级。

## A 级

- single-cell
- spatial transcriptomics
- RNA-seq
- proteomics
- metabolomics
- multi-omics
- CCM基础机制
- mTOR/PI3K-AKT
- HIF1A/HIF-1α
- EPAS1/HIF-2α
- immune/inflammation/metabolism
- plasma exchange / plasmapheresis / blood exchange

## B 级

- natural history
- cohort
- hemorrhage
- epilepsy
- outcome
- surgery
- general clinical imaging

## C 级

- broad review/background

# 分级约束

- 高优先级规则覆盖低优先级规则，匹配顺序固定为 S、A、B、C。
- CM/CCM + QSM 永远不能被降为 B 级。
- `priority` 必须由确定性 Python 规则生成，禁止让 LLM 决定或修改优先级。
