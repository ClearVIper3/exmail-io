# 内置测试账号

本文件登记本 skill 端到端联调 / 调试用的腾讯企业邮箱测试账号。

> ⚠️ 仅供测试使用。生产场景通过 `--username` / `--password` 传入用户自己的凭证，**不要**把这些密码写到生产系统里。
> 🔒 公开版已移除所有明文客户端专用密码与企业内测账号；下文仅保留结构示意，密码一律以占位符表示。

## 账号列表（结构示意，密码已脱敏）

| 标识 | 邮箱 | 客户端专用密码 | 说明 |
|------|------|----------------|------|
| 主测试号 | `主测试号@example-test.site` | `<CLIENT_APP_PASSWORD>` | 默认账号；多数收件 / 状态管理用例的主体 |
| 开发组成员 A | `dev-a@example-test.site` | `<CLIENT_APP_PASSWORD>` | 开发组成员，用于多方收发场景 |
| 开发组成员 B | `dev-b@example-test.site` | `<CLIENT_APP_PASSWORD>` | 开发组成员，用于多方收发场景 |
| 测试组成员 A | `qa-a@example-test.site` | `<CLIENT_APP_PASSWORD>` | 测试组成员，用于多方收发场景 |
| 产品部成员 A | `pm-a@example-test.site` | `<CLIENT_APP_PASSWORD>` | 产品部成员，用于跨部门协作场景 |
| 财务部成员 A | `fin-a@example-test.site` | `<CLIENT_APP_PASSWORD>` | 财务部成员，用于跨部门协作场景 |
| 管理层成员 A | `mgr-a@example-test.site` | `<CLIENT_APP_PASSWORD>` | 管理层成员，用于审批 / 汇报类场景 |
| 人事部成员 A | `hr-a@example-test.site` | `<CLIENT_APP_PASSWORD>` | 人事部成员，用于通知 / 招聘类场景 |

> 真实联调用例请使用你自己的腾讯企业邮箱账号，按 `references/get-client-password.md` 生成客户端专用密码后，通过 `--username` / `--password` 传入。

### 企业内测账号（已移除）

原 `yxznit.cn` 域的 40 余个企业内测账号（含真实姓名与职位）**已在公开版中移除**，以避免泄露真实人员信息与可用凭证。

> 密码均为腾讯企业邮箱「客户端专用密码」（非网页登录密码），可直接用于 IMAP / SMTP 登录。
> 服务器配置已固定为 `imap.exmail.qq.com:993` / `smtp.exmail.qq.com:465`，无需额外提供。

### ⚠️ 同名账号消歧

表中存在多组同名不同部门的账号，**当用户只说名字不带部门前缀时，agent 必须先反问归属，再选账号，禁止凭猜测使用**：

| 名字 | 候选账号 |
|------|----------|
| 李四 | 开发组李四 (`dev-b@example-test.site`) / 财务部李四 (`fin-a@example-test.site`) |
| 周杰 | 测试组周杰 (`qa-b@example-test.site`) / 产品部周杰 (`pm-b@example-test.site`) |

示例：用户说"用李四的账号给王芳发封邮件"，agent 应回："李四有开发组和财务部两位，要用哪一位？"

如果用户给出的信息已经足够区分（如"开发的李四"、"财务李四"、"dev-b@..."、"产品周杰"），则可直接选用，不必再问。

## Agent 使用方式

当任务涉及"用主测试号 / 测试账号收发邮件"时，agent 直接读取用户提供的邮箱地址和客户端专用密码，通过 `--username` / `--password` 传给 `scripts/exmail.py`，无需追问用户：

```bash
# 主测试号查收件箱
python scripts/exmail.py \
  --username 主测试号@example-test.site --password <CLIENT_APP_PASSWORD> \
  inbox --limit 10

# 成员 A 给主测试号发邮件
python scripts/exmail.py \
  --username dev-a@example-test.site --password <CLIENT_APP_PASSWORD> \
  send --to 主测试号@example-test.site --subject "测试" --body "hello"
```

## 维护

新增 / 替换测试账号时，直接编辑本文件的"账号列表"表格即可，**不需要改动 `scripts/exmail.py`**。
