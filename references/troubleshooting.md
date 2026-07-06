# 故障排查

## 1. 认证失败（最常见）

### 症状

- `smtplib.SMTPAuthenticationError: (535, b'Login Fail. Please enter your authorization code to login')`
- `imaplib.error: b'[AUTHENTICATIONFAILED] Authentication failed.'`

### 原因 & 处理

| 原因 | 处理 |
|------|------|
| 用了**登录密码**而非客户端专用密码 | 按 [get-client-password.md](get-client-password.md) 重新生成并替换 |
| 管理员**未开启 IMAP/SMTP 服务范围** | 联系管理员在「企业微信管理端 → 协作 → 邮件 → 安全管理 → 客户端访问权限」开启 |
| 客户端专用密码已过期/被撤销 | 网页端重新生成 |
| 用户名拼写错误 | 必须是完整邮箱地址，例如 `name@company.com` |

## 2. 连接超时 / DNS 失败

### 症状

- `TimeoutError: [WinError 10060]`
- `socket.gaierror: [Errno 11001] getaddrinfo failed`

### 处理

1. 确认本机能 ping `imap.exmail.qq.com` / `smtp.exmail.qq.com`
2. 公司网络是否走代理？设置 `HTTPS_PROXY` 不会影响 SMTP/IMAP，需要走代理时只能用支持 SOCKS 隧道（本 skill 默认直连）
3. 部分企业为客户端配置了 **IP 白名单**，问管理员是否需要把当前公网 IP 加入白名单
4. 防火墙是否拦截了 993 / 465 端口

## 3. 中文搜索/主题乱码

### 服务端不支持非 ASCII SEARCH（腾讯企业邮已知行为）

实测 `imap.exmail.qq.com` **不支持** `CHARSET UTF-8` 形式的 SEARCH，会忽略条件返回 ALL。
本 skill 已自动应对：当 `--from` / `--subject` 含中文时，切换为「客户端兜底过滤」
（粗筛后本地匹配，扫描窗口 = `limit × 10`）。

详见 [imap-search.md](imap-search.md#中文非-ascii-关键词)。

### 主题/发件人显示乱码

读邮件时本 skill 已自动调用 `email.header.decode_header` 解码 RFC 2047；
若仍乱码多半是发件方未规范编码，可手工对比 raw bytes 排查。

### Windows 控制台中文 JSON 乱码

脚本启动时已强制把 stdout/stderr 切到 UTF-8。如果仍看到 `��`，请在终端执行：

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

## 4. 文件夹名含空格 / 中文 IMAP 报错

### 症状

```
EXAMINE command error: BAD [b'EXAMINE parameters!']
SELECT command error: BAD ...
```

### 原因 & 处理

腾讯企业邮的发件箱真名是 `Sent Messages`、垃圾箱是 `Junk` 等，含空格的必须用 IMAP
双引号包裹后再发给服务器。本 skill 已在 `_quote_folder()` 中自动处理；外部调用 `ExmailClient.list_inbox(folder=...)` 等 API 也会自动加引号。

如果你直接用 imaplib 操作，请：

```python
m.select('"Sent Messages"')   # ✅ 正确，字符串里要含双引号
m.select('Sent Messages')     # ❌ 错误，会触发 EXAMINE parameters!
```

### 文件夹真实名称参考（exmail）

| 中文显示 | IMAP 真实名 |
|----------|-------------|
| 收件箱 | `INBOX` |
| 已发送 | `Sent Messages` |
| 草稿箱 | `Drafts` |
| 已删除 | `Deleted Messages` |
| 垃圾邮件 | `Junk` |
| 自定义中文文件夹 | `&UXZO1mWHTvZZOQ-` 形式（modified UTF-7） |



## 5. 邮件被反垃圾拦截 / 554 拒收

- `From` 字段务必等于认证用户名（本 skill 已强制）
- 显示名包含敏感词（如 "免费"、"中奖"、"贷款"）会被打分
- 短时大量发件触发反垃圾，使用 `--send-interval`/批量参数降速
- 内容含可疑链接/附件可执行文件（.exe/.bat/.scr）易被拦

## 6. 附件/正文过大

- 单封邮件 ≤ 50MB（base64 后），超出请改用网盘链接
- 大附件下载耗时，CLI 会显示进度提示

## 7. UID 失效

- IMAP UID 在文件夹被「重建」时可能改变（罕见）
- 建议每次操作前用 `inbox` 重新拉取最新 UID
- `modify-date` 命令会产生新 UID，操作完成后原 UID 失效

## 8. IMAP APPEND 失败（modify-date 相关）

- **APPEND 被拒**：邮箱配额已满，清理邮件或联系管理员扩容
- **新 UID 返回 0**：少数服务器不支持 APPENDUID 响应扩展，此时返回的 new_uid 可能为文件夹中最后一封邮件的 UID（近似值）
- **日期格式错误**：仅支持 `YYYY-MM-DD HH:MM:SS` 或 `YYYY-MM-DD`，时区格式为 `+0800` / `-0500` 等
- **修改后邮件状态变化**：APPEND 默认标记为 `\Seen`，如需未读状态需手动调用 `flag --unseen`
