# AgEcon Literature MCP

一个面向个人学术研究的本地优先工具：用 CNKI 做发现式检索、题录与摘要获取，按需且经确认后只下载 PDF，通过 Zotero 10 官方 Local API 导入题录或题录+PDF，再由配套 Skill 完成有证据等级的初步文献脉络梳理。

当前版本：`0.1.0-alpha`。默认安全策略是“先检索、先计划、再确认、后写入”。

## 能做什么

- CNKI 主题、题名、作者、机构、关键词、摘要、来源、DOI 和一框式检索。
- 以本地 session 保存确切检索式、筛选条件、结果顺序和检索时间。
- 对选中文献按需补取摘要与完整题录，不强制抓取全部详情。
- 在当前检索结果内统计作者、年份、来源和关键词，并明确覆盖边界。
- 只读匹配 Zotero 现有条目：DOI、CNKI 来源键、规范化题名+首位作者+年份、模糊题名候选。
- PDF 下载先生成计划；确认后通过已登录 CNKI 浏览器获取，并校验 `%PDF-`、可解析性、页数、大小、MD5 和 SHA-256。
- 通过 Zotero 10 官方 Local API 导入：
  - `metadata_only`
  - `metadata_with_pdf`
  - `attach_pdf_to_existing`
- 用独立 SQLite 账本跟踪非原子附件流程：题录创建、附件创建、字节上传、上传注册、复核和完成。
- 配套 `agecon-literature-research` Skill：概念扩展、核心论文筛选、证据分级、作者/主题/方法/数据/结论脉络梳理。

## 当前边界

- CNKI 登录与网页结构可能变化；出现安全验证时需要人工完成。
- 校外访问不等于“永久下载权限”。工具只复用用户本人当前有效的校园 IP、
  CARSI 或学校 VPN 会话，且仅限学校已经订购、账号有权访问的内容。
- `references` 和 `similar` 的可靠完整图谱尚未实现。实验性 `RF` 检索只标为“候选引证”，不会冒充完整引证网络。
- 不下载 CAJ/NH，不绕过权限，不自动批量获取全文。
- 不删除 Zotero 条目，不覆盖已有题录，不自动合并模糊重复项，不写群组库。
- v0.1 的结构化题录写入仅支持 `journalArticle`；若 CNKI 来源键明确显示为学位论文、会议论文或报纸，计划会返回冲突而不是错误套用期刊字段。来源类型无法判断时，计划会显式标注期刊类型假设。
- Zotero 本地写入是普通本地修改；若用户开启 Zotero 同步，后续可能同步到其 Zotero 账户。

## 架构

```text
配套 Skill（检索策略、证据判断、综述脉络）
                       │
                       ▼
AgEcon MCP（确定性工具与安全门）
 ├─ CNKI 适配器 ── 已登录的本地浏览器 profile
 ├─ 文献 session ── 应用自有 SQLite 账本
 ├─ PDF 验真 ───── 应用数据目录/downloads
 └─ Zotero 适配器 ─ 官方 Local API :23119/api
                       │
                       ▼
              Zotero 本地个人文献库
```

详见 [docs/architecture.md](docs/architecture.md)、
[docs/cnki-access.md](docs/cnki-access.md) 和
[docs/zotero-local-api.md](docs/zotero-local-api.md)。

## 安装

