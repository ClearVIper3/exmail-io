---
name: exmail-io
description: 通过 IMAP/SMTP 公有协议在腾讯企业邮箱（企业微信邮箱 / exmail.qq.com）收发邮件的技能，预置 imap.exmail.qq.com:993 与 smtp.exmail.qq.com:465 配置。支持收件箱列表/搜索/正文读取/附件下载/标记已读/修改邮件日期，以及纯文本/HTML/附件/抄送/密送/内联图片（cid）/JSON 描述完整邮件/线程合并（In-Reply-To/References）/自定义头部 等发件能力。内置测试素材库（附件/内联图/HTML 组件/邮件模板）与拼装工具，可快速构造 E2E 评测所需的各类邮件。当用户需要"收企业邮箱邮件 / 发企业邮箱邮件 / 读企业微信邮箱 / 查企微邮件 / receive exmail / send exmail / 检查未读邮件 / 下载邮件附件 / 回复企业邮件 / 内联图片邮件 / 富文本邮件 / 构造测试邮件 / E2E 评测邮件 / 修改邮件日期 / 篡改邮件时间"等时使用，即使用户没有显式说出 IMAP / SMTP 也应使用本技能。
---

# Exmail I/O Skill

腾讯企业邮箱（企业微信邮箱，域名 `exmail.qq.com`）专用收发邮件技能。基于 Python `imaplib` + `smtplib` 标准库实现，无需第三方依赖，跨平台可用。

## 核心能力

| 能力 | 说明 |
|------|------|
| **IMAP 收件** | 连接 `imap.exmail.qq.com:993`，列出/搜索/读取邮件，下载附件，标记已读 |
| **SMTP 发件** | 连接 `smtp.exmail.qq.com:465`，发送文本/HTML/带附件邮件 |
| **修改邮件日期** | 拉取邮件 → **全局替换所有 RFC 2822 日期串**（Date / Received 多行 / X-Received / Message-ID）→ IMAP APPEND 并同步 INTERNALDATE → 删除原件；支持指定时区 |
| 邮箱地址支持 | `@<企业域名>` 自定义域 与 `@exmail.qq.com` 通用域 |
| 凭证管理 | 优先环境变量，其次 JSON 配置文件，绝不硬编码 |
| 收件搜索 | 未读、按日期、按发件人、按主题、按正文关键词；中文关键词自动客户端兜底（绕过腾讯企业邮 SEARCH bug） |
| 多文件夹 | 支持 INBOX / Sent Messages / Drafts / Junk / 自定义；提供 `folders` 子命令查看（含中文文件夹名 IMAP UTF-7 解码） |
| 附件 | 收件时按文件名提取并保存；发件时支持任意文件类型，含中文文件名 |
| 编码兼容 | 自动处理 RFC 2047 主题编码、`utf-8 / gbk / gb2312` 正文解码 |
| 大邮箱友好 | `--output FILE` 写文件、`--no-html` / `--body-lines N` 截断长邮件 |

## 服务器配置（已预置，无需用户提供）

IMAP `imap.exmail.qq.com:993`（SSL）/ SMTP `smtp.exmail.qq.com:465`（SSL）。详见 `references/exmail-protocol.md`。如管理员未开启 IMAP/SMTP，需在「企业微信管理端 → 协作 → 邮件 → 安全管理 → 客户端访问权限」开启。

## 工作流程（SOP）

每次任务按以下顺序推进。**遇到信息缺失时，先尝试从环境变量与配置文件读取，不要一上来就追问用户。**

### 步骤 1：获取凭证

凭证通过 CLI 参数 `--username` / `--password` 传入（必填）。Agent 从 `references/test-accounts.md` 或用户提供的信息中获取，直接传给脚本。

⚠️ **关键**：腾讯企业邮箱**不支持 OAuth2**。若企业管理员开启了「安全登录」（绝大多数企业都开了），用户**必须使用客户端专用密码**，而非邮箱登录密码。获取步骤见 `references/get-client-password.md`。

如果用户用登录密码尝试且认证失败，立即提示：「企业邮箱已开启安全登录，请使用客户端专用密码（不是登录密码）」并指引到 `references/get-client-password.md`。

> 💡 **联调测试场景**：当用户提及"主测试号 / 刘畅 / wktest.site 测试账号"等内置联调身份时，直接读取 `references/test-accounts.md` 中登记的邮箱地址与客户端专用密码，通过 `--username` / `--password` 传给脚本，**不要再追问用户**。

