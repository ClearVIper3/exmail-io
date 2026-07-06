# Exmail I/O

腾讯企业邮箱（企业微信邮箱）收发邮件技能，基于 IMAP + SMTP 公有协议实现。`io` 取自 Input/Output，对应收件（IMAP in）+ 发件（SMTP out）的双向能力。

## 这个 Skill 是什么

这是一个供 AI Agent 使用的"技能包"。当用户让 Agent 帮忙收发企业邮箱邮件时，Agent 会加载本 skill 中的指令和脚本来完成任务。

**人类不需要手动执行里面的命令**——你只需要：
1. 确保有客户端专用密码（见下方"凭证"部分）
2. 把密码配置好（环境变量或配置文件）
3. 然后用自然语言告诉 Agent 你想做什么就行

## 核心概念

### 客户端专用密码

腾讯企业邮箱**不支持 OAuth2**，第三方客户端必须用「客户端专用密码」登录（不是你平时的网页登录密码）。

获取方式：登录 https://exmail.qq.com → 设置 → 微信绑定 → 安全登录 → 生成客户端专用密码（16 位）

详见 [references/get-client-password.md](references/get-client-password.md)

### 凭证传递

Agent 通过 CLI 参数 `--username` / `--password` 将凭证传给脚本。凭证来源于用户告知或 `references/test-accounts.md` 中登记的测试账号——你只需确保有客户端专用密码即可。

### 前置条件

企业管理员需开启 IMAP/SMTP 服务：**企业微信管理端 → 协作 → 邮件 → 安全管理 → 客户端访问权限**。

## 能力范围

- **收件**：列出/搜索邮件、读取全文、下载附件、标记已读、移动/删除
- **发件**：纯文本/HTML/附件/内联图片/抄送密送/回复/线程合并
- **修改邮件日期**：篡改已有邮件的 Date 头（用于测试场景）
- **中文搜索**：自动绕过腾讯企业邮 IMAP SEARCH 的已知 bug，走客户端兜底过滤
- **模板拼装**：用预置模板 + 组件快速构造复杂 HTML 邮件（用于 E2E 评测）

## 目录结构

```
exmail-io/
├── SKILL.md                  # Agent 读的完整操作手册（SOP + 命令参考）
├── README.md                 # 你正在看的文件
│
├── scripts/
│   ├── exmail.py             # 核心脚本（CLI + Python 库，~1600 行）
│   └── render_email.py       # 邮件正文模板拼装工具
│
├── assets/                   # 测试素材库
│   ├── index.md              # 素材导航（模板/组件/附件/图片清单）
│   ├── subjects.yaml         # 主题文案池
│   ├── attachments/          # 通用测试附件
│   ├── inline_images/        # 内联图片素材
│   ├── components/           # HTML 片段（审批卡/告警/通知/签名等）
│   └── templates/            # 完整邮件骨架模板
│
└── references/               # 参考文档
    ├── exmail-protocol.md    # 服务器/端口/认证协议
    ├── get-client-password.md # 客户端专用密码获取步骤
    ├── imap-search.md        # IMAP 搜索语法 & 中文兜底机制
    ├── send-from-json.md     # 复杂邮件 JSON 描述格式
    ├── test-accounts.md      # 内置联调测试账号
    └── troubleshooting.md    # 故障排查
```

## 运行环境

- Python 3.8+，**无需 pip install 任何包**（仅用标准库）
- 跨平台：Windows / macOS / Linux

## 常见问题

| 问题 | 原因 & 解决 |
|------|------------|
| 登录失败 | 用了网页登录密码，需改用客户端专用密码 |
| 连接超时 | 网络/代理问题，或管理员未开启 IMAP/SMTP |
| 搜索结果不对 | 腾讯企业邮 SEARCH 有 bug，Agent 会自动用客户端兜底方式处理 |

更多见 [references/troubleshooting.md](references/troubleshooting.md)
