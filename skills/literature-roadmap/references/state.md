# 记录格式与辅助脚本

Python 3.9+，标准库即可运行。所有 JSON/Markdown 为 UTF-8。脚本处理输出和同步，不会自动搜索或作学术判断。一个 run 同时只由一个写入者维护。

## 目录

`scope.md`：权威范围约定、检索词及讨论理由。`state.json`：阶段、主题树、范围版本、讨论确认、限制和输出状态。`papers.jsonl`：每行一个文献版本。`queue.jsonl`：每行一个查询/引用追踪任务。`evidence.md`：正文位置与核验记录。`scope-questions.md`：agent 记录的范围取舍问题。导出生成 `pending-fulltext.md`（已纳入但缺全文）、`download-help.md`（确需用户协助的子集）和 `roadmap.xmind`，保留 `roadmap.previous.xmind`。

init 创建新目录，拒绝覆盖。agent 用文件工具维护记录，也可导入 `write_json/write_jsonl` 作原子替换。修改前重读，勿用新建记录覆盖其他字段。

## state.json

```json
{
  "schema_version": 1,
  "run_id": "稳定唯一标识，由 init 生成",
  "title": "研究主题",
  "scope_version": 1,
  "phase": "expansion",
  "gates": {"scope": "用户确认的日期与依据", "seeds": "确认依据", "taxonomy": "确认依据"},
  "coverage": "in_progress",
  "topics": [{"id": "t1", "title": "攻击生成", "parent": null}],
  "relations": [],
  "limitations": [],
  "zotero": {},
  "exports": {}
}
```

phase：scope/seeds/taxonomy/expansion/review。coverage：in_progress/blocked/complete；complete 需 final 讨论确认、无待定候选及无未完成检索队列。阶段成果不要求写 complete。主题 ID 稳定，重命名保留 ID，合并记录迁移。

新调研额外记录 `gates.queries` 的检索词确认；`scope` 保存目标与初始边界，`seeds`、`taxonomy` 可引用同一次种子后讨论，`final` 保存最后统一反馈。旧调研缺 queries 记录时查历史，不能编造确认或强制重问已有答案。自动校验不替代交互节点的执行。

硬性筛选条件记录在 `gates.requirements`；所有确认依据必须可追溯到用户实际回复及其对应方案。提问前增加以下等待字段（无待答问题时为 null 或不存在），然后发出问题并结束本轮：

```json
{
  "awaiting_user": {
    "gate": "queries",
    "scope_version": 1,
    "proposal": "scope.md 中本轮检索词与 Scholar/arXiv 渠道方案的完整内容或稳定快照路径",
    "question": "请确认或修改这组检索词及渠道分工。",
    "asked_at": "实际提问时间"
  }
}
```

恢复时先检查 `awaiting_user`，再检查队列。没有用户回复则保持等待；既不能新增批准记录，也不能运行下一阶段。明确批准后在 `scope.md` 保存方案、用户回复依据、日期和范围版本，更新对应 `gates`，清除等待字段。方案被修改则保留旧记录并重建待确认方案；旧范围的批准不能自动授权新增分支。`phase` 保持当前阶段，不将 waiting 填成新的 phase 值，避免破坏旧数据。

这些字段用于 agent 恢复流程，不是脚本实现的工具调用拦截器。当前 `check` 不核实用户消息、也不阻断直接联网调用；严格的运行时强制需要宿主在等待状态禁用后续调研工具。不要把状态记录或脚本检查成功声称为任意模型都无法越过关口。

relations 示例：`{"from":"p1","to":"p2","kind":"improves","verified":true,"evidence":"出版页URL；§3 p.5；具体改进依据","label":"改进搜索"}`。

## papers.jsonl

```json
{"id":"p1","title":"Exact paper title","short_title":"简称","authors":["作者全名"],"year":2025,"doi":"","url":"https://example.org/paper","decision":"include","reason":"与目标的直接联系","topics":["t1"],"methods":["agent"],"key_paper":true,"summary":"有证据的一句话贡献","publication_status":"preprint","venue":"","ccf":null,"work_family":"w1","reading":"abstract","fulltext":"missing","metadata_verified":false,"evidence":"evidence.md 中的位置及来源URL","zotero":{}}
```

- decision：include/exclude/pending；include 必须有主题，exclude 保留排除理由。pending 不作已确认结论。
- pending 记录 `pending_kind=screening/access_blocked/scope_question/metadata` 与具体原因、下一步；不再将它们全部放进用户导图。缺全文但摘要已确认相关且符合纳入标准的论文用 include，而非 pending。
- `language` 与语言来源、`publication_type`、`ccf_status=listed/not_listed/unverified` 记录筛选依据。`ccf=null` 不等于不在目录。新筛选要求变更后保留原决定及重审原因，不删除用户 Zotero 条目。
- reading：unread/abstract/intro-related-method/deep；fulltext：missing/available。记录附件路径和阅读版本等附加字段，不因下载成功自动升级 reading。
- 只有纳入、已读摘要或正文且仍缺全文的论文可设 `fulltext_help=true`；必须有 `fulltext_attempts` 非空列表，每项含 `source`（URL 或附件/会话来源）、`result`、`date`。未尝试不求助；取得可读全文后移除求助标记。export 生成下载求助清单，并在论文节点标“需用户帮助下载”。
- 有 CCF 等级时同时提供 `ccf_catalog`（目录版本）、`ccf_source`（官方链接）、准确 `venue`。
- `work_family` 关联版本；每行是一个版本。代表版本用 `key_paper`，其他版本折叠并说明关系，避免重复计为独立贡献。
- `metadata_verified=true` 仅在实际核对标题、作者、年份及发表状态后设置。新建 Zotero 前补完整 `zotero_data`：官方 itemType、creators、proceedingsTitle/publicationTitle、date、DOI、url 等。不要猜 itemType 字段。
- 同步助手只对准确 DOI 唯一匹配自动复用。其他近似候选由 agent 核对后设置 `zotero.key`；保留返回的 partition 和版本状态。不删除已有版本。
- `zotero_data` 是新建数据，已有条目不会被它覆盖。`zotero` 下 key、note_key、note_hash、partition、status 由脚本维护。

## queue.jsonl

每项至少有 `id`、`kind`（query/backward/forward/fulltext/verify）、`status`（pending/running/blocked/done/excluded）、`scope_version`、`source`、`next` 和 `reason`。查询记录 query、参数、日期、页 offset、结果来源；引用任务记录 paper_id/citesId。done 必须有实际处理依据；保存下一页再进入下一批。

`check` 校验 ID、主题无环、纳入论文归属、关系证据、CCF 来源以及完成状态的一致性；它无法判断学术证据是否真实，仍需 agent 阅读核实。

## 导出

`export` 从结构化记录生成原生 XMind 8 XML/ZIP；遵循官方 xmind-sdk-python 命名空间、层级、折叠和关系结构，不是 Markdown 改后缀。包含所有纳入文献，允许多主题节点；非关键论文在所属主题的“其他相关工作”折叠分支。待定候选及排除项保留后台，不渲染“待判断”分支；后台 pending 仍触发未完成警告并阻止宣称 coverage=complete，隐藏不等于完成筛选。

仅已核实的改进/派生关系连线，节点链接优先选择已同步 Zotero，否则原文链接。多主题论文的第一主题节点用作关系端点。结构验证通过才替换导图；保留上一有效文件。客户端打开核验另行记录，不能把 ZIP/XML 验证当作视觉兼容验证。