### 步骤 2：判断意图并路由

根据用户表述路由到对应分支，所有操作都通过 `scripts/exmail.py` 完成：

- **收件/查阅** → 分支 A（inbox / folders / read）
- **发件/回复** → 分支 B（send / reply）
- **邮件管理** → 分支 A 中的 flag / move / delete / modify-date

---

### 分支 A：收件与邮件管理（IMAP）

#### A.1 列出邮件

```bash
# 列出收件箱最近 10 封
python scripts/exmail.py inbox --limit 10

# 仅未读
python scripts/exmail.py inbox --unread --limit 20

# 来自指定发件人
python scripts/exmail.py inbox --from "boss@company.com" --limit 50

# 主题包含关键词（中英文都直接用 --subject，自动选服务端或客户端兜底路径）
python scripts/exmail.py inbox --subject "Weekly" --limit 30
python scripts/exmail.py inbox --subject "周报" --limit 30

# 正文关键词（中文走客户端兜底，开销大；建议配合 --since 缩小范围）
python scripts/exmail.py inbox --body "合同" --since 2026-05-01 --limit 30

# 指定日期范围（接受 YYYY-MM-DD 或 DD-Mon-YYYY，自动转换）
python scripts/exmail.py inbox --since 2026-05-01 --before 2026-05-21

# 指定文件夹（先用 folders 子命令查看真实名称）
python scripts/exmail.py inbox --folder "Sent Messages" --limit 50
python scripts/exmail.py inbox --folder "Junk" --unread

# 大邮箱避免终端截断：写到文件
python scripts/exmail.py inbox --limit 200 --output ./inbox.json
```

输出 JSON 数组，每项包含 `uid / from / to / subject / date / size / unread / has_attachment`。

#### A.2 列出文件夹

```bash
# 列出所有文件夹（中文文件夹自动解码 IMAP modified UTF-7）
python scripts/exmail.py folders
```

返回 `[{name, raw_name, flags, delimiter}, ...]`。`name` 是解码后的可读名（如 `已发送`），`raw_name` 是 IMAP 原始字节（如 `&XfJT0ZAB-`）——后续 `--folder` 两种都可以传。

#### A.3 读取邮件全文

```bash
# 按 UID 读取（UID 来自 inbox 的输出）
python scripts/exmail.py read --uid 12345

# 长邮件友好：去掉 body_html，正文截断到前 50 行
python scripts/exmail.py read --uid 12345 --no-html --body-lines 50

# 写到文件，避免终端截断
python scripts/exmail.py read --uid 12345 --output ./mail-12345.json

# 读取并自动标记为已读
python scripts/exmail.py read --uid 12345 --mark-seen

# 读取并下载所有附件到指定目录
python scripts/exmail.py read --uid 12345 --save-attachments ./downloads/
```

返回结构：`{from, to, cc, subject, date, body_text, body_html, attachments: [{filename, size, saved_path}]}`。

#### A.4 标记 / 删除 / 移动

```bash
python scripts/exmail.py flag --uid 12345 --seen          # 标记已读
python scripts/exmail.py flag --uid 12345 --unseen        # 标记未读
python scripts/exmail.py flag --uid 12345 --flagged       # 标星
python scripts/exmail.py flag --uid 12345 --unflagged     # 取消标星
python scripts/exmail.py move --uid 12345 --to "Archive"  # 移动到文件夹
python scripts/exmail.py delete --uid 12345               # 删除（移到已删除）
```

#### A.5 修改邮件日期

通过拉取原始 .eml、**全局替换邮件中所有 RFC 2822 日期串**、IMAP APPEND 重新存入（并同步设置 INTERNALDATE）、删除原件的方式修改邮件日期：

```bash
# 修改单封邮件的日期（默认时区 +0800）
python scripts/exmail.py modify-date --uid 12345 --new-date "2026-06-01 10:30:00"

# 指定时区
python scripts/exmail.py modify-date --uid 12345 --new-date "2026-06-01" --timezone "+0000"

# 保留原邮件（不删除）
python scripts/exmail.py modify-date --uid 12345 --new-date "2026-06-01 10:30:00" --keep-original

# 指定文件夹
python scripts/exmail.py modify-date --uid 12345 --folder "Sent Messages" --new-date "2026-05-20 09:00:00"
```

