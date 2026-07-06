# IMAP SEARCH 语法速查

本 skill 的 `inbox` 子命令在底层使用 IMAP `SEARCH`。常用参数已封装为高层选项；复杂场景使用 `--raw-search` 直接传 IMAP 原生语法。

## 常用 criteria

| 关键字 | 说明 | 示例 |
|--------|------|------|
| `ALL` | 全部 | `ALL` |
| `UNSEEN` | 未读 | `UNSEEN` |
| `SEEN` | 已读 | `SEEN` |
| `FLAGGED` | 加星 | `FLAGGED` |
| `FROM "<addr>"` | 发件人 | `FROM "boss@x.com"` |
| `TO "<addr>"` | 收件人 | `TO "me@company.com"` |
| `SUBJECT "<text>"` | 主题包含 | `SUBJECT "weekly"` |
| `BODY "<text>"` | 正文包含 | `BODY "invoice"` |
| `SINCE <date>` | ≥ 日期 | `SINCE 01-May-2026` |
| `BEFORE <date>` | < 日期 | `BEFORE 21-May-2026` |
| `ON <date>` | = 日期 | `ON 20-May-2026` |
| `LARGER <bytes>` | 大于 | `LARGER 1048576` |
| `SMALLER <bytes>` | 小于 | `SMALLER 102400` |

> 日期格式必须为 `DD-Mon-YYYY`（英文月份缩写：Jan/Feb/Mar/Apr/May/Jun/Jul/Aug/Sep/Oct/Nov/Dec）。

## 组合：AND / OR / NOT

- 默认空格连接 = AND：`UNSEEN FROM "boss@x.com"`
- OR：`OR FROM "a@x.com" FROM "b@x.com"`
- NOT：`NOT FROM "spam@x.com"`

## 中文/关键词搜索（客户端兜底机制）

> ⚠️ **腾讯企业邮服务端已知缺陷**（实测 2026-05）：
>
> - `SEARCH CHARSET UTF-8 SUBJECT/BODY "..."` 会被**忽略**，返回全部邮件
> - 即使纯 ASCII 关键词，`SUBJECT "..."` / `BODY "..."` 也不做精确子串匹配
>
> **因此建议所有关键词搜索都用本 skill 的高层参数 `--subject` / `--from` / `--body`**。

**本 skill 的应对策略**：`--subject` / `--from` / `--body` 统一走**客户端兜底过滤**——服务端用其它条件（UNSEEN / SINCE / BEFORE）粗筛，扫描窗口扩大到 `limit × 10` 封最新邮件，本地拉取头部或正文做大小写不敏感子串匹配。`--raw-search` 中如包含中文字面量也会自动提取做客户端兜底。

```bash
python scripts/exmail.py inbox --subject "周报" --limit 5
python scripts/exmail.py inbox --from "张强"  --limit 5
python scripts/exmail.py inbox --body "合同" --since 2026-05-01 --limit 20
```

**性能提示**：`--body` 需拉全文，开销大，**务必配合 `--since` / `--from` 缩小范围**。

## 示例

```bash
# 老板发的、本月、未读
python scripts/exmail.py inbox \
  --raw-search 'UNSEEN FROM "boss@company.com" SINCE 01-May-2026'

# 本周内、主题或正文含 "invoice"
python scripts/exmail.py inbox \
  --raw-search 'SINCE 19-May-2026 OR SUBJECT "invoice" BODY "invoice"'

# 大于 5MB 的邮件（可能是带大附件）
python scripts/exmail.py inbox --raw-search 'LARGER 5242880'
```

## 文件夹

`inbox` 默认搜 `INBOX`，可以用 `--folder` 切换。先用 `folders` 子命令查看真实文件夹名：

```bash
python scripts/exmail.py folders
# 输出每项含 name（解码后，如 "已发送"）+ raw_name（IMAP 原始字节，如 "&XfJT0ZAB-"）
# --folder 两种都可以传

python scripts/exmail.py inbox --folder "Sent Messages" --limit 20
python scripts/exmail.py inbox --folder "已发送" --limit 20         # 自动 UTF-7 编码
python scripts/exmail.py inbox --folder "Junk" --unread
```

腾讯企业邮常见文件夹（不同账号语言/历史可能略有差异，**以 `folders` 输出为准**）：

| name | 说明 |
|---|---|
| `INBOX` | 收件箱 |
| `Sent Messages` | 已发送 |
| `Drafts` | 草稿箱 |
| `Deleted Messages` | 已删除 |
| `Junk` | 垃圾邮件 |

## --raw-search 中的关键词路径对比

| 写法 | 路径 | 说明 |
|---|---|---|
| `--body "invoice"` / `--subject "周报"` | 客户端兜底 | 结果可信（推荐） |
| `--raw-search 'BODY/SUBJECT "..."'` | 服务端 | **不推荐**：腾讯企业邮不精确 |

## 参考

- RFC 3501 §6.4.4 SEARCH Command
- RFC 3501 §5.1.3 Mailbox International Naming Convention（IMAP modified UTF-7）
