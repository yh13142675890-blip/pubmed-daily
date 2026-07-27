# 项目说明

本项目是 CCM/CM 科研文献监测系统，用于持续检索、筛选、分级并汇总相关 PubMed 文献。

# 固定文献优先级

## S 级

- CM/CCM 与下列任一 QSM 相关表达同时出现时固定为 S 级：QSM、quantitative susceptibility mapping、quantitative susceptibility、magnetic susceptibility、susceptibility mapping、delta QSM、ΔQSM、QSM change、longitudinal QSM。
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
- MAP3K3/MEKK3/KLF2/KLF4/RhoA/ROCK/MAPK
- macrophage/microglia/pericyte/fibroblast
- iron metabolism/hemosiderin/ferroptosis
- glycolysis/mitochondria/metabolic reprogramming
- genomics/epigenomics/spatial omics/bioinformatics
- immune/inflammation/metabolism
- plasma exchange / plasmapheresis / blood exchange / immunoadsorption

## B 级

- natural history
- cohort
- hemorrhage
- epilepsy
- outcome
- surgery
- general clinical imaging
- prospective/retrospective/registry/follow-up/prognosis
- quality of life/patient-reported outcome/PRO/mRS
- radiosurgery/stereotactic radiosurgery
- SWI/DCE/radiomics/machine learning/risk prediction

## C 级

- broad review/background

# 分级约束

- 高优先级规则覆盖低优先级规则，匹配顺序固定为 S、A、B、C。
- CM/CCM + QSM 永远不能被降为 B 级。
- `priority` 必须由确定性 Python 规则生成，禁止让 LLM 决定或修改优先级。

# Daily 持久化范围

- `reports/daily/YYYY-MM-DD.json` 和 `.md` 保存本次运行第一次被系统发现并推送的全部未重复 PMID。
- 来源可以是今日新文献、近期补位、经典补位或顶刊扩展，继续使用 `source_type` 区分来源。
- 是否为本轮首次推送仍由现有 `seen_pmids.json` 和本轮 session 去重流程决定。
