# 腾讯企业邮箱协议参考

## 服务器与端口

| 协议 | 服务器 | 端口 | 加密 |
|------|--------|------|------|
| IMAP | `imap.exmail.qq.com` | 993 | SSL/TLS |
| SMTP | `smtp.exmail.qq.com` | 465 | SSL/TLS |
| POP3 | `pop.exmail.qq.com` | 995 | SSL/TLS（本 skill 不用） |

> 不使用 POP3：POP3 仅能下载，无法管理状态/文件夹。

## 认证

- **不支持 OAuth2**
- 支持两种密码：
  1. 普通登录密码（仅在管理员未强制安全登录时可用，已极少见）
  2. **客户端专用密码（推荐 / 通常必需）** — 在企业邮箱网页端「设置 → 微信绑定 → 安全登录」生成

## 管理员前置开关

企业微信管理端 → 协作 → 邮件 → 安全管理 → 客户端访问权限：
- 开启 IMAP/SMTP 服务范围

## 邮件地址形式

- 自定义企业域名：`name@yourcompany.com`
- 企业邮箱通用域：`name@exmail.qq.com`

两种地址均使用同一组 IMAP/SMTP 服务器。

## 限制与注意

| 限制 | 说明 |
|------|------|
| IP 白名单 | 部分企业可能配置了客户端 IP 白名单，未在白名单内会被拒 |
| 频率限制 | 大量轮询/发送可能触发限流 |
| 单封大小 | 一般限制 50MB（含附件 base64 后大小） |
| 收件人数量 | 单次发送一般不超过 100 人 |

## 参考链接

- [POP/IMAP 协议设置帮助](https://open.work.weixin.qq.com/help2/pc/19886)
- [客户端专用密码获取](https://open.work.weixin.qq.com/help2/pc/19902)
- [企业微信邮件 API 概述（备用方案，本 skill 不使用）](https://developer.work.weixin.qq.com/document/path/95486)
