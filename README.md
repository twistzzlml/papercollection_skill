# Paper Collection Skill

一个以研究主题为主线的文献调研 skill：先与研究者讨论检索词，再用种子论文确定细分范围，随后进行主题检索和前后向引用追踪，整理 Zotero 文献库与 XMind 路线图。

Skill 名称：`literature-roadmap`。面向支持 `SKILL.md` 的智能体环境，附带 Codex 配置。Python 脚本负责校验、导图导出和 Zotero 同步；检索、阅读与学术判断由智能体执行，不是一个独立运行的全自动爬虫。

## 工作流程

1. **检索前讨论**：描述研究目标，可提供论文、文档或资料目录。智能体通过逐步提问澄清边界，并与使用者确认关键词及检索组合。
2. **种子后讨论**：阅读真实摘要初筛种子，结合可获取的 Introduction、Related Work 提出主题树；讨论哪些细分 scope 核心展开、仅作对照或排除。
3. **自主调研**：以 Google Scholar 为主，追踪参考文献和被引论文，核对来源与发表等级，逐批消化筛选队列。
4. **统一汇报**：交付导图与文献库，集中讨论剩余范围取舍和全文下载求助。

已读摘要并确认相关、但全文获取受阻的论文仍进入导图，标注“需用户帮助下载”。尚未筛选的候选留在后台，不作为“待判断”节点堆入导图；未处理完的工作不会被算作调研完成。

## 安装

克隆仓库，将 `skills/literature-roadmap` 整个目录放入你的 skill 目录。Codex 默认位置为 `~/.codex/skills/`；自定义 `CODEX_HOME` 时使用其下的 `skills/`。若已安装同名 skill，先检查并保留自己的修改。

```bash
git clone https://github.com/twistzzlml/papercollection_skill.git
```

Windows PowerShell 示例（默认安装位置）：

```powershell
$skillDestination = Join-Path $HOME '.codex/skills'
New-Item -ItemType Directory -Force -Path $skillDestination | Out-Null
Copy-Item -Recurse -LiteralPath './papercollection_skill/skills/literature-roadmap' -Destination $skillDestination
```

macOS / Linux 示例：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R papercollection_skill/skills/literature-roadmap "${CODEX_HOME:-$HOME/.codex}/skills/"
```

## 配置与使用

需要可用的 Google Scholar / HasData 连接。自动写入 Zotero 还需要可写连接或 Zotero Web API key 与目标库 ID。Python 3.9+ 用于运行附带脚本，不需要第三方 Python 依赖。XMind 用来查看导出的 `.xmind` 文件。

具体 API key 名称、配置路径、连接检查和命令见 [启动指南](skills/literature-roadmap/README.md)。仓库不提供真实凭据，也不自动加载 `.env`；请使用连接器凭据管理或运行时环境变量。

启动示例：

> 使用 $literature-roadmap 调研 Java 反序列化防御。我有一些种子论文和讨论文档。先和我讨论检索词，再搜集种子并确认细分 scope，最后整理 Zotero 和 XMind。

继续调研时提供原调研目录，智能体从 `scope.md`、状态文件和未完成队列恢复。

默认仅纳入英文文献，优先 CCF A/B/C 正式论文与近两年预印本；排除已核实不在 CCF 的期刊论文，预印本豁免。非 CCF 会议按范围约定处理。以上偏好可以在启动讨论中调整；论文数不设固定上限，以研究相关性控制范围。

## 文件结构

```text
skills/literature-roadmap/
├── SKILL.md                 智能体入口与三阶段交互要求
├── README.md                连接、凭据配置与使用说明
├── agents/openai.yaml       Codex 展示信息
├── references/              研究流程、状态格式、工具适配
├── scripts/roadmap.py        状态校验与原生 XMind 导出
├── scripts/zotero_sync.py    Zotero Local / Web API 同步
└── tests/                   离线回归测试
```

调研输出包括 `roadmap.xmind`、`scope.md`、`papers.jsonl`、`queue.jsonl`、证据 Markdown 以及 `download-help.md`。这些是使用者的数据，不随 skill 发布。

## 验证

在仓库根目录运行：

```bash
python -X utf8 -m unittest discover -s skills/literature-roadmap/tests -v
```

测试覆盖导图结构、候选隔离、下载求助条件及 Zotero 同步的去重和已有内容保护，使用模拟 API，不需要 key，也不访问真实文献库。测试不能替代真实检索、全文阅读或 XMind 客户端检查。

Zotero 同步脚本管理条目、受管理笔记及收藏夹关联；PDF 上传需要可用的附件工具另行完成。机构登录由使用者自行完成密码与 MFA。工具受阻时保存进度并如实报告覆盖缺口。