返回 JSON：`{success, old_uid, new_uid, folder, new_date, replaced_dates}`。`replaced_dates` 为本次替换掉的日期字符串数量（通常 ≥1，含 Date + 各 Received 行）。

> ⚠️ **为什么不能只改 `Date` 头**：邮件客户端（腾讯企业邮 WebMail / Outlook / Thunderbird 等）判断邮件到达时间时**优先读取 `Received` 字段的时间戳**，而非 `Date`。日期还可能散布在 `Received`（常折行成多行、有 `for <...>;` / `id ;` 等多种格式）、`X-Received`、`Message-ID` 等位置。逐字段修改必然遗漏，导致"改完仍显示旧日期"。
>
> ✅ **当前实现**：对整封邮件原始字节做**全局正则替换**，把所有符合 RFC 2822 格式的日期串一次性统一为新日期；同时把 IMAP `INTERNALDATE` 也设为新日期（很多客户端按它排序/显示）。一步到位、不留残留。
>
> ⚠️ 注意：修改日期会生成新 UID，原 UID 默认被删除。如需保留原件请加 `--keep-original`。
>
> 💡 **决策指引**：对用户邮箱中的真实邮件操作时，**默认加 `--keep-original`**，确认无误后再手动删除原件。仅在构造测试数据等明确不需要保留的场景下省略该参数。

#### A.6 中文/复杂搜索

中文搜索直接用 `--subject` / `--from` / `--body`，脚本自动走客户端兜底过滤。复杂语法用 `--raw-search`（如 `OR` / `NOT` / `LARGER`）。详见 `references/imap-search.md`。

```bash
python scripts/exmail.py inbox --subject "周报" --limit 20
python scripts/exmail.py inbox --raw-search 'OR FROM "a@x.com" FROM "b@x.com"'
```

---

### 分支 B：发件（SMTP）

```bash
# 纯文本
python scripts/exmail.py send \
  --to "user1@x.com,user2@x.com" \
  --subject "通知" \
  --body "邮件正文"

# HTML + 附件 + 抄送 + 密送
python scripts/exmail.py send \
  --to user@x.com \
  --cc boss@x.com \
  --bcc audit@x.com \
  --subject "周报 W21" \
  --body-file ./report.html \
  --html \
  --attach ./report.pdf \
  --attach ./data.xlsx \
  --from-name "张三"

# HTML 正文中嵌入内联图片（cid:）：正文里写 <img src="cid:logo">
python scripts/exmail.py send \
  --to user@x.com \
  --subject "产品架构图" \
  --body-file ./body.html --html \
  --inline-image ./architecture.png:logo \
  --inline-image ./badge_high.png:risk_badge \
  --attach ./details.pdf

# 复杂邮件用 JSON 一站式描述（支持 to/cc/bcc/subject/body_file/
# attachments/inline_images/from_name/text_alt 等所有字段）
python scripts/exmail.py send --from-json ./mail.json
# CLI 参数与 JSON 共存：CLI 覆盖标量字段，--attach/--inline-image 追加到列表

# 回复某封收到的邮件（保留 In-Reply-To / References，自动加 Re: 前缀）
python scripts/exmail.py reply \
  --uid 12345 \
  --body "收到，明天讨论"

# reply 子命令支持与 send 等价的高级参数：
python scripts/exmail.py reply --uid 12345 \
  --body-file ./reply.html --html \
  --attach ./补充材料.pdf \
  --inline-image ./screenshot.png:shot \
  --include-quote                # 在新正文下方追加原文引用块
```

发件人 `From` 字段强制等于认证用户名，避免被反垃圾系统拒收。

> 📎 `--attach` = 附件（邮件底部）；`--inline-image PATH:CID` = 内嵌图（正文 `<img src="cid:CID">`）。
> 复杂邮件用 `--from-json mail.json` 一站式描述，schema 见 `references/send-from-json.md`。

#### B.x 用 `render_email.py` 拼装复杂正文

需要模板 + 组件 + 内联图拼装 HTML 正文时，用 `scripts/render_email.py`（支持 `render` 仅输出 HTML、`compose` 一步生成 `mail.json`）：

