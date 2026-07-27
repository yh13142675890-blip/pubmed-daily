# 项目定位

本项目是“以 cerebral cavernous malformation（CCM/CM）为核心，同时覆盖相关血管畸形、可迁移机制和跨领域靶向治疗启发的科研文献情报系统”。

系统应主动保留有价值的 venous malformation、brain AVM、其他 vascular malformation 和跨领域血管生物学研究，但必须把疾病领域、转化相关性和阅读优先级分开表达，避免泛关键词制造假阳性。

# 固定分类层次

每篇正式报告文章必须由确定性 Python 规则生成以下三层信息，禁止交给 LLM 判断：

1. `domain`：`CCM`、`Venous malformation`、`Brain AVM / AVM`、`Other vascular malformation`、`Cross-domain vascular biology` 或 `Out-of-scope`。
2. `translational_relevance`：`Direct`、`Strong`、`Moderate`、`Exploratory` 或 `Low`。
3. `priority`：`S`、`A`、`B` 或 `C`，高优先级覆盖低优先级。

单独的 `CCM` 或 `CM` 缩写不是 cerebral cavernous malformation 的强证据。generic `cavernoma/cavernomas` 也不是强 CCM 证据，必须有 brain、cerebral、intracranial、spinal、spinal cord、intramedullary、CNS 等解剖上下文；spinal/spinal cord/intramedullary cavernous malformation 属于 CCM。不得让 corneal confocal microscopy、cirrhotic cardiomyopathy、orbital/portal cavernoma 或 topic 名称触发 CCM domain 或 S 级。

# Priority 规则

## S

- 文章本身有强 CCM 证据并出现 QSM、quantitative susceptibility mapping、quantitative susceptibility、magnetic susceptibility、susceptibility mapping、delta/Δ QSM、QSM change 或 longitudinal QSM。
- 文章本身有强 CCM 证据并涉及 RCT、randomized/clinical trial、phase I/II/III、placebo-controlled、trial readiness、AT CASH EPOC、CARE、REC-994、rapamycin/sirolimus/everolimus trial。

## A

- CCM 核心组学、内皮/屏障、信号、代谢、免疫、铁代谢及细胞机制。
- Venous malformation、AVM 或其他 vascular malformation 与 PIK3CA、TEK/TIE2、PI3K-AKT-mTOR、MAP3K3/MEKK3、KLF2/KLF4、RhoA/ROCK、MAPK、somatic/mosaic mutation、endothelial biology、targeted therapy、sirolimus/rapamycin/everolimus/alpelisib、反馈或耐药机制相结合。
- 药名单独出现不能触发 A；必须与 CCM、相关血管畸形或明确内皮机制结合。
- plasma exchange、plasmapheresis、immunoadsorption、exchange transfusion、red cell exchange、blood exchange 是独立 A 类兴趣方向。
- 独立血浆/换血方向使用 `special_interest = "Plasma exchange / blood exchange"` 表达，不因 domain 为 `Out-of-scope` 而进入低相关展示章节。

免疫概念只精确匹配 immune、immunity、immunology、immunological、immune response/cell、immune-mediated、immunomodulatory、immunosuppressive 等；immunohistochemistry、immunostaining、immunofluorescence 等纯技术词不能单独触发 A。

## B

仅限 CCM 或相关 vascular malformation 的 natural history、prospective/retrospective、cohort、registry、follow-up、hemorrhage/rebleeding、epilepsy/seizure、prognosis/outcome、quality of life/PRO/mRS、surgery/resection、radiosurgery、MRI/SWI/DCE、radiomics、machine learning、risk prediction。CCM + QSM 始终优先为 S。

## C

广泛背景、低转化相关性、方法性但启发有限，以及只有弱机制重叠的跨领域文章。

# 数据与运行约束

- `reports/daily/YYYY-MM-DD.json` 保存当天各次运行第一次发现并推送的全部未重复 PMID；同日重跑必须按 PMID 合并，不能覆盖丢失旧记录。
- 顶刊扩展只能进入独立 topic `跨领域顶刊启发`，`source_type` 为 `顶刊扩展`，并保留原 fallback 名称到 `source_note`；不得继承原检索 topic。
- fallback 候选中已完成内容筛选但被拒绝的 PMID 保存到独立 `screened_out_fallback_pmids`，后续跳过；不得混入 `global_seen_pmids`。
- Cross-domain 必须同时命中机制白名单和明确血管生物学上下文；单独 `vascular`（包括 `vascular invasion`）不足以进入 Cross-domain。
- Daily 与 Weekly 的业务日期和上一完整自然周均使用 `Asia/Shanghai`。
- topic 可配置 `classic_lookback_days`，未配置时使用命令行全局默认值。
- 保持 PubMed E-utilities、SMTP、`seen_pmids.json`、Daily/Weekly JSON/Markdown 和 GitHub Actions 基础架构兼容。
- SMTP 地址和凭据只能来自 GitHub Secrets，不得写入公开代码。
