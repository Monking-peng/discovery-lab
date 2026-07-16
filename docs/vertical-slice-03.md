# 纵向切片 03：Hybrid Retrieval 与 Context Manifest

## 演示目标

用户输入检索问题后，系统只从当前、人工 `ACCEPT`、非合成且可确定性回放的 Evidence Revision 中取回候选，并把查询、算法版本、精确 Evidence/Source/Review Revision、分数和上下文链接冻结成不可变 `Context Manifest`。

```text
untrusted query
→ formal Evidence eligibility gate
→ BM25 + feature-hash cosine
→ weighted reciprocal-rank fusion
→ relevance floor
→ immutable Context Manifest
→ exact Evidence Revision replay
```

## 为什么不是“搜索框套列表过滤”

- PostgreSQL 使用 `vector(256)` 投影与 HNSW cosine index；SQLite 仅在自动化测试中使用同一确定性向量的 Python fallback。
- BM25 与 vector 分别排名，再用带权 RRF 融合；没有词项命中且 cosine 低于阈值的候选会 fail closed，不会因为“总要凑够 top-k”进入上下文。
- 本地向量是可离线复现的 feature hashing，不冒充训练得到的语义 embedding；API 与 UI 都显式返回该说明。
- 搜索投影是可重建缓存，不是业务事实源。Evidence Review、revision 和来源链仍以主表为准。

## Eligibility Gate

候选必须同时满足：

1. 是 Evidence Unit 的当前 Revision；
2. 最新 Evidence Review 为人工 `ACCEPT`；
3. 不是 `synthetic_demo` 或 `simulation_output`；
4. typed Locator 能解析并在 Segment 内精确切出 Quote；
5. Segment、Source、Quote 与 Evidence content hash 全部匹配；
6. Evidence、Source 与 Study 的关系一致。

旧 revision 仍可通过已有 Manifest 或 Claim edge 回放，但不会进入新的检索结果。

## Context Manifest 契约

Manifest 是 append-only 记录，包含：

- 原始查询与声明用途：support、counterevidence 或 explore；
- retrieval profile、BM25、vector 与 fusion 算法版本；
- 每个结果的 exact Evidence Revision、Source Revision 与 Evidence Review ID；
- Evidence/Source content hash、冻结的 quote/analysis/review snapshot；
- lexical、vector、hybrid score 及各自排名；
- 绑定 exact revision 的 context URL；
- request/content hash 与幂等键。

后续 Review 变化会影响新的检索，但不会改写历史 Manifest。因此可以复现“当时模型实际看到了什么”，而不是事后用最新资料重构一个近似上下文。

## 安全边界

查询与资料都被当作不受信任的数据。它们只进入参数绑定、tokenization 和确定性数值计算，不能改变工具、SQL、Prompt 或发布状态。Golden/API tests 使用 `DROP TABLE`、角色覆盖和工具调用文本验证该边界。

## 运行与验收

```powershell
.\scripts\dev.ps1 restart -ApiPort 8010 -WebPort 3010
.\scripts\seed-helphub.ps1
```

然后在 Evidence Explorer 的 Hybrid Retrieval Lab 中检索 `enterprise outage escalation SLA`。验收结果应包含：

- 返回当前六条人工 Evidence 中的相关项；
- 展示三类分数、算法名和不受信任查询边界；
- 点击结果按 exact revision 回放原始 CSV 行；
- 重复同一幂等请求返回同一 Manifest；
- 无关查询产生可审计的空 Manifest。