```bash
# 推荐：一步到位生成 mail.json，配合 send --from-json 直接发出
python scripts/render_email.py compose \
  --template boss_request.html \
  --set BODY="请确认排期" \
  --set 'IMG_TAG_OR_EMPTY=<img src="cid:arch1" width="100%">' \
  --set DEADLINE_LINE="" --set LINK_HTML="" \
  --to me@example.com --subject "Q3产品路线图确认" --from-name "技术负责人" \
  --inline-image "assets/inline_images/architecture.png:arch1" \
  --output ./mail.json

python scripts/exmail.py send --from-json ./mail.json
```

> 模板/组件占位符清单见 `assets/index.md`；构造测试邮件时**优先复用 templates + components**。

#### Python 调用

```python
from scripts.exmail import ExmailClient

cli = ExmailClient(username="me@company.com", password="<客户端专用密码>")
unread = cli.list_inbox(unread_only=True, limit=10)
mail = cli.read(uid=unread[0]["uid"], mark_seen=True, save_attachments_to="./tmp")
cli.send(to=["a@x.com"], subject="主题", body="正文", from_name="我")
```

> 完整 API 签名见 `scripts/exmail.py` 中 `ExmailClient` 类定义（方法：`list_folders` / `list_inbox` / `read` / `flag` / `move` / `delete` / `append` / `send` / `reply`）。

### 步骤 3：错误处理

| 错误关键字 | 快速处理 |
|-----------|---------|
| `LOGIN failed` / `AUTHENTICATIONFAILED` | 改用客户端专用密码，见 `references/get-client-password.md` |
| `Connection timed out` / `getaddrinfo failed` | 检查网络/代理/IP 白名单 |
| `554` / `spam` | 检查 From 一致、降频、去可疑链接 |
| SEARCH 结果不精确 | 用 `--subject` / `--body` 走客户端兜底，勿依赖服务端 SEARCH |

详细排查见 `references/troubleshooting.md`。

## 安全规范

1. **绝不在代码、日志、回复中明文打印客户端专用密码**
2. 邮件正文与附件可能含敏感信息，**默认不要回显完整正文给用户之外的第三方**
4. 一次性发送多收件人且 > 50 人时启用逐个发送间隔（如 `--send-interval 2`，每封间隔 2 秒），降低被反垃圾系统打分的风险。该参数仅在同一条 send 命令含多个 `--to` 时生效，会拆成多次逐个发送。

## 运行时依赖

仅依赖 **Python 3.8+ 标准库**（`imaplib` / `smtplib` / `email` / `ssl` / `json` / `argparse` 等），无需 `pip install` 任何第三方包。

## 目录结构

```
exmail-io/
├── SKILL.md                              # 本文件
├── scripts/
│   ├── exmail.py                         # 核心 CLI + 库（IMAP+SMTP 一体，~1500 行，勿整体读取）
│   └── render_email.py                   # 邮件正文拼装工具（模板+组件→HTML/JSON）
├── assets/
│   ├── index.md                          # ⭐ 测试素材库导航（必读）
│   ├── subjects.yaml                     # 主题文案池
│   ├── attachments/                      # 通用附件（readable / locked / confidential）
│   ├── inline_images/                    # 通用内联 PNG（架构图/监控/截图/海报等）
│   ├── components/                       # HTML 片段（审批卡/告警卡/通知/会议/签名/保密/线程引用…）
│   └── templates/                        # 完整邮件骨架（boss/customer/peer/cc/notice/approval/alert/线程追问）
└── references/
    ├── exmail-protocol.md                # 服务器/端口/认证协议详解
    ├── get-client-password.md            # 客户端专用密码获取步骤
    ├── imap-search.md                    # IMAP SEARCH 语法速查
    ├── send-from-json.md                 # 复杂邮件 JSON 描述 schema
    ├── test-accounts.md                  # 内置测试账号（仅联调用）
    └── troubleshooting.md                # 故障排查
```

> 📦 **测试 / E2E 评测场景构造邮件时**：先看 `assets/index.md`，里面已经预置了
> 附件（含不可读 / 保密变体）、内联图、审批卡片 / 通知标签 / 保密 banner / 代码
> 块 / 表格等 HTML 组件，**不要重新造轮子**，直接复用并替换 `{{占位符}}` 即可。

## 与通用 email-sender 的协作

如果用户的发件场景**完全不需要收件**且邮箱**非企业邮箱**（如 QQ/Gmail/163），优先使用 `email-sender`。
如果涉及**企业邮箱收件**或**收发一体**，使用本 skill。两者可共存。
