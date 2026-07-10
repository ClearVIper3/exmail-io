# 预配置账号

本文件登记常用的腾讯企业邮箱账号，便于多账号收发场景直接选用。

> 账号与密码均通过 `--username` / `--password` 传入 `scripts/exmail.py`，不会被写入代码或日志。

## 账号列表（示例）

| 标识 | 姓名（示例） | 邮箱 | 客户端专用密码 | 说明 |
|------|------|------|----------------|------|
| 主账号 | 张三 | `main@example-test.site` | `<你的客户端专用密码>` | 默认账号；多数收件 / 状态管理操作的主体 |
| 开发组成员 A | 王五 | `dev-a@example-test.site` | `<你的客户端专用密码>` | 开发组成员，用于多方收发 |
| 开发组成员 B | 李四 | `dev-b@example-test.site` | `<你的客户端专用密码>` | 开发组成员，用于多方收发 |
| 测试组成员 A | 赵六 | `qa-a@example-test.site` | `<你的客户端专用密码>` | 测试组成员，用于多方收发 |
| 测试组成员 B | 周杰 | `qa-b@example-test.site` | `<你的客户端专用密码>` | 测试组成员，用于多方收发 |
| 产品部成员 A | 孙七 | `pm-a@example-test.site` | `<你的客户端专用密码>` | 产品部成员，用于跨部门协作 |
| 产品部成员 B | 周杰 | `pm-b@example-test.site` | `<你的客户端专用密码>` | 产品部成员，用于跨部门协作 |
| 财务部成员 A | 李四 | `fin-a@example-test.site` | `<你的客户端专用密码>` | 财务部成员，用于跨部门协作 |
| 管理层成员 A | 钱经理 | `mgr-a@example-test.site` | `<你的客户端专用密码>` | 管理层成员，用于审批 / 汇报 |
| 人事部成员 A | 吴助理 | `hr-a@example-test.site` | `<你的客户端专用密码>` | 人事部成员，用于通知 / 招聘 |

> 上表的 `example-test.site` 为示例域名、姓名亦为占位示例；实际使用时请替换为你的腾讯企业邮箱账号与真实姓名，按 `references/get-client-password.md` 生成客户端专用密码后填入。**下方「同名账号消歧」中的 李四 / 周杰 即对应此表中的重名行**。

### 服务器配置

> IMAP / SMTP 服务器已固定为 `imap.exmail.qq.com:993` / `smtp.exmail.qq.com:465`，使用「客户端专用密码」登录（非网页登录密码），无需额外提供。

### ⚠️ 同名账号消歧

表中存在多组同名不同部门的账号，**当用户只说名字不带部门前缀时，agent 必须先反问归属，再选账号，禁止凭猜测使用**：

| 名字 | 候选账号 |
|------|----------|
| 李四 | 开发组李四 (`dev-b@example-test.site`) / 财务部李四 (`fin-a@example-test.site`) |
| 周杰 | 测试组周杰 (`qa-b@example-test.site`) / 产品部周杰 (`pm-b@example-test.site`) |

示例：用户说"用李四的账号给王芳发封邮件"，agent 应回："李四有开发组和财务部两位，要用哪一位？"

如果用户给出的信息已经足够区分（如"开发的李四"、"财务李四"、"dev-b@..."、"产品周杰"），则可直接选用，不必再问。

## Agent 使用方式

当任务涉及"用某个已登记账号收发邮件"时，agent 直接读取用户提供的邮箱地址和客户端专用密码，通过 `--username` / `--password` 传给 `scripts/exmail.py`，无需追问用户：

```bash
# 主账号查收件箱
python scripts/exmail.py \
  --username main@example-test.site --password <你的客户端专用密码> \
  inbox --limit 10

# 成员 A 给主账号发邮件
python scripts/exmail.py \
  --username dev-a@example-test.site --password <你的客户端专用密码> \
  send --to main@example-test.site --subject "同步" --body "hello"
```

## 维护

新增 / 替换账号凭证时，直接编辑本文件的"账号列表"表格即可，**不需要改动 `scripts/exmail.py`**。
