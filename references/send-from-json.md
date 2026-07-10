# Send from JSON — 复杂邮件描述 schema

当一封邮件需要同时使用 **HTML 正文 + 多个内联图片 + 多个附件 + 多收件人 + 抄送 + 中文显示名 + 自定义纯文本替代版本** 时，CLI 参数会变得很冗长且容易出错。

`exmail.py send` 提供 `--from-json FILE` 参数，让你用一份 JSON 描述完整邮件结构。

```bash
python scripts/exmail.py send --from-json ./mail.json
```

## 完整字段参考

```jsonc
{
  // 收件人：字符串或字符串数组；多个用 , 或 ; 分隔
  "to": ["a@x.com", "b@x.com"],
  "cc": "c@x.com",
  "bcc": ["audit@x.com"],

  // 主题与发件人显示名
  "subject": "Q3 周报",
  "from_name": "张三",

  // 正文：以下三选一（优先级 body_html > body_file > body）
  "body_html": "<h1>周报</h1><p>详情：<img src=\"cid:logo\"></p>",
  "body_file": "./body.html",     // 路径相对 JSON 文件所在目录
  "body": "纯文本正文",

  // 是否为 HTML 邮件（body_html 出现时自动 true）
  "html": true,

  // HTML 邮件的纯文本替代版本；不传则自动从 HTML 简单去标签生成
  "text_alt": "周报\n详情：见图片",

  // 附件：路径相对 JSON 文件所在目录；支持任意文件类型，含中文文件名
  "attachments": [
    "./report.pdf",
    "./data.xlsx"
  ],

  // 内联图片：HTML 中通过 <img src="cid:CID"> 引用
  // 三种写法等价（对象形式的键支持别名：path≈file，cid≈content_id）：
  "inline_images": [
    {"path": "./logo.png", "cid": "logo"},
    {"file": "./logo2.png", "content_id": "logo2"},
    "./banner.jpg:banner_cid"
  ],

  // 线程合并（让邮件客户端把多封邮件归到同一线程）
  "in_reply_to": "<original-msg-id@host>",   // 被回复邮件的 Message-ID（含尖括号）
  "references": "<id1@host> <id2@host>",      // 空格分隔的历史 Message-ID 列表

  // 任意附加自定义头部（dict 形式，键为头名）
  // 以下头由脚本自动生成、传入将被忽略：From/To/Cc/Subject/Date/Message-ID/In-Reply-To/References
  "headers": {
    "X-Priority": "1",
    "X-Custom-Trace": "abc"
  }
}
```

## 与 CLI 参数的合并规则

`--from-json` **可以**与命令行参数同时使用：

| 字段 | 合并方式 |
|------|---------|
| `to` / `cc` / `bcc` / `subject` / `from_name` | CLI 参数显式提供时**覆盖** JSON 字段 |
| `html` | CLI `--html` 提供时强制 true（不会强制 false） |
| `body` / `body_file` | CLI 提供时**覆盖** JSON 中的正文 |
| `attachments` | CLI `--attach` **追加**到 JSON 列表后（不覆盖） |
| `inline_images` | CLI `--inline-image` **追加**到 JSON 列表后（不覆盖） |
| `in_reply_to` / `references` | CLI `--in-reply-to` / `--references` 显式提供时**覆盖** JSON 字段 |
| `headers` | CLI `--header` **追加**到 JSON 的 headers 字典（同名键覆盖） |

例如：用 JSON 描述一份固定的邮件模板，每次发送只需在命令行覆盖 subject：

```bash
# 每周用同一份 mail.json，只改主题
python scripts/exmail.py send --from-json ./weekly.json --subject "周报 W22"
python scripts/exmail.py send --from-json ./weekly.json --subject "周报 W23"
```

## MIME 结构

`exmail.py` 会根据邮件内容自动选择最合适的 MIME 树：

| 内容组合 | 顶层结构 |
|---------|---------|
| 纯文本 | `text/plain`（外层 `multipart/alternative` 仅含一个 part） |
| HTML（无附件无内联图） | `multipart/alternative` → `text/plain + text/html` |
| HTML + 附件 | `multipart/mixed` → `multipart/alternative` + 附件 parts |
| HTML + 内联图 | `multipart/related` → `multipart/alternative` + image parts |
| HTML + 内联图 + 附件 | `multipart/mixed` → (`multipart/related` → `multipart/alternative` + image parts) + 附件 parts |

这是邮件客户端（Outlook / Foxmail / Gmail / Apple Mail）兼容性最佳的结构。

## 内联图片 vs 附件 — 怎么选？

| 需求 | 用法 |
|------|------|
| 图片**显示在正文里**（产品截图、架构图、内嵌徽标、风险标签等） | `inline_images` + 正文写 `<img src="cid:NAME">` |
| 图片**作为附件**显示在邮件底部（用户需主动点击下载） | `attachments` |
| 同一张图既要内嵌又要作为附件 | 两个列表都加（cid 与文件名可不同） |

## 完整示例：含审批卡片 + 内联图 + 多附件的邮件

`mail.json`:

```json
{
  "to": "approver@company.com",
  "cc": ["watcher1@company.com", "watcher2@company.com"],
  "subject": "费用报销审批-差旅费 38000 元",
  "from_name": "财务OA系统",
  "body_file": "./approval_card.html",
  "html": true,
  "attachments": [
    "./invoice.pdf",
    "./travel_details.xlsx"
  ],
  "inline_images": [
    {"path": "./oa_logo.png", "cid": "oa_logo"},
    {"path": "./status_pending.png", "cid": "status_badge"}
  ],
  "text_alt": "差旅费报销审批：申请人 张伟，金额 ¥38,000，请审批。"
}
```

`approval_card.html`:

```html
<div style="font-family:Microsoft YaHei,sans-serif;max-width:600px">
  <img src="cid:oa_logo" width="120" style="margin-bottom:12px">
  <h2 style="color:#0a6cff">费用报销审批</h2>
  <table style="border-collapse:collapse;width:100%">
    <tr><td>审批类型</td><td>差旅费报销</td></tr>
    <tr><td>申请人</td><td>张伟</td></tr>
    <tr><td>金额</td><td>¥38,000</td></tr>
    <tr><td>状态</td><td><img src="cid:status_badge" width="60"></td></tr>
  </table>
  <p>请尽快在 OA 系统中处理。</p>
</div>
```

发送：

```bash
python scripts/exmail.py send --from-json ./mail.json
```

## 常见错误

| 错误信息 | 原因 |
|---------|------|
| `--from-json 文件 JSON 解析失败` | JSON 语法错误，注意中文双引号 / 末尾逗号 |
| `inline_images 字符串必须是 path:cid 形式` | 字符串语法漏写冒号或 cid |
| `内联图文件不存在` | JSON 中的相对路径不是相对 JSON 文件目录，或拼写错误 |
| `send 缺少必填字段：to/subject/...` | JSON 与 CLI 合并后仍缺少 to / subject / 任一种正文 |
| 邮件客户端中内联图显示为附件 | HTML 中 `<img src="cid:XXX">` 的 cid 与 `inline_images` 中 cid 不一致；注意大小写敏感 |

## 安全提示

JSON 中**不要**写入凭证字段。凭证走 CLI `--username/--password`。`mail.json` 可以纳入版本控制，但必须确认其中无敏感信息。
