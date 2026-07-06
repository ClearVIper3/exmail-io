# Assets 通用素材库

本目录提供**测试 / 演示 / E2E 评测**场景下构造邮件所需的全部预制素材。
SKILL 在收到「构造若干邮件 + 含附件 / 内联图 / 审批卡片 / 通知标签…」类需求时，
**优先复用本目录文件，不要重复造轮子**。

## 目录

- [目录结构](#目录结构)
- [附件清单（attachments/）](#附件清单attachments)
- [内联图清单（inline_images/）](#内联图清单inline_images)
- [HTML 组件（components/）— 用法](#html-组件components用法)
- [邮件模板（templates/）— 用法](#邮件模板templates用法)
- [主题文案池（subjects.yaml）](#主题文案池subjectsyaml)
- [SMTP 协议层无法表达的语义](#smtp-协议层无法表达的语义必须妥协)
- [重新生成](#重新生成)

## 目录结构

```
assets/
├── index.md                       ← 本文件（导航索引）
├── subjects.yaml                  主题文案池（系统通知/公告/活动/订阅/FYI/历史）
│
├── attachments/                   附件库
│   ├── readable/                  可读附件（PDF/DOCX/XLSX/TXT/PNG）
│   ├── locked/                    损坏/不可读（模拟"无权限"）
│   └── confidential/              保密附件（文件名带 [保密] 前缀）
│
├── inline_images/                 PNG 内联图（嵌正文用 cid 引用）
│
├── components/                    可复用 HTML 片段（含 {{占位符}}）
│   ├── signature_wechat.html      签名档「发自我的企业微信」
│   ├── signature_normal.html      普通签名档（参数化）
│   ├── approval_card.html         审批卡片（差旅/合规/采购/资源/绩效）
│   ├── alert_card.html            P0/P1 告警卡片（服务名/影响/责任人/详情链接）
│   ├── meeting_invite_card.html   日程邀约卡片（接受/暂定/拒绝按钮）
│   ├── meeting_booked_card.html   预定会议卡片（HR 面谈类）
│   ├── notice_label.html          通知格式标签（系统维护/安全/人事/行政）
│   ├── permission_expiry_notice.html  权限到期提醒（系统/到期时间/续期链接）
│   ├── large_attachment_link.html 超大附件/网盘链接卡片（含状态与有效期）
│   ├── confidential_banner.html   保密模式提示条
│   ├── forwarded_from_chat.html   "由群聊转发"来源标识
│   ├── translate_banner.html      英文邮件翻译提示条
│   ├── risk_level_badge.html      风险等级标签（高/中/低）
│   ├── code_block.html            灰色等宽代码粘贴区
│   ├── log_block.html             暗色日志粘贴区
│   ├── data_table.html            通用数据表格框架
│   ├── auto_daily_report.html     自动日报（等宽统计表格）
│   ├── thread_quote.html          邮件线程引用原文块。嵌到正文底部作"--------- 原始邮件 ---------"
│   └── subscription_summary.html  订阅邮件摘要+链接
│
└── templates/                     完整邮件骨架（拼装组件后即可作为 body-file）
    ├── boss_request.html          上级 → 你的请求邮件
    ├── customer_request.html      客户/外部 → 你（含报错日志/截图）
    ├── peer_request.html          同事/平级 → 你
    ├── cc_generic.html            CC 类骨架（项目同步/纪要/方案变更/风险）
    ├── system_notice.html         系统通知/群发/FYI 通用骨架
    ├── approval_email.html        审批邮件（含审批卡片，开箱即用）
    ├── alert_email.html           监控告警邮件（P0/P1 样式，含告警头部与详情按钮）
    └── thread_followup.html       线程追问邮件（正文 + 签名 + 原文引用）
```

## 附件清单（attachments/）

### readable/ — 可读附件

| 文件 | 用途 / 出现场景 |
|------|------|
| `return_codes.xlsx` (~126KB) | 「返回码对照表」——接口联调类邮件 |
| `compliance_report.pdf` | 「合规评估报告」——合规审批 |
| `complaint_detail.pdf` (~580KB语义) | 「投诉详情」——客户投诉 |
| `dd_report_v3.pdf` | 「尽调报告 v3」——客户邮件 |
| `pricing_plan_v2.pdf` | 「定价方案 v2」——产品总监请审阅 |
| `risk_plan_v2.pdf` | 「风控方案 v2」 |
| `incident_report.pdf` | 「故障报告」 |
| `procurement_plan_v2.pdf` | 「采购方案 v2」 |
| `design_doc.pdf` | 「设计文档」 |
| `plan_compare_v2.pdf` | 「方案对比 v2」 |
| `vpn_policy_detail.pdf` | 「VPN 策略详情」 |
| `cooperation_plan_v1.pdf` | 「合作方案 v1」（注入 case 用） |
| `expense_detail.pdf` | 「报销明细」 |
| `material_list.pdf` | 「物料清单」 |
| `quotation.pdf` | 「报价单」 |
| `requirements_doc.pdf` | 「需求文档」 |
| `weekly_report.pdf` | 「周报」 |
| `revision_v3.docx` | 「修订稿 v3」 |
| `requirements_list.docx` | 「需求清单」 |
| `api_doc.docx` | 「接口文档」 |
| `device_compare.xlsx` | 「设备参数对比」 |
| `order_detail.xlsx` | 「订单明细」 |
| `request_list.xlsx` | 「需求清单」xlsx |
| `milestone.xlsx` | 「项目里程碑」 |
| `review_record.xlsx` | 「评审记录」 |
| `strategy_overview.pdf` | 「战略总览」 |
| `error_log.txt` | 「错误日志」 |
| `stat_daily.txt` | 「自动统计文本」 |
| `image.png` | 通用可读 PNG 附件 |

### locked/ — 不可读 / 无权限（损坏 ZIP 头）

| 文件 | 模拟语义 |
|------|------|
| `data_migration_plan.docx` | 「数据迁移方案」无权限 |
| `supplier_quote.docx` | 「供应商报价单」无权限 |
| `competitor_analysis.xlsx` | 「竞品分析」加密锁定 |
| `supplier_info.xlsx` | 「供应商信息」加密锁定 |
| `dump.bin` (~128KB) | 非标准格式 dump 文件 |
| `reference.zip` | 损坏的 zip（打开提示文件损坏） |

> ⚠️ 这些文件用客户端打开会提示「文件已损坏 / 无法打开」，**这是预期行为**，
> 用于模拟"附件不可读 / 用户无权限"语义。

### confidential/ — 保密附件（文件名前缀带 `[保密]`）

| 文件 | 用途 |
|------|------|
| `[保密] confidential_agreement_v3.pdf` | 保密协议 v3 |
| `[保密] revision_confidential_v3.docx` | 保密修订稿 |
| `[保密] quotation_confidential.pdf` | 保密报价单 |

> 配合 `components/confidential_banner.html` 在正文加保密提示条使用。

## 内联图清单（inline_images/）

> 发送时 `--inline-image PATH:CID`，正文 HTML 用 `<img src="cid:CID">` 引用。

| 文件 | 用途 |
|------|------|
| `architecture.png`       | 产品架构图 |
| `arch_compare.png`       | 架构升级对比图 |
| `risk_label.png`         | 风险等级标签（红色） |
| `gantt.png`              | 甘特图 / 进度图 |
| `monitor.png`            | 监控曲线 |
| `monitor_capacity.png`   | 容量告警截图 |
| `client_screenshot.png`  | 客户端截图 |
| `error_screenshot.png`   | 错误截图 |
| `feature_screenshot.png` | 功能截图 |
| `device_compare.png`     | 设备参数对比截图 |
| `production_line.png`    | 产线照片 |
| `flowchart.png`          | 流程图 |
| `threshold_table.png`    | 阈值对比表截图 |
| `priority_change.png`    | 优先级调整表截图 |
| `chart_industry.png`     | 行业资讯图表 |
| `design_draft.png`       | 设计稿 / 原型 |
| `poster.png`             | 活动海报（竖图） |

## HTML 组件（components/）—— 用法

每个组件是一段可嵌入正文的 HTML 片段，含 `{{占位符}}`。
**使用流程**：

```python
# 1. 读组件
with open("assets/components/approval_card.html", "r", encoding="utf-8") as f:
    card = f.read()
# 2. 替换占位符
card = (card
        .replace("{{TYPE}}", "差旅费报销")
        .replace("{{APPLICANT}}", "张伟（市场部）")
        .replace("{{AMOUNT}}", "¥38,000")
        .replace("{{REASON}}", "深圳客户拜访")
        .replace("{{DEADLINE}}", "明天 18:00")
        .replace("{{STATUS}}", "待我审批")
        .replace("{{STATUS_COLOR}}", "#ff7d00"))
# 3. 拼到 templates/system_notice.html 的 {{BODY}} 里
```

### 组件占位符速查

| 组件 | 占位符 |
|------|--------|
| `signature_wechat.html` | （无） |
| `signature_normal.html` | NAME / TITLE / DEPT / PHONE / EMAIL |
| `approval_card.html` | TYPE / APPLICANT / AMOUNT / REASON / DEADLINE / STATUS / STATUS_COLOR |
| `meeting_invite_card.html` | TITLE / TIME / LOCATION / ORGANIZER / ATTENDEES |
| `meeting_booked_card.html` | TITLE / TIME / LOCATION / HOST |
| `notice_label.html` | TYPE / EFFECTIVE / COLOR |
| `permission_expiry_notice.html` | PERMISSION_NAME / SYSTEM_NAME / EXPIRE_DATE / DAYS_LEFT / RENEW_LINK |
| `large_attachment_link.html` | FILE_NAME / FILE_SIZE / SOURCE_TYPE / LINK_URL / STATUS / STATUS_COLOR / EXPIRE_DATE |
| `alert_card.html` | ALERT_LEVEL / ALERT_COLOR / SERVICE_NAME / ALERT_TITLE / IMPACT / OWNER / START_TIME / DETAIL_LINK |
| `confidential_banner.html` | （无） |
| `forwarded_from_chat.html` | GROUP |
| `translate_banner.html` | （无） |
| `risk_level_badge.html` | LEVEL / COLOR |
| `code_block.html` | CODE（注意 `<>&` 转义） |
| `log_block.html` | LOG |
| `data_table.html` | HEADERS / ROWS |
| `auto_daily_report.html` | DATE / ROWS |
| `thread_quote.html` | QUOTE_SENDER / QUOTE_DATE / QUOTE_CONTENT |
| `subscription_summary.html` | TITLE / SUMMARY / LINKS |

### 颜色色值速查

| 语义 | 色值 |
|------|------|
| 主色（链接/按钮） | `#165dff` |
| 警告 / 待办（黄） | `#ff7d00` |
| 成功（绿） | `#00b42a` |
| 危险 / 高风险（红） | `#f53f3f` |
| 信息（蓝边） | `#5b88d6` |
| 主文字 | `#1d2129` |
| 次文字 | `#4e5969` |
| 弱文字 | `#86909c` |
| 边框 | `#e5e6eb` |
| 卡片背景 | `#f7f8fa` |

## 邮件模板（templates/）—— 用法

模板是「完整邮件正文骨架」，**直接作为 `--body-file` 即可发送**。
模板内的 `{{占位符}}` 通常用来填入具体业务文字 / 嵌入组件 HTML / 内联图标签。

```bash
# 示例：用 boss_request 模板发一封 VP → 你的邮件
python scripts/exmail.py send \
  --to me@example.com \
  --subject "Q3产品路线图确认" \
  --body-file ./assembled_body.html --html \
  --inline-image assets/inline_images/architecture.png:arch1 \
  --from-name "技术VP张磊"
```

`assembled_body.html` 是把 `templates/boss_request.html` 中的占位符替换好后的产物。

## 主题文案池（subjects.yaml）

按类别组织的主题字符串列表，供批量生成第三层邮件时随机/顺序选取。
不需要 PyYAML，可用 stdlib 简单解析（行首 `-` 取条目）。

类别：
- `system_notice` — 纯系统通知
- `approval_done` — 审批完成通知
- `daily_report` — 自动日报
- `scan_report` — 安全扫描
- `announcement` — 全员公告
- `activity` — 活动/邀请
- `subscription` — 订阅推送
- `fyi` — FYI 通用
- `old_misc` — "7 天外"历史邮件填充

## SMTP 协议层无法表达的语义（必须妥协）

下列语义**不在 assets 范围内**——它们要么是客户端行为，要么需要业务系统配合：

| 语义 | 妥协方案 |
|------|---------|
| **DDL 已过期 / 3 天前** | 在正文文字写明「截止：3 天前（已逾期）」 |
| **真实历史时间（7 天外）** | SMTP `Date:` 头可写过去，但服务端展示**收信时刻**；需要"历史邮件"效果时，建议直接发送（不必伪造时间）并在正文标注 |
| **星标联系人** | 收件方手动星标，不可构造 |
| **免提醒** | 客户端规则匹配，不可构造 |
| **真实 EAS 审批卡片** | 用 `approval_card.html` 视觉模拟 |
| **附件无权限** | 用 `locked/*` 损坏文件 + 文件名标记 |
| **线程合并** | 需手动构造 `Message-ID` / `In-Reply-To` / `References` 头（exmail.py send 子命令支持，详见 references/send-from-json.md） |
