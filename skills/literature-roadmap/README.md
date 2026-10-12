# Literature Roadmap：启动与使用

先交流研究目标和检索词，种子初筛后确认主题范围，再自主扩展引用；最后交付 Zotero、XMind，以及范围取舍和下载求助清单。无需先写一份完整需求文档，可以给方向、种子论文或已有资料目录。

## 启动需要什么

| 项目 | 配置方式 | 是否必需 |
| --- | --- | --- |
| Google Scholar / HasData | 已授权的 HasData Scholar MCP，或运行时提供 `HASDATA_API_KEY` | Scholar 检索需要；已有有效连接无需再提供 key |
| arXiv API | 公开 Atom 查询接口，无需 API key | 可选；补充预印本、摘要与开放全文，不替代 Scholar 被引检索 |
| Zotero | 可写 MCP；或 Web API 的 `ZOTERO_API_KEY`，以及 `users/<数字用户ID>` / `groups/<组ID>` | 自动入库需要写权限和目标库 |
| Zotero Local API | 启动客户端、开启本机 API；可选 `ZOTERO_LOCAL_API_KEY` 或客户端授权 | 本地方案的替代配置，只有可读 API 不足以写入 |
| Python | Python 3.9+，随附脚本使用标准库 | 本地校验、导图导出及 API 同步需要 |
| XMind | 可以打开 `.xmind` 的客户端 | 导出不需要 key；客户端用于打开和查看 |
| 机构访问 | 已登录的图书馆/出版平台会话 | 可选；学校 SSO 密码、MFA 由用户自行输入 |

不要把真实 key 写入 README、skill、调研目录或聊天输出。优先配置 MCP 的凭据管理；直接 API 备用路径从进程环境读取凭据。`HASDATA_API_KEY` 是 agent 备用调用的环境变量约定，随附脚本不包含 Scholar 搜索客户端，也不会自动配置 MCP。更换凭据时更新运行环境即可，不修改论文状态。

HasData 备用接口为 `https://api.hasdata.com/scrape/google/scholar`，通过 `x-api-key` 请求头传入运行时凭据。用已确认的一个查询检查连接，保留响应状态、查询参数和结果数，不保存认证头。引用模式额外核验返回 URL 中的 `cites`。接口细节见 [工具适配](references/integrations.md)。

Zotero API key 可在 [Zotero Keys](https://www.zotero.org/settings/keys) 管理，确保目标库访问与写入权限。下例在已安全配置环境变量后运行，`<skill>`、`<run>`、数字 ID 需要替换成实际值：

```text
python <skill>/scripts/zotero_sync.py probe --mode web --library users/<数字ID>
python <skill>/scripts/zotero_sync.py sync <run> --mode web --library users/<数字ID>
python <skill>/scripts/roadmap.py check <run>
python <skill>/scripts/roadmap.py export <run>
```

`probe` 仅确认可读性，不证明写入成功；真实同步须逐项读回。已有同一调研的同步状态应复用，切换库或 Local/Web 模式前核对身份，避免重复创建。

## 如何开始

可以说：“用 literature-roadmap 调研 Java 反序列化防御，材料在这个目录。先和我讨论检索词，再找种子并确定细分 scope。”继续时提供原调研目录即可，不需要重新回答已确认的问题。

默认只收英文；优先 CCF A/B/C 与近两年预印本，排除已核实不在 CCF 的期刊论文，预印本豁免。非 CCF 会议另按范围约定。不同项目可在启动讨论时修改这些筛选条件。没有固定篇数上限，通过相关性控制范围。

## 交付和需要你参与的地方

- 启动时：确认语言、发表门槛、时间等硬性条件。
- 读材料后：逐步讨论并确认研究目标与 scope。
- 检索前：审核检索词、组合及 Scholar/arXiv 的渠道分工。
- 种子后：决定主方向、核心细分主题与对照范围。
- 汇报时：决定有争议的 scope 是否继续，协助获取确实受阻的全文。

每个确认问题发出后，智能体必须结束当前轮次，收到明确回答后才能继续。异步问题未回答、默认选项或超时均不代表同意；不会边问边检索。已有明确确认可继承，不要求重复回答。你可以修改方案，或明确说“按此修改并继续”。

arXiv 补充检索也受这些节点约束。它提供预印本发现、摘要和版本信息；向前被引仍走 Google Scholar。队列任务完成后保留 done 记录，仅从活动队列移出；下载/引用受阻保留 blocked，不以“活动队列为空”冒充全部完成。

此 skill 通过指令和持久化等待状态约束执行，不是运行时权限系统。更换模型或宿主后应复测是否真正停轮；若模型仍越过关口，宿主需要在等待确认时禁用调研工具。现有 Python 测试只验证脚本功能，不能证明 zcodeglm 等模型遵守交互流程。

`roadmap.xmind` 展示确认纳入的论文；已读摘要且相关但全文受阻的条目标“需用户帮助下载”。`download-help.md` 给出链接和已尝试来源。未完成初筛的候选留在后台，不作为“待判断”论文堆进主图；后台积压仍属于未完成工作。`scope.md` 保存确认，`papers.jsonl`、`queue.jsonl` 与证据 Markdown 支持继续调研。