前提：Python 3.11–3.14、Git、[uv](https://docs.astral.sh/uv/)、Zotero 10+。

```bash
git clone https://github.com/ae0n90/agecon-literature.git
cd agecon-literature
python3 scripts/bootstrap.py
uv run --no-editable playwright install chromium
```

Playwright 的 Chromium 仅用于用户本人已获授权的 CNKI 浏览器会话。浏览器 profile、cookies、PDF、检索历史和 Zotero key 均不进入 Git。

如需自定义配置：

```bash
mkdir -p "$HOME/Library/Application Support/agecon-literature"
cp config.example.toml "$HOME/Library/Application Support/agecon-literature/config.toml"
```

也可将 `AGECON_LIT_CONFIG` 指向其他 TOML 文件。

## 首次设置

### 1. CNKI 登录

```bash
uv run --no-editable agecon-literature cnki-init --profile default
```

在打开的浏览器窗口中完成学校/机构登录。状态由上游 `cnki-mcp` 保存在 `~/.cnki-mcp/profiles/`，不要提交该目录。

在校外优先使用本校 CARSI，并单独保存一个 profile：

```bash
uv run --no-editable agecon-literature cnki-init --profile institution-carsi
```

在 CNKI 机构登录页选择自己的学校，完成学校统一身份认证；然后在应用配置中设置：

```toml
[cnki]
profile = "institution-carsi"
```

该命令不会保存或代填学校密码，只保存浏览器会话。会话过期后需重新交互认证。
详细边界与 VPN 备选方案见 [CNKI 访问配置](docs/cnki-access.md)。

### 2. Zotero 只读探测

打开 Zotero，在“设置 → 高级”中允许本机其他应用通信，然后运行：

```bash
uv run --no-editable agecon-literature zotero-probe
```

### 3. Zotero 写授权

只有计划导入时才需要：

```bash
uv run --no-editable agecon-literature zotero-authorize
```

Zotero 弹窗中选择 **Always Allow**。PDF 导入需要多次写请求；一次性授权无法完成整条流程。持久 key 进入操作系统 Keychain，不写入配置文件。

### 4. 推荐：导入只进 Zotero Inbox

建议在 Zotero 中新建一个分类（如 `Inbox`），让 agent 导入的新条目都进入这里，再由你手工归入主题分类。这样 agent 不需要知道你的分类结构，也只需要一个白名单分类。

查出该分类的 key（8 位字母数字，不是分类名）：

```bash
curl --noproxy '*' -s 'http://127.0.0.1:23119/api/users/0/collections?limit=100' \
  | python3 -c 'import json,sys; [print(c["key"], c["data"]["name"]) for c in json.load(sys.stdin)]'
```

写入应用配置 `config.toml` 的 `[zotero]` 段：

```toml
allow_root_library = false
allowed_collections = ["ABCD1234"]  # Inbox
```

只有一个白名单分类且禁止导入根目录时，导入计划默认使用该分类；`doctor` 的 `import_targets` 会显示当前目标。修改配置后需重启 MCP 客户端。

### 5. 可选：用 Zotero 插件补全引文字段

CNKI 检索结果有时缺卷、期、页码。本工具和配套 Skill 不修改 Zotero 中已有题录；导入后 Skill 会列出缺失或可疑字段，建议在 Inbox 中用 [Jasminum（茉莉花）](https://github.com/l0o0/jasminum) 等插件从知网补全，再手工分类。插件可能改写 `extra` 字段和附件文件名，因此本工具的溯源信息（记录 ID、证据等级、PDF 哈希）保存在本地账本中，附件复核只比对文件内容（MD5）。

### 6. 自检

```bash
uv run --no-editable agecon-literature doctor
```

## 接入 MCP 客户端

推荐 stdio。以下是通用 Codex TOML 片段，路径替换为实际克隆目录：

```toml
[mcp_servers.agecon-literature]
command = "uv"
args = [
  "--directory",
  "/path/to/agecon-literature",
  "run",
  "--no-editable",
  "agecon-literature",
  "serve",
  "--transport",
  "stdio",
]
enabled = true
required = false
startup_timeout_sec = 30
tool_timeout_sec = 180
default_tools_approval_mode = "writes"
```

`default_tools_approval_mode` 只在客户端直接管理该 MCP 时生效。经网关或代理转接、或客户端审批策略设为不询问时，计划返回的确认 token 会直接交给模型，"展示计划 → 用户明确同意 → 提交"这一关由配套 Skill 约束。可接受的原因是写入范围本身有限：只写白名单目标，不删除、不覆盖已有条目，token 一次性且短期有效。
也可仅在 loopback 上运行 HTTP：

```bash
uv run --no-editable agecon-literature serve --transport http --host 127.0.0.1 --port 7790
```

服务拒绝绑定非 loopback 地址。

## 安装配套 Skill

仓库内 Skill 位于 `skills/agecon-literature-research/`。复制到个人 Codex Skill 目录：

```bash
uv run --no-editable python scripts/install_skill.py
```

若目标已存在，脚本默认拒绝覆盖；明确升级时使用 `--force`。

升级时先 `git pull`，再运行 `uv run --no-editable python scripts/install_skill.py --force` 并重启客户端。`--force` 会覆盖已安装副本；需要调整 Skill 时请改仓库中的 `skills/` 再安装，不要只改安装目录，否则下次升级会丢失改动，仓库与本地也会不一致。也可把 Skill 目录打成 zip，按支持 Skill bundle 的客户端方式安装。

## 安全工作流示例

1. `lit_search` 建立 session。
2. `lit_get_records(hydrate=true)` 只补取入围文献摘要。
3. `zotero_match` 只读查重。
4. 如确需全文，调用 `pdf_plan`；向用户展示题名、理由和目标路径。
5. 用户明确同意后，才把对应 token 交给 `pdf_download`。
6. `zotero_plan_import` 展示将创建、跳过或冲突的项目。
7. 用户明确同意后，才调用 `zotero_commit_import`。
8. 用 `zotero_verify_import` 回读校验；失败项先 `zotero_plan_resume`，再次确认后再恢复。

计划 token 短期有效且只能使用一次。任何冲突都要求重新计划，不自动合并。

## 开发与验证

```bash
python3 scripts/bootstrap.py
uv run --no-sync ruff check .
uv run --no-sync mypy
uv run --no-sync pytest
uv run --no-sync python scripts/export_tool_catalog.py --check
uv run --no-sync python scripts/check_tool_skill_contract.py
uv run --no-sync python scripts/validate_skill.py
uv build
uv run --no-sync python scripts/check_distribution.py
```

### macOS 上不要省略 `--no-editable`

uv 默认把当前项目安装为 editable 包，并通过 `.pth` 指向 `src/`。部分
macOS 环境会给 `.venv` 及该 `.pth` 设置 `UF_HIDDEN`，导致 Python 跳过
路径文件并报 `ModuleNotFoundError: agecon_literature_mcp`。本项目的运行命令
固定使用 `--no-editable`，将实际包文件安装到环境中，从而不依赖该路径文件。

若已出现这个错误，重新运行：

```bash
python3 scripts/bootstrap.py
uv run --no-editable agecon-literature --help
```

默认 CI 只使用合成数据和 HTTP mock，不访问 CNKI，不弹 Zotero 授权，也不写真实 Zotero 文献库。真实集成检查在 `tests/live/`，必须由用户显式启动。

## 许可证与上游

本项目采用 GPL-3.0-only。CNKI 浏览器层固定依赖 `SepineTam/cnki-mcp` 的特定 commit；详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
