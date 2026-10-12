# 工具连接、核验与降级

## Google Scholar / HasData

运行时发现现有 Scholar MCP；使用其凭据连接，不向用户重复索取已配置密钥，不把密钥写入文件。普通搜索 q；按返回下一页设置 start 并保留原参数。记录 Scholar 的原始查询 URL、分页和筛选结果。

2026-10-12 的连接实测：工具 `hasdata_google_scholar_scholar_getScholarSearchResults` 要求 q 非空。被引模式可使用 `q=" "`（一个空格）和 `cites=<citesId>`；空字符串被拒绝，非空关键词可能限定结果。DESERIGUARD 的 citesId `9213549430869730134` 返回包括 Gleipner 的被引列表，下一页保留 cites；作者公开全文参考文献 [59] 核实该引用。此为模式探测样例，不硬编码调研对象。

每次连接首次使用引用模式都检查 requestMetadata.url 和 pagination.next 是否保留 cites，抽样核对正文参考文献。HTTP 200 或给出列表不等于正确。若工具行为变化，任务标 blocked；可用 Scholar 浏览器页面继续同一主渠道，或说明障碍后讨论替代源，不能悄悄把普通搜索当作被引列表。cluster/versions 同样核验。

官方说明：https://docs.hasdata.com/apis/google-scholar/scholar

## arXiv API（补充渠道）

先确认检索方案，再调用。用途：按主题补充近期预印本、取得真实摘要和版本元数据、为缺全文论文寻找开放版本。它不是 cited-by 服务，不能替代 Scholar 向前引用队列。Scholar 受阻时，只能继续已获确认的 arXiv 补充任务，并保留 Scholar 的 blocked 状态；未确认检索词时，两边都不能先试搜。

官方公开 Atom 查询接口 `https://export.arxiv.org/api/query` 不需要 API key。使用现有 HTTP/MCP 工具或标准库请求即可，随附脚本不包含 arXiv 客户端。把用户审核过的概念转换为 `ti:` / `abs:` 等字段及 AND/OR 查询；转换语法不改变研究范围，新增概念则回到范围确认流程。通过 `search_query` 或已知 `id_list` 检索，`start` / `max_results` 分页；保存完整请求参数、日期、原始响应和下一页位置，不把每页大小当总量上限。

读取 Atom 的 title、summary（真实摘要）、authors、published、updated、版本 ID、PDF 链接，以及可选 DOI、journal_ref。published 是首版日期，updated 是版本更新日期；近期更新不等于近期首次公开。作者提供的 journal_ref/DOI 需要核对正式出版页与 CCF，不能把 arXiv 条目直接称为 CCF 论文，也不能用预印本版本规避已确认的正式发表筛选条件。按基础 arXiv ID / DOI 与现有记录关联版本，不能另算一篇独立研究。

按官方当前要求，所有同源调用合计最多每三秒一次、单连接；缓存响应，遇 429/服务错误保存进度并退避，不能把错误 Atom entry 当成论文或零结果。需要 PDF 时使用返回链接并核验内容；摘要足以判断相关性时可以先归类，正文未读必须如实标注。

官方参考（使用前如有变化按官方更新）：
- [API 手册](https://info.arxiv.org/help/api/user-manual.html)
- [调用限制](https://info.arxiv.org/help/api/tou.html)

## 全文

顺序：Zotero 附件 → OA 正式版 → 预印本/作者稿 → 已授权机构会话。记录版本、文件类型和可读性，拒绝把登录 HTML 当论文。正文提取保留页码/章节，用原 PDF 检查关键表格与公式。

IEEE：可导航学校选择入口；用户在学校 SSO 页面自行输入密码及 MFA。只复用已建立会话，不把凭据录入状态或日志。取不到全文保留条目、列入待补清单并继续其他论文。用户补全文后恢复该条目的阅读与引用扩展。

## Zotero

优先现有具备写入能力且已授权的 MCP/API。当前仅检索/元数据/全文三个 MCP 工具时，不能声称写库成功。可使用随附 `zotero_sync.py` 的官方 Local/Web API 路径；绝不编辑 Zotero SQLite。

先 `probe`。Local API 需要客户端开启“允许本机其他应用与 Zotero 通信”；本地写入需 Zotero 10+ 的 Server-ID 与运行时授权。`sync <run> --authorize-local` 必要时弹 Zotero 授权对话框，返回 key 仅留内存；单次授权可能只允许一次写入，401 后停止本次批次，避免反复弹窗。用户可自行选择“Always Allow”。已配置凭据也可通过 `ZOTERO_LOCAL_API_KEY` 环境变量传入。

Web API：`--mode web --library users/<实际数字ID>` 或 groups/<ID>，读取 `ZOTERO_API_KEY` 环境变量。凭据需目标库写权限；不要在命令中写值或输出环境变量。先核对目标库身份。Local/Web 版本号不同，不能混用；partition 改变必须重新解析已有条目/收藏夹，不能直接重复创建。

同步过程：为本次 run 建总收藏夹及主题子收藏夹 → 复用准确匹配或经 agent 核对的条目 → 更新受管理集合关联 → 创建独立受管理短笔记 → 逐项读回。脚本在创建前持久化随机 key，失败后先按 key 查询，减少超时重复写入；记录本次调研实际新增的集合关联，论文重新分类时只移除其中已过时的关联，原有集合/字段/标签/笔记不改。受管理笔记发生外部编辑则保留并报冲突。主题重命名/移动如遇已建收藏夹不符，先核对用户改动再更新映射，脚本不擅自覆盖。

本地脚本管理元数据、集合及短笔记；PDF 附件优先已有连接上传能力，否则按官方附件流程另行处理，状态单列，不能把元数据成功当作 PDF 已归档。缺权限继续本地研究和导图，Zotero 保持 pending；RIS/BibTeX 不能代替自动同步成功。

正式 API 参考：
- https://www.zotero.org/support/dev/web_api/v3/local_api
- https://www.zotero.org/support/dev/web_api/v3/write_requests
- https://www.zotero.org/support/dev/web_api/v3/file_upload

## XMind

随附 exporter 无外部依赖，按官方 SDK 原生 XML 结构写 ZIP：
- https://github.com/xmindltd/xmind-sdk-python
- https://github.com/xmindltd/xmind-sdk-python/blob/master/xmind/core/const.py
- https://github.com/xmindltd/xmind-sdk-python/blob/master/xmind/core/topic.py

导出后结构校验只是第一步；可用客户端时打开，查看中文标题、多层主题、折叠分支、链接及关键关系。没有可操作客户端则明确“结构校验通过，客户端兼容性待验证”。无需常驻预览服务。
