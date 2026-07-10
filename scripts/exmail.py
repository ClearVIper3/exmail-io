#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exmail.py — 腾讯企业邮箱（exmail.qq.com）IMAP+SMTP 一体客户端

仅依赖 Python 3.8+ 标准库。

用法（CLI）：
    python exmail.py inbox    [--unread] [--from ADDR] [--subject S] [--body KW]
                              [--since DATE] [--before DATE] [--limit N]
                              [--folder INBOX] [--raw-search 'IMAP_SEARCH_STRING']
                              [--output FILE]
    python exmail.py folders                                  # 列出所有文件夹
    python exmail.py read     --uid UID [--folder INBOX] [--mark-seen]
                              [--save-attachments DIR] [--no-html]
                              [--body-lines N] [--output FILE]
    python exmail.py flag     --uid UID [--seen|--unseen|--flagged|--unflagged]
    python exmail.py move     --uid UID --to FOLDER
    python exmail.py delete   --uid UID
    python exmail.py send     --to A,B [--cc C] [--bcc D] --subject S
                              (--body TEXT | --body-file FILE) [--html]
                              [--attach FILE]... [--inline-image PATH:CID]...
                              [--from-name NAME]
                              [--in-reply-to MSGID] [--references "ID1 ID2..."]
                              [--header "Name:Value"]...
                              [--from-json FILE] [--send-interval SEC]
    python exmail.py reply    --uid UID --body TEXT [--include-quote]
    python exmail.py modify-date --uid UID --new-date "YYYY-MM-DD HH:MM:SS"
                              [--folder INBOX] [--timezone +0800]
                              [--keep-original]

用法（Python 库）：
    from exmail import ExmailClient
    cli = ExmailClient(username=..., password=...)
    cli.list_inbox(unread_only=True, limit=10)
    cli.read(uid=123, mark_seen=True, save_attachments_to="./att")
    cli.send(to=["a@x.com"], subject="hi", body="hello")
"""
from __future__ import annotations

import argparse
import json
import re
import smtplib
import ssl
import sys
import tempfile
import time
import email
import email.utils
import imaplib
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from email import encoders
from email.header import Header, decode_header, make_header
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr
import mimetypes
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# ---------- 默认服务器配置（可由配置文件覆盖） ----------
DEFAULT_IMAP_HOST = "imap.exmail.qq.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_HOST = "smtp.exmail.qq.com"
DEFAULT_SMTP_PORT = 465




# =====================================================================
# 工具函数
# =====================================================================

def _decode_mime_header(raw: Optional[str]) -> str:
    """解码邮件头中的 RFC 2047 编码字符串。"""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _split_addresses(value: Union[str, Sequence[str], None]) -> List[str]:
    """统一处理邮件地址输入：字符串(支持逗号/分号分隔)或列表。"""
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;]+", value)
    else:
        parts = list(value)
    return [p.strip() for p in parts if p and p.strip()]


def _resolve_credentials(
    cli_username: Optional[str],
    cli_password: Optional[str],
) -> Tuple[str, str]:
    """解析凭证：必须通过 CLI --username / --password 提供。"""
    if not cli_username or not cli_password:
        raise SystemExit(
            "凭证缺失。请从 references/test-accounts.md 读取预配置的账号凭证，"
            "或询问用户获取邮箱地址与客户端专用密码，"
            "然后通过 --username / --password 传入。"
        )
    return cli_username, cli_password


def _format_imap_date(s: str) -> str:
    """允许用户传入 'YYYY-MM-DD' 或原生 'DD-Mon-YYYY'，统一转换为 IMAP 的 DD-Mon-YYYY。"""
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if not m:
        return s  # 假定用户已传 IMAP 日期格式
    y, mo, d = m.groups()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{int(d):02d}-{months[int(mo) - 1]}-{y}"


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _escape_imap_astring(value: str) -> str:
    """转义 IMAP quoted-string 中的反斜杠与双引号（RFC 3501 §9 quoted）。

    用于把用户输入安全地嵌进 `FROM "..."` 等 SEARCH 条件里。裸拼接时，
    形如 `a"b` 的地址会破坏 IMAP 语法（`FROM "a"b"`），导致 SEARCH 报错。
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _quote_folder(name: str) -> str:
    """IMAP 文件夹名包含空格/特殊字符时必须用双引号包裹。

    imaplib.IMAP4.select() 不会自动加引号，传 `Sent Messages` 会被解析为
    `EXAMINE Sent Messages` → 服务器报 `EXAMINE parameters!`。
    """
    if not name:
        return '""'
    # 已经被引号包裹则原样返回
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        return name
    # 含 ASCII 安全的字母数字、下划线、INBOX 这类裸名直接返回
    if re.match(r"^[A-Za-z0-9_./\-]+$", name):
        return name
    # 其余加引号，转义内部双引号和反斜杠
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _imap_search_utf8(m: imaplib.IMAP4_SSL,
                      criteria: Sequence[str]) -> Tuple[str, Any]:
    """发送 UTF-8 字节的 SEARCH，**不带 CHARSET**。

    腾讯企业邮（exmail.qq.com）对 `SEARCH CHARSET UTF-8 ...` 一概返回
    ALL（已知服务端 bug），但对裸 UTF-8 字节字面量能正确按字节匹配。
    实现：临时把 connection._encoding 改为 utf-8，让 imaplib 用 UTF-8 编码。"""
    old_enc = getattr(m, "_encoding", "ascii")
    try:
        m._encoding = "utf-8"
        return m.search(None, *criteria)
    finally:
        m._encoding = old_enc


def _imap_search_raw(m: imaplib.IMAP4_SSL, charset: Optional[str],
                     raw: str) -> Tuple[str, Any]:
    """执行用户提供的原生 SEARCH 字符串。

    若 charset=UTF-8 且服务器是 exmail，会自动剥离 CHARSET 走 UTF-8 字节路径。"""
    if charset and charset.upper().replace("-", "") == "UTF8":
        return _imap_search_utf8(m, [raw])
    if _is_ascii(raw) and not charset:
        return m.search(None, raw)
    if charset:
        # 其他 charset：尝试原始路径
        return m.search(charset, raw)
    return _imap_search_utf8(m, [raw])


def _extract_nonascii_terms(raw_search: str) -> Dict[str, List[str]]:
    """从 raw-search 字符串中提取 FROM/SUBJECT/BODY/TEXT 后跟的非 ASCII 字面量。

    腾讯企业邮 IMAP 对非 ASCII SEARCH 一律返回 ALL，所以即使用户走 raw-search
    带了中文字面量，服务端结果也不可信。把这些字段提取出来做客户端兜底过滤。

    返回 {"from": [...], "subject": [...], "body": [...]}（body 包含 TEXT）。
    """
    fields = {"FROM": "from", "SUBJECT": "subject",
              "BODY": "body", "TEXT": "body"}
    out: Dict[str, List[str]] = {"from": [], "subject": [], "body": []}
    # 匹配 FIELD "..."，注意要兼容中英文混合
    pattern = re.compile(
        r'\b(FROM|SUBJECT|BODY|TEXT)\s+"([^"]*)"',
        re.IGNORECASE,
    )
    for kw, val in pattern.findall(raw_search):
        if val and not _is_ascii(val):
            out[fields[kw.upper()]].append(val)
    return out


def _imap_utf7_decode(name: bytes) -> str:
    """解码 IMAP modified UTF-7（RFC 3501 §5.1.3）邮箱名为 Python str。

    与标准 UTF-7 的差异：
      * shift 字符是 `&` 而不是 `+`
      * `&-` 表示字面 `&`
      * 内部用 base64 但用 `,` 替换 `/`
    腾讯企业邮中文文件夹返回类似 `&UXZO1mWHTvZZOQ-` 的形式，需要这个解码。
    """
    if not name:
        return ""
    out: List[str] = []
    i = 0
    while i < len(name):
        c = name[i:i + 1]
        if c == b"&":
            j = name.find(b"-", i + 1)
            if j == -1:
                # 异常输入，按字节解
                out.append(name[i:].decode("utf-8", "replace"))
                break
            seg = name[i + 1:j]
            if seg == b"":
                out.append("&")  # &- → &
            else:
                # IMAP modified UTF-7：base64 用 , 替代 /
                b64 = seg.replace(b",", b"/")
                # 补齐 base64 padding
                pad = (-len(b64)) % 4
                b64 = b64 + b"=" * pad
                import base64
                try:
                    decoded = base64.b64decode(b64).decode("utf-16-be")
                except Exception:
                    decoded = name[i:j + 1].decode("utf-8", "replace")
                out.append(decoded)
            i = j + 1
        else:
            out.append(c.decode("ascii", "replace"))
            i += 1
    return "".join(out)









# =====================================================================
# 客户端核心
# =====================================================================

@dataclass
class ExmailClient:
    username: str
    password: str
    from_name: Optional[str] = None
    imap_host: str = DEFAULT_IMAP_HOST
    imap_port: int = DEFAULT_IMAP_PORT
    smtp_host: str = DEFAULT_SMTP_HOST
    smtp_port: int = DEFAULT_SMTP_PORT
    timeout: int = 30

    # ---------- IMAP ----------

    def _imap_connect(self) -> imaplib.IMAP4_SSL:
        ctx = ssl.create_default_context()
        try:
            m = imaplib.IMAP4_SSL(self.imap_host, self.imap_port,
                                  ssl_context=ctx, timeout=self.timeout)
        except TypeError:
            # 老版本 Python 的 IMAP4_SSL 不支持 timeout 参数
            m = imaplib.IMAP4_SSL(self.imap_host, self.imap_port,
                                  ssl_context=ctx)
        m.login(self.username, self.password)
        return m

    def list_inbox(
        self,
        folder: str = "INBOX",
        unread_only: bool = False,
        from_addr: Optional[str] = None,
        subject: Optional[str] = None,
        body_kw: Optional[str] = None,
        since: Optional[str] = None,
        before: Optional[str] = None,
        raw_search: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """列出邮件元信息（不含正文）。返回按时间倒序的列表。

        subject / body_kw：腾讯企业邮服务端的 SUBJECT/BODY SEARCH 即使是 ASCII
        关键词也不作准确子串匹配（实测会返回不包含关键词的邮件），统一走
        客户端兜底：服务端用其它条件粗筛，本地拉取 header / body 后做大小写不
        敏感子串匹配。建议配合 since / from_addr 缩小范围，避免扫全邮箱。
        from_addr 的 ASCII 分支仍走服务端 FROM（实测可靠）。
        """
        m = self._imap_connect()
        try:
            typ, _ = m.select(_quote_folder(folder), readonly=True)
            if typ != "OK":
                raise RuntimeError(f"选择文件夹 {folder} 失败")

            # 拼接 SEARCH 条件
            client_filter_from: Optional[str] = None
            client_filter_subject: Optional[str] = None
            client_filter_body: Optional[str] = None
            scan_factor = 1  # 客户端过滤时扩大服务端扫描窗口
            if raw_search:
                # 用户给了原生语句；CHARSET 需要单独传给 search()
                charset = None
                rs = raw_search.strip()
                cm = re.match(r"^CHARSET\s+(\S+)\s+(.+)$", rs, re.IGNORECASE)
                if cm:
                    charset = cm.group(1)
                    rs = cm.group(2)
                # 腾讯企业邮对 raw-search 中的非 ASCII 字面量也不能正确匹配，
                # 抽取出来做客户端兜底
                nonascii = _extract_nonascii_terms(rs)
                if nonascii["from"]:
                    client_filter_from = nonascii["from"][0]
                if nonascii["subject"]:
                    client_filter_subject = nonascii["subject"][0]
                if nonascii["body"]:
                    client_filter_body = nonascii["body"][0]
                if any(nonascii.values()):
                    scan_factor = max(scan_factor, 10)
                typ, data = _imap_search_raw(m, charset, rs)
            else:
                criteria: List[str] = []
                if unread_only:
                    criteria.append("UNSEEN")
                # FROM：ASCII 走服务端，非 ASCII 走客户端兜底
                # （腾讯企业邮 IMAP 不支持非 ASCII SEARCH，会忽略条件返回 ALL）
                if from_addr:
                    if _is_ascii(from_addr):
                        criteria.append(f'FROM "{_escape_imap_astring(from_addr)}"')
                    else:
                        client_filter_from = from_addr
                        scan_factor = max(scan_factor, 10)
                if subject:
                    # 腾讯企业邮的 SUBJECT SEARCH 即使是 ASCII 也不精确（会返回
                    # 不包含关键词的邮件），统一走客户端兜底。
                    client_filter_subject = subject
                    scan_factor = max(scan_factor, 10)
                if body_kw:
                    # 同 SUBJECT，BODY SEARCH 也不精确，统一走客户端兜底。
                    client_filter_body = body_kw
                    scan_factor = max(scan_factor, 10)
                if since:
                    criteria.append(f"SINCE {_format_imap_date(since)}")
                if before:
                    criteria.append(f"BEFORE {_format_imap_date(before)}")
                if not criteria:
                    criteria.append("ALL")
                typ, data = m.search(None, *criteria)

            if typ != "OK":
                raise RuntimeError(f"IMAP SEARCH 失败：{data}")

            all_ids = data[0].split()
            # 客户端过滤场景：扩大扫描窗口，倒序遍历直到收满 limit 或扫尽
            need_client_filter = (
                client_filter_from
                or client_filter_subject
                or client_filter_body
            )
            if need_client_filter:
                # 最多扫 limit*scan_factor 封最新邮件做客户端匹配
                ids = all_ids[-(limit * scan_factor):][::-1]
            else:
                ids = all_ids[-limit:][::-1] if limit else all_ids[::-1]

            results: List[Dict[str, Any]] = []
            for num in ids:
                # 用 UID 而非序号；先 FETCH UID + ENVELOPE + FLAGS + RFC822.SIZE
                typ, resp = m.fetch(num, "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER])")
                if typ != "OK" or not resp or resp[0] is None:
                    continue
                meta_line, header_blob = resp[0]
                meta_str = meta_line.decode("utf-8", errors="replace")
                uid_match = re.search(r"UID (\d+)", meta_str)
                size_match = re.search(r"RFC822\.SIZE (\d+)", meta_str)
                flags_match = re.search(r"FLAGS \(([^)]*)\)", meta_str)
                flags = flags_match.group(1).split() if flags_match else []

                msg = email.message_from_bytes(header_blob)
                from_dec = _decode_mime_header(msg.get("From", ""))
                subject_dec = _decode_mime_header(msg.get("Subject", ""))

                # 客户端兜底过滤（针对 exmail 不支持非 ASCII SEARCH 的情况）
                if client_filter_from and \
                        client_filter_from.lower() not in from_dec.lower():
                    continue
                if client_filter_subject and \
                        client_filter_subject.lower() not in subject_dec.lower():
                    continue
                # 正文兜底：只在确实需要时拉取整封正文（开销大）
                if client_filter_body:
                    uid_for_body = uid_match.group(1) if uid_match else None
                    if not uid_for_body:
                        continue
                    typ_b, data_b = m.uid("FETCH", uid_for_body, "(BODY.PEEK[])")
                    if typ_b != "OK" or not data_b or data_b[0] is None:
                        continue
                    full = email.message_from_bytes(data_b[0][1])
                    body_text, body_html, _ = _walk_message(full, save_to=None)
                    haystack = (body_text + "\n" + body_html).lower()
                    if client_filter_body.lower() not in haystack:
                        continue

                results.append({
                    "uid": int(uid_match.group(1)) if uid_match else None,
                    "from": from_dec,
                    "to": _decode_mime_header(msg.get("To", "")),
                    "subject": subject_dec,
                    "date": msg.get("Date", ""),
                    "size": int(size_match.group(1)) if size_match else 0,
                    "unread": "\\Seen" not in flags,
                    "flagged": "\\Flagged" in flags,
                    "has_attachment": _looks_like_has_attachment(msg),
                })
                if limit and len(results) >= limit:
                    break
            return results
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def list_folders(self) -> List[Dict[str, Any]]:
        """列出邮箱所有文件夹。返回每项含 name / flags / delimiter。

        典型输出（腾讯企业邮）：
            INBOX, Sent Messages, Drafts, Deleted Messages, Junk
        """
        m = self._imap_connect()
        try:
            typ, data = m.list()
            if typ != "OK":
                raise RuntimeError(f"LIST 失败：{data}")
            results: List[Dict[str, Any]] = []
            # 服务端返回类似：(\HasNoChildren) "/" "INBOX"
            line_re = re.compile(
                rb'^\((?P<flags>[^)]*)\)\s+'
                rb'"(?P<delim>[^"]*)"\s+'
                rb'(?P<name>(?:"[^"]*"|\S+))\s*$'
            )
            for raw in data or []:
                if raw is None:
                    continue
                if isinstance(raw, tuple):
                    raw = b" ".join(p for p in raw if p)
                mt = line_re.match(raw)
                if not mt:
                    continue
                flags = mt.group("flags").decode("utf-8", "replace").split()
                delim = mt.group("delim").decode("utf-8", "replace")
                name_b = mt.group("name")
                if name_b.startswith(b'"') and name_b.endswith(b'"'):
                    name_b = name_b[1:-1]
                # IMAP 文件夹名走的是 modified UTF-7（RFC 3501 §5.1.3），
                # 中文文件夹会被编为 `&XXX-` 的形式，需要专门解码
                try:
                    name = _imap_utf7_decode(name_b)
                except Exception:
                    name = name_b.decode("utf-8", "replace")
                results.append({
                    "name": name,
                    "raw_name": name_b.decode("utf-8", "replace"),
                    "flags": flags,
                    "delimiter": delim,
                })
            return results
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def read(
        self,
        uid: int,
        folder: str = "INBOX",
        mark_seen: bool = False,
        save_attachments_to: Optional[str] = None,
        save_eml_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """读取单封邮件全文。

        参数：
            save_eml_to: 将原始邮件保存为 .eml 文件。
                - 如果是目录路径：文件命名为 {uid}_{subject_safe}.eml
                - 如果是文件路径：直接保存到该路径
        """
        m = self._imap_connect()
        try:
            # 想标记已读就用读写模式
            typ, _ = m.select(_quote_folder(folder), readonly=not mark_seen)
            if typ != "OK":
                raise RuntimeError(f"选择文件夹 {folder} 失败")

            fetch_item = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
            typ, data = m.uid("FETCH", str(uid), fetch_item)
            if typ != "OK" or not data or data[0] is None:
                raise RuntimeError(f"未找到 UID={uid} 的邮件")

            raw_bytes = data[0][1]
            msg = email.message_from_bytes(raw_bytes)

            # 保存 .eml 文件
            eml_saved_path = None
            if save_eml_to:
                save_path = Path(save_eml_to)
                if save_path.is_dir() or (not save_path.suffix and not save_path.exists()):
                    # 当作目录处理
                    save_path.mkdir(parents=True, exist_ok=True)
                    subject_safe = re.sub(
                        r'[<>:"/\\|?*\x00-\x1f]', '_',
                        _decode_mime_header(msg.get("Subject", "no_subject"))
                    )[:50]
                    eml_filename = f"{uid}_{subject_safe}.eml"
                    eml_saved_path = str(save_path / eml_filename)
                else:
                    # 当作文件路径处理
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    eml_saved_path = str(save_path)
                Path(eml_saved_path).write_bytes(raw_bytes)

            body_text, body_html, attachments_meta = _walk_message(
                msg, save_to=save_attachments_to
            )

            result = {
                "uid": uid,
                "from": _decode_mime_header(msg.get("From", "")),
                "to": _decode_mime_header(msg.get("To", "")),
                "cc": _decode_mime_header(msg.get("Cc", "")),
                "subject": _decode_mime_header(msg.get("Subject", "")),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "in_reply_to": msg.get("In-Reply-To", ""),
                "references": msg.get("References", ""),
                "body_text": body_text,
                "body_html": body_html,
                "attachments": attachments_meta,
            }
            if eml_saved_path:
                result["eml_path"] = eml_saved_path
            return result
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def flag(self, uid: int, folder: str = "INBOX",
             seen: Optional[bool] = None,
             flagged: Optional[bool] = None) -> None:
        """标记邮件已读/未读/加星/取消加星。"""
        m = self._imap_connect()
        try:
            typ, _ = m.select(_quote_folder(folder))
            if typ != "OK":
                raise RuntimeError(f"选择文件夹 {folder} 失败")
            ops: List[Tuple[str, str]] = []
            if seen is True:
                ops.append(("+FLAGS", "\\Seen"))
            elif seen is False:
                ops.append(("-FLAGS", "\\Seen"))
            if flagged is True:
                ops.append(("+FLAGS", "\\Flagged"))
            elif flagged is False:
                ops.append(("-FLAGS", "\\Flagged"))
            for op, flag in ops:
                typ, data = m.uid("STORE", str(uid), op, flag)
                if typ != "OK":
                    raise RuntimeError(f"STORE {op} {flag} 失败：{data}")
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def move(self, uid: int, dest_folder: str, src_folder: str = "INBOX") -> None:
        """将邮件移动到目标文件夹。优先使用 MOVE 指令，否则回退 COPY+EXPUNGE。"""
        m = self._imap_connect()
        try:
            typ, _ = m.select(_quote_folder(src_folder))
            if typ != "OK":
                raise RuntimeError(f"选择文件夹 {src_folder} 失败")
            quoted_dest = _quote_folder(dest_folder)
            try:
                typ, data = m.uid("MOVE", str(uid), quoted_dest)
                if typ == "OK":
                    return
            except imaplib.IMAP4.error:
                pass
            # 回退：COPY + 标记已删除 + EXPUNGE
            typ, data = m.uid("COPY", str(uid), quoted_dest)
            if typ != "OK":
                raise RuntimeError(f"COPY 到 {dest_folder} 失败：{data}")
            m.uid("STORE", str(uid), "+FLAGS", "\\Deleted")
            m.expunge()
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def delete(self, uid: int, folder: str = "INBOX") -> None:
        """删除邮件（标记 Deleted 并 EXPUNGE）。"""
        m = self._imap_connect()
        try:
            typ, _ = m.select(_quote_folder(folder))
            if typ != "OK":
                raise RuntimeError(f"选择文件夹 {folder} 失败")
            typ, data = m.uid("STORE", str(uid), "+FLAGS", "\\Deleted")
            if typ != "OK":
                raise RuntimeError(f"标记删除失败：{data}")
            m.expunge()
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def append(
        self,
        folder: str,
        raw_email: Union[bytes, str],
        flags: Optional[List[str]] = None,
        date: Optional[datetime] = None,
    ) -> int:
        """通过 IMAP APPEND 将原始邮件存入指定文件夹。

        参数：
            folder: 目标文件夹名
            raw_email: 原始邮件内容（bytes 或 str）
            flags: 可选标志列表，如 ["\\Seen", "\\Flagged"]
            date: 可选内部日期（datetime 对象）

        返回：新邮件的 UID
        """
        if isinstance(raw_email, str):
            raw_email = raw_email.encode("utf-8")

        flag_str = None
        if flags:
            flag_str = "(" + " ".join(flags) + ")"

        # imaplib.append 的 date_time 参数需要 imaplib.Time2Internaldate 格式
        date_time = None
        if date:
            date_time = imaplib.Time2Internaldate(date.timetuple())

        m = self._imap_connect()
        try:
            typ, data = m.append(
                _quote_folder(folder),
                flag_str,
                date_time,
                raw_email,
            )
            if typ != "OK":
                raise RuntimeError(
                    f"APPEND 到文件夹 {folder} 失败：{data}")

            # 尝试从 APPEND 响应中解析新 UID
            # 典型响应: [b'[APPENDUID 1 12345] (Success)']
            new_uid = 0
            if data and data[0]:
                resp = data[0] if isinstance(data[0], str) else data[0].decode(
                    "utf-8", errors="replace")
                uid_match = re.search(r'\[APPENDUID\s+\d+\s+(\d+)\]', resp)
                if uid_match:
                    new_uid = int(uid_match.group(1))

            # 如果无法从响应中获取 UID，搜索最近的邮件获取
            if not new_uid:
                typ2, _ = m.select(_quote_folder(folder), readonly=True)
                if typ2 == "OK":
                    typ3, uid_data = m.uid("SEARCH", None, "ALL")
                    if typ3 == "OK" and uid_data and uid_data[0]:
                        uids = uid_data[0].split()
                        if uids:
                            new_uid = int(uids[-1])

            return new_uid
        finally:
            try:
                m.logout()
            except Exception:
                pass

    # ---------- SMTP ----------

    def send(
        self,
        to: Union[str, Sequence[str]],
        subject: str,
        body: str = "",
        html: bool = False,
        cc: Union[str, Sequence[str], None] = None,
        bcc: Union[str, Sequence[str], None] = None,
        attachments: Optional[Sequence[str]] = None,
        inline_images: Optional[Sequence[Union[str, Tuple[str, str]]]] = None,
        from_name: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        text_alt: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """发送一封邮件。返回 {message_id, accepted, refused}

        参数：
            inline_images: 内联图片列表，每项可以是：
                - "path/to/img.png:logo_cid"   字符串形式（path:cid）
                - ("path/to/img.png", "logo_cid")  二元组
                正文 HTML 中通过 <img src="cid:logo_cid"> 引用。
                使用内联图片时 html 参数会被强制视为 True。
            text_alt: HTML 邮件的纯文本替代版本；不传则自动从 HTML 简单去标签生成。
                仅在 html=True 或存在 inline_images 时有意义。
            in_reply_to: 设置 In-Reply-To 头，值通常为被回复邮件的 Message-ID
                （含尖括号），用于线程合并。
            references: 设置 References 头，值通常是空格分隔的 Message-ID 列表。
                与 in_reply_to 配合使用即可让客户端把多封邮件归到同一线程。
            extra_headers: 任意附加邮件头，dict 形式 {name: value}。
                例：{"X-Priority": "1", "X-Custom-Trace": "abc"}。注意以下头由
                本方法自身生成、传入将被忽略：From / To / Cc / Subject / Date /
                Message-ID / In-Reply-To / References。
        """
        to_list = _split_addresses(to)
        cc_list = _split_addresses(cc)
        bcc_list = _split_addresses(bcc)
        if not to_list:
            raise ValueError("to 不能为空")

        # 解析内联图：[(path, cid, subtype), ...]
        inline_specs: List[Tuple[Path, str, str]] = []
        for item in (inline_images or []):
            if isinstance(item, (tuple, list)):
                if len(item) != 2:
                    raise ValueError(
                        f"inline_images 元组必须是 (path, cid)，收到：{item!r}")
                path_s, cid = item
            elif isinstance(item, str):
                # 仅按 **最后一个** 冒号切分，兼容 Windows 盘符 'C:\\x.png:cid'
                if ":" not in item:
                    raise ValueError(
                        f"inline_images 字符串需用 path:cid 格式：{item!r}")
                path_s, cid = item.rsplit(":", 1)
            else:
                raise ValueError(f"inline_images 元素类型不支持：{item!r}")
            cid = cid.strip().lstrip("<").rstrip(">")
            if not cid:
                raise ValueError("内联图 cid 不能为空")
            p = Path(path_s)
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(f"内联图文件不存在：{path_s}")
            mime_type, _ = mimetypes.guess_type(p.name)
            subtype = "png"
            if mime_type and mime_type.startswith("image/"):
                subtype = mime_type.split("/", 1)[1]
            else:
                # 未知扩展名时按后缀兜底
                ext = p.suffix.lower().lstrip(".")
                if ext:
                    subtype = ext
            inline_specs.append((p, cid, subtype))

        has_inline = bool(inline_specs)
        has_attach = bool(attachments)
        # 强制 html：有内联图时正文必为 HTML（cid: 引用只对 HTML 渲染有意义）
        if has_inline:
            html = True

        # 构造 MIME 结构（决策树，避免冗余嵌套）：
        #   纯文本无附件无内联图 → text/plain（顶层即单个 part，不套 multipart）
        #   纯 HTML 无附件无内联图 → alternative
        #   有附件无内联图 → mixed → alternative
        #   有内联图无附件 → related → alternative
        #   有内联图 + 附件 → mixed → (related → alternative) + 附件
        plain_only = not html and not has_attach and not has_inline
        body_str = body or ""
        if plain_only:
            # 纯文本：顶层直接是 text/plain，避免多余的 multipart/alternative 单壳
            top: email.message.Message = MIMEText(body_str, "plain", "utf-8")
        elif has_attach:
            top = MIMEMultipart("mixed")
        elif has_inline:
            top = MIMEMultipart("related")
        else:  # html，无附件无内联图
            top = MIMEMultipart("alternative")

        display_name = from_name or self.from_name
        top["From"] = formataddr((str(Header(display_name, "utf-8")), self.username)) \
            if display_name else self.username
        top["To"] = ", ".join(to_list)
        if cc_list:
            top["Cc"] = ", ".join(cc_list)
        top["Subject"] = Header(subject, "utf-8").encode()
        top["Date"] = formatdate(localtime=True)
        top["Message-ID"] = make_msgid(domain=self.username.split("@", 1)[-1] or "exmail.qq.com")
        if in_reply_to:
            top["In-Reply-To"] = in_reply_to
        if references:
            top["References"] = references
        # 附加自定义头部
        if extra_headers:
            _reserved = {"from", "to", "cc", "bcc", "subject", "date",
                         "message-id", "in-reply-to", "references"}
            for k, v in extra_headers.items():
                if not k or v is None:
                    continue
                if k.lower() in _reserved:
                    # 这些由本方法自身生成，忽略以避免重复/冲突
                    continue
                # 中文/非 ASCII 头部值用 RFC 2047 编码
                try:
                    v_str = str(v)
                    v_str.encode("ascii")
                    top[k] = v_str
                except UnicodeEncodeError:
                    top[k] = Header(str(v), "utf-8").encode()

        # 构造正文 part（纯文本就是单个 MIMEText；HTML 则准备一对 plain+html）
        if html:
            html_part = MIMEText(body_str, "html", "utf-8")
            plain_str = text_alt if text_alt is not None else _html_to_text(body_str)
            plain_part = MIMEText(plain_str, "plain", "utf-8")

            # 当顶层就是 alternative（纯 HTML 无附件无内联图）：直接挂两个 part
            if top.get_content_subtype() == "alternative":
                body_container = None  # 标记：直接挂到 top
            else:
                # 顶层是 mixed/related：用一个独立的 alternative 包住 plain+html
                body_container = MIMEMultipart("alternative")
                body_container.attach(plain_part)
                body_container.attach(html_part)
        else:
            html_part = None
            plain_part = None
            # 纯文本无附件无内联图时 top 已是 MIMEText 正文本身，无需再造 container
            body_container = None if plain_only else MIMEText(body_str, "plain", "utf-8")

        # 把正文挂到合适的层
        if plain_only:
            pass  # 正文即 top，无需附加
        elif has_inline:
            related = MIMEMultipart("related") if has_attach else top
            if html and body_container is None:
                # 不应该走到这里（has_inline 时顶层不是 alternative），但兜底
                inner_alt = MIMEMultipart("alternative")
                inner_alt.attach(plain_part)
                inner_alt.attach(html_part)
                related.attach(inner_alt)
            else:
                related.attach(body_container)
            for path, cid, subtype in inline_specs:
                with open(path, "rb") as f:
                    img_data = f.read()
                img = MIMEImage(img_data, _subtype=subtype)
                img.add_header("Content-ID", f"<{cid}>")
                img.add_header("Content-Disposition", "inline",
                               filename=("utf-8", "", path.name))
                related.attach(img)
            if has_attach:
                top.attach(related)
        elif has_attach:
            # mixed → alternative + 附件
            top.attach(body_container)
        else:
            # 顶层即 alternative（HTML） 或 单 part（plain）
            if html and body_container is None:
                top.attach(plain_part)
                top.attach(html_part)
            else:
                top.attach(body_container)

        if has_attach:
            for fp in attachments:
                top.attach(_build_attachment(fp))

        # 投递
        recipients = to_list + cc_list + bcc_list
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port,
                              context=ctx, timeout=self.timeout) as s:
            s.login(self.username, self.password)
            refused = s.sendmail(self.username, recipients, top.as_string())

        accepted = [r for r in recipients if r not in (refused or {})]
        return {
            "message_id": top["Message-ID"],
            "accepted": accepted,
            "refused": list((refused or {}).keys()),
        }

    def reply(
        self,
        uid: int,
        body: str,
        html: bool = False,
        attachments: Optional[Sequence[str]] = None,
        inline_images: Optional[Sequence[Union[str, Tuple[str, str]]]] = None,
        include_quote: bool = False,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """对一封邮件进行回复，自动维护 Re: 主题与 In-Reply-To/References。"""
        original = self.read(uid=uid, folder=folder, mark_seen=False)
        from_addr = parseaddr(original["from"])[1]
        if not from_addr:
            raise RuntimeError("原邮件 From 解析失败，无法回复")

        subj = original.get("subject", "") or ""
        if not re.match(r"^\s*Re:", subj, re.IGNORECASE):
            subj = "Re: " + subj

        in_reply_to = original.get("message_id") or None
        refs = (original.get("references") or "").strip()
        new_refs = (refs + " " + (in_reply_to or "")).strip() if (refs or in_reply_to) else None

        if include_quote:
            quote_text = (original.get("body_text") or "").strip()
            if quote_text:
                quoted = "\n".join("> " + line for line in quote_text.splitlines())
                if html:
                    body = body + "<br/><br/><blockquote>" + \
                           quoted.replace("\n", "<br/>") + "</blockquote>"
                else:
                    body = body + "\n\n----- 原邮件 -----\n" + quoted

        return self.send(
            to=from_addr,
            subject=subj,
            body=body,
            html=html,
            attachments=attachments,
            inline_images=inline_images,
            in_reply_to=in_reply_to,
            references=new_refs,
        )


# =====================================================================
# 解析邮件内容
# =====================================================================

def _looks_like_has_attachment(msg: email.message.Message) -> bool:
    """通过头部快速判断是否含附件（仅启发式）。

    注意：当 msg 由 BODY.PEEK[HEADER] 解析得到时，**没有 body 部分**，
    is_multipart() / walk() 都不会进入子部件。因此优先看顶层 Content-Type，
    `multipart/mixed`、`multipart/related` 通常意味着有附件或内嵌资源。
    """
    ctype = (msg.get("Content-Type", "") or "").lower()
    if "multipart/mixed" in ctype or "multipart/related" in ctype:
        return True
    # 完整邮件场景：照常遍历
    if msg.is_multipart():
        for part in msg.walk():
            cd = part.get("Content-Disposition", "") or ""
            if "attachment" in cd.lower():
                return True
            if part.get_filename():
                return True
    return False


def _walk_message(
    msg: email.message.Message,
    save_to: Optional[str] = None,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """遍历邮件，提取正文（text/html）与附件列表。"""
    body_text_parts: List[str] = []
    body_html_parts: List[str] = []
    attachments: List[Dict[str, Any]] = []

    save_dir: Optional[Path] = None
    if save_to:
        save_dir = Path(save_to)
        save_dir.mkdir(parents=True, exist_ok=True)

    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        cd = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        if filename:
            filename = _decode_mime_header(filename)

        # 附件
        if "attachment" in cd or filename:
            payload = part.get_payload(decode=True) or b""
            saved_path = None
            if save_dir is not None and filename:
                safe = _sanitize_filename(filename)
                target = save_dir / safe
                # 文件名冲突自动加序号
                idx = 1
                while target.exists():
                    target = save_dir / f"{target.stem}_{idx}{target.suffix}"
                    idx += 1
                target.write_bytes(payload)
                saved_path = str(target)
            attachments.append({
                "filename": filename,
                "content_type": ctype,
                "size": len(payload),
                "saved_path": saved_path,
            })
            continue

        # 正文
        payload_bytes = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload_bytes.decode(charset, errors="replace")
        except (LookupError, TypeError):
            text = payload_bytes.decode("utf-8", errors="replace")

        if ctype == "text/plain":
            body_text_parts.append(text)
        elif ctype == "text/html":
            body_html_parts.append(text)

    return "\n".join(body_text_parts), "\n".join(body_html_parts), attachments


def _sanitize_filename(name: str) -> str:
    name = name.replace("\x00", "")
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    return name.strip() or "attachment"


def _html_to_text(html: str) -> str:
    """从 HTML 简易抽取纯文本，用于多部件邮件的 text/plain 替代版本。

    不追求 100% 还原，只保证：
      - 去掉 <script>/<style> 内容
      - <br>/<p>/<div>/<li>/<tr> 等块级元素改为换行
      - HTML 实体（&nbsp; &amp; &lt; ...）解码
      - 连续空白压缩
    """
    if not html:
        return ""
    s = html
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
    # 块级标签替换为换行
    s = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*(p|div|li|tr|h[1-6]|blockquote|pre|table)\s*>", "\n", s)
    # 列表项前缀
    s = re.sub(r"(?i)<\s*li[^>]*>", "- ", s)
    # 去掉所有剩余标签
    s = re.sub(r"<[^>]+>", "", s)
    # 实体解码
    try:
        import html as _html_mod
        s = _html_mod.unescape(s)
    except Exception:
        pass
    # 压缩多余空白
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _build_attachment(filepath: str) -> MIMEBase:
    p = Path(filepath)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"附件不存在：{filepath}")
    data = p.read_bytes()
    part = MIMEBase("application", "octet-stream")
    part.set_payload(data)
    encoders.encode_base64(part)
    # 中文文件名兼容性最好的方式：RFC 2231
    part.add_header("Content-Disposition", "attachment",
                    filename=("utf-8", "", p.name))
    return part


# =====================================================================
# 邮件日期修改
# =====================================================================

# RFC 2822 日期格式全局匹配正则（字节模式，覆盖 Date / Received(含多行折行) /
# X-Received / Message-ID 等任意字段中出现的日期串）。
#   - 星期前缀可选（RFC 2822 允许省略，如 "15 Jun 2026 ..."）
#   - 秒、时区偏移、时区注释 (CST)/(PDT) 均可选
#   - 各组件间分隔符限定为空格/制表符（[ \t]+），避免 \s+ 误跨续行/换行
_RFC2822_DATE_RE = re.compile(
    rb'(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),[ \t]+)?'
    rb'\d{1,2}[ \t]+'
    rb'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[ \t]+'
    rb'\d{4}[ \t]+'
    rb'\d{1,2}:\d{2}(?::\d{2})?'
    rb'(?:[ \t]+[+-]\d{4})?'
    rb'(?:[ \t]+\([A-Za-z]+\))?'
)


def modify_eml_date(
    eml_path: str,
    new_date: Union[datetime, str],
    output_path: Optional[str] = None,
) -> int:
    """全局修改 .eml 文件中所有 RFC 2822 日期字符串（不区分字段名）。

    ⚠️ 关键认知：邮件客户端（腾讯企业邮 WebMail / Outlook / Thunderbird 等）判断
    邮件到达时间时**优先读取 `Received` 字段的时间戳**，而非 `Date` 字段。若只改
    `Date` 头，客户端往往仍显示旧日期——这是日期"反复改不对"的根本原因。

    EML 中的日期可能散布在多个位置，且格式各异：
        - `Date:` 头
        - `Received:` 头（常折行成多行，日期在以 TAB 开头的续行中；
          存在 `for <...>;` / `id ;` 等多种格式）
        - `X-Received:`（Gmail 转发常见）
        - `Message-ID:`（部分邮件内嵌可读日期）

    逐字段正则永远有盲区。本函数因此**对整封邮件原始字节做全局正则替换**，把所有
    符合 RFC 2822 格式的日期串一次性替换为新日期，一步到位、不留残留。

    采用字节级替换而非先解析再序列化，可避免：
        1. `email.message_from_bytes` 重新序列化时改写正文/编码；
        2. UTF-8 BOM 等编码陷阱导致的检测误判。

    参数：
        eml_path: 输入 .eml 文件路径
        new_date: 新日期，datetime 对象或字符串（"YYYY-MM-DD [HH:MM:SS]"）
        output_path: 输出路径，不传则原地修改

    返回：被替换的日期字符串数量
    """
    eml_file = Path(eml_path)
    if not eml_file.exists():
        raise FileNotFoundError(f".eml 文件不存在：{eml_path}")

    # 解析日期
    if isinstance(new_date, str):
        new_date = _parse_date_string(new_date)

    # 完整 RFC 2822 日期串（含星期与时区），如 "Mon, 22 Jun 2026 10:30:00 +0800"
    date_str = email.utils.format_datetime(new_date)
    date_bytes = date_str.encode("ascii")

    # 读取原始字节并做全局替换
    raw_bytes = eml_file.read_bytes()
    new_bytes, count = _RFC2822_DATE_RE.subn(date_bytes, raw_bytes)

    # 兜底：整封邮件没有任何 RFC 日期串（极少见），至少补上 Date 头
    if count == 0:
        msg = email.message_from_bytes(raw_bytes)
        if "Date" in msg:
            del msg["Date"]
        msg["Date"] = date_str
        new_bytes = msg.as_bytes()

    # 写回
    out = output_path or eml_path
    Path(out).write_bytes(new_bytes)
    return count


def _parse_date_string(date_str: str, tz_str: str = "+0800") -> datetime:
    """解析日期字符串为 datetime 对象。

    支持格式：
        - "YYYY-MM-DD HH:MM:SS"
        - "YYYY-MM-DD"

    参数：
        date_str: 日期字符串
        tz_str: 时区偏移，如 "+0800", "-0500", "+0000"
    """
    # 解析时区
    tz_sign = 1 if tz_str[0] == '+' else -1
    tz_hours = int(tz_str[1:3])
    tz_minutes = int(tz_str[3:5])
    tz = timezone(timedelta(hours=tz_sign * tz_hours, minutes=tz_sign * tz_minutes))

    # 尝试不同格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=tz)
        except ValueError:
            continue

    raise ValueError(
        f"日期格式不正确：{date_str!r}\n"
        f"支持的格式：\n"
        f"  - YYYY-MM-DD HH:MM:SS（如 2026-06-01 10:30:00）\n"
        f"  - YYYY-MM-DD（如 2026-06-01，时间默认 00:00:00）"
    )


# =====================================================================
# CLI
# =====================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="exmail",
        description="腾讯企业邮箱（exmail.qq.com）IMAP+SMTP 客户端",
    )
    p.add_argument("--username", required=True, help="完整邮箱地址")
    p.add_argument("--password", required=True, help="客户端专用密码")
    p.add_argument("--imap-host", default=None)
    p.add_argument("--imap-port", type=int, default=None)
    p.add_argument("--smtp-host", default=None)
    p.add_argument("--smtp-port", type=int, default=None)

    sub = p.add_subparsers(dest="cmd", required=True)

    # inbox
    s_in = sub.add_parser("inbox", help="列出邮件")
    s_in.add_argument("--folder", default="INBOX",
                      help="文件夹名，含空格/中文需用引号；先用 folders 子命令查看")
    s_in.add_argument("--unread", action="store_true")
    s_in.add_argument("--from", dest="from_addr")
    s_in.add_argument("--subject")
    s_in.add_argument("--body", dest="body_kw",
                      help="正文关键词（中文走客户端兜底，开销大；建议配合 --since 缩小范围）")
    s_in.add_argument("--since", help="日期，YYYY-MM-DD 或 DD-Mon-YYYY")
    s_in.add_argument("--before", help="日期，同 --since")
    s_in.add_argument("--limit", type=int, default=20)
    s_in.add_argument("--raw-search", help="原生 IMAP SEARCH 字符串（可含 CHARSET UTF-8 ...）")
    s_in.add_argument("--output", help="将 JSON 结果写入文件（避免大邮箱终端截断）")

    # folders
    s_fd = sub.add_parser("folders", help="列出邮箱所有文件夹（含中文名解码）")
    s_fd.add_argument("--output", help="将 JSON 结果写入文件")

    # read
    s_rd = sub.add_parser("read", help="读取单封邮件")
    s_rd.add_argument("--uid", type=int, required=True)
    s_rd.add_argument("--folder", default="INBOX")
    s_rd.add_argument("--mark-seen", action="store_true")
    s_rd.add_argument("--save-attachments", help="附件保存目录")
    s_rd.add_argument("--no-html", action="store_true",
                      help="输出中省略 body_html 字段（长邮件友好）")
    s_rd.add_argument("--body-lines", type=int, default=0,
                      help="只保留正文前 N 行（0=全部）")
    s_rd.add_argument("--output", help="将 JSON 结果写入文件")

    # flag
    s_fl = sub.add_parser("flag", help="标记邮件状态")
    s_fl.add_argument("--uid", type=int, required=True)
    s_fl.add_argument("--folder", default="INBOX")
    g = s_fl.add_mutually_exclusive_group()
    g.add_argument("--seen", dest="seen", action="store_true")
    g.add_argument("--unseen", dest="unseen", action="store_true")
    s_fl.add_argument("--flagged", action="store_true")
    s_fl.add_argument("--unflagged", action="store_true")

    # move
    s_mv = sub.add_parser("move", help="移动邮件到指定文件夹")
    s_mv.add_argument("--uid", type=int, required=True)
    s_mv.add_argument("--to", dest="dest", required=True, help="目标文件夹名")
    s_mv.add_argument("--folder", default="INBOX")

    # delete
    s_del = sub.add_parser("delete", help="删除邮件")
    s_del.add_argument("--uid", type=int, required=True)
    s_del.add_argument("--folder", default="INBOX")

    # send
    s_sd = sub.add_parser("send", help="发送邮件")
    s_sd.add_argument("--to", help="收件人，多个用逗号/分号分隔；使用 --from-json 时可省略")
    s_sd.add_argument("--cc")
    s_sd.add_argument("--bcc")
    s_sd.add_argument("--subject", help="主题；使用 --from-json 时可省略")
    s_sd.add_argument("--body")
    s_sd.add_argument("--body-file")
    s_sd.add_argument("--html", action="store_true")
    s_sd.add_argument("--attach", action="append", default=[])
    s_sd.add_argument("--inline-image", action="append", default=[],
                      dest="inline_image",
                      help="内联图片，格式 PATH:CID；正文 HTML 中通过 "
                           "<img src=\"cid:CID\"> 引用；可重复指定多张")
    s_sd.add_argument("--from-name", help="发件人显示名")
    s_sd.add_argument("--in-reply-to", dest="in_reply_to",
                      help="In-Reply-To 头，值为被回复邮件的 Message-ID（含尖括号），"
                           "用于线程合并")
    s_sd.add_argument("--references", dest="references",
                      help="References 头，空格分隔的 Message-ID 列表（含尖括号），"
                           "配合 --in-reply-to 使用")
    s_sd.add_argument("--header", action="append", default=[], dest="header",
                      help='附加自定义头部，格式 NAME:VALUE（可重复）。例：'
                           '--header "X-Priority:1" --header "X-Trace:abc"')
    s_sd.add_argument("--from-json",
                      help="从 JSON 文件读取完整邮件描述（详见 references/"
                           "send-from-json.md），可与命令行参数共存（命令行参数优先）")
    s_sd.add_argument("--send-interval", type=float, default=0,
                      help="多收件人按个发送时的间隔秒数（默认一次性发送）")

    # reply
    s_rp = sub.add_parser("reply", help="回复一封邮件")
    s_rp.add_argument("--uid", type=int, required=True)
    s_rp.add_argument("--folder", default="INBOX")
    body_grp2 = s_rp.add_mutually_exclusive_group(required=True)
    body_grp2.add_argument("--body")
    body_grp2.add_argument("--body-file")
    s_rp.add_argument("--html", action="store_true")
    s_rp.add_argument("--attach", action="append", default=[])
    s_rp.add_argument("--inline-image", action="append", default=[],
                      dest="inline_image",
                      help="内联图片，格式 PATH:CID（可重复）")
    s_rp.add_argument("--include-quote", action="store_true",
                      help="在正文末尾附上原邮件引用")

    # modify-date
    s_md = sub.add_parser("modify-date", help="修改邮件的 Date 头部日期")
    s_md.add_argument("--uid", type=int, required=True,
                      help="要修改的邮件 UID")
    s_md.add_argument("--folder", default="INBOX",
                      help="邮件所在文件夹（默认 INBOX）")
    s_md.add_argument("--new-date", required=True, dest="new_date",
                      help="新日期，格式 YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD")
    s_md.add_argument("--timezone", default="+0800", dest="timezone",
                      help="时区偏移（默认 +0800），如 +0000, -0500")
    s_md.add_argument("--keep-original", action="store_true", dest="keep_original",
                      help="保留原邮件（默认删除原邮件）")

    return p


def _make_client(args: argparse.Namespace) -> ExmailClient:
    username, password = _resolve_credentials(args.username, args.password)
    return ExmailClient(
        username=username,
        password=password,
        imap_host=args.imap_host or DEFAULT_IMAP_HOST,
        imap_port=args.imap_port or DEFAULT_IMAP_PORT,
        smtp_host=args.smtp_host or DEFAULT_SMTP_HOST,
        smtp_port=args.smtp_port or DEFAULT_SMTP_PORT,
    )


def _read_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    return Path(args.body_file).read_text(encoding="utf-8")


def _resolve_send_spec(args: argparse.Namespace) -> Dict[str, Any]:
    """合并 send 子命令的 --from-json 与 CLI 参数，返回 send() 调用所需的字段。

    解析优先级：CLI 显式参数 > JSON 文件字段。
    自定义头（headers / --header）的合并方式是 CLI 追加并按名覆盖到 JSON。

    JSON 格式（所有字段均可选，但合并后 to/subject/body 必须有值）：
    {
        "to": "a@x.com,b@x.com",         // 字符串或字符串数组
        "cc": ["c@x.com"],
        "bcc": "d@x.com",
        "subject": "周报",
        "from_name": "张三",
        "html": true,                     // 缺省 false；body_html 存在时自动 true
        "body": "纯文本/HTML 字符串",     // 与 body_file/body_html 三选一
        "body_file": "./body.html",       // 路径相对 JSON 文件所在目录
        "body_html": "<h1>HTML</h1>",     // 等同 body+html=true
        "text_alt": "HTML 邮件的纯文本替代版本",
        "attachments": ["./report.pdf", "./data.xlsx"],
        "inline_images": [
            {"path": "./logo.png", "cid": "logo_cid"},
            "./banner.jpg:banner_cid"     // 也支持 path:cid 字符串
        ],
        "in_reply_to": "<msgid@host>",    // 用于线程合并：被回复邮件的 Message-ID
        "references": "<id1@h> <id2@h>",  // 空格分隔的历史 Message-ID 列表
        "headers": {                      // 任意附加自定义头部
            "X-Priority": "1",
            "X-Custom-Trace": "abc"
        }
    }
    """
    spec: Dict[str, Any] = {
        "to": None, "cc": None, "bcc": None,
        "subject": None, "from_name": None,
        "html": False, "body": None, "text_alt": None,
        "attachments": [], "inline_images": [],
        "in_reply_to": None, "references": None,
        "extra_headers": {},
    }

    # 1) 先吃 JSON 文件（如有）
    json_path = getattr(args, "from_json", None)
    if json_path:
        jp = Path(json_path)
        if not jp.exists():
            raise FileNotFoundError(f"--from-json 文件不存在：{json_path}")
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"--from-json 文件 JSON 解析失败：{e}")
        if not isinstance(data, dict):
            raise SystemExit("--from-json 顶层必须是一个 JSON 对象")
        base_dir = jp.parent

        def _abs(p: str) -> str:
            pp = Path(p)
            if pp.is_absolute():
                return str(pp)
            return str((base_dir / pp).resolve())

        # 简单字段
        for k in ("to", "cc", "bcc", "subject", "from_name", "text_alt",
                  "in_reply_to", "references"):
            if k in data and data[k] is not None:
                v = data[k]
                if isinstance(v, list):
                    v = ",".join(str(x) for x in v)
                spec[k] = v
        if "html" in data:
            spec["html"] = bool(data["html"])
        # 自定义头部（dict 形式，键为头名）
        if "headers" in data and data["headers"]:
            if not isinstance(data["headers"], dict):
                raise SystemExit("--from-json 的 headers 字段必须是对象/字典")
            for k, v in data["headers"].items():
                if k and v is not None:
                    spec["extra_headers"][str(k)] = str(v)
        # body 三种来源
        if "body_html" in data and data["body_html"] is not None:
            spec["body"] = str(data["body_html"])
            spec["html"] = True
        elif "body_file" in data and data["body_file"]:
            spec["body"] = Path(_abs(data["body_file"])).read_text(encoding="utf-8")
        elif "body" in data and data["body"] is not None:
            spec["body"] = str(data["body"])
        # 附件
        if "attachments" in data and data["attachments"]:
            spec["attachments"] = [_abs(p) for p in data["attachments"]]
        # 内联图
        if "inline_images" in data and data["inline_images"]:
            normalized: List[Any] = []
            for item in data["inline_images"]:
                if isinstance(item, str):
                    if ":" not in item:
                        raise SystemExit(
                            f"inline_images 字符串必须是 path:cid 形式：{item!r}")
                    p, cid = item.rsplit(":", 1)
                    normalized.append((_abs(p), cid))
                elif isinstance(item, dict):
                    p = item.get("path") or item.get("file")
                    cid = item.get("cid") or item.get("content_id")
                    if not p or not cid:
                        raise SystemExit(
                            f"inline_images 对象必须含 path 与 cid：{item!r}")
                    normalized.append((_abs(p), cid))
                else:
                    raise SystemExit(
                        f"inline_images 元素类型不支持：{item!r}")
            spec["inline_images"] = normalized

    # 2) CLI 参数覆盖（仅当用户显式传值时）
    if args.to:
        spec["to"] = args.to
    if args.cc:
        spec["cc"] = args.cc
    if args.bcc:
        spec["bcc"] = args.bcc
    if args.subject:
        spec["subject"] = args.subject
    if args.from_name:
        spec["from_name"] = args.from_name
    if args.html:
        spec["html"] = True
    if args.body is not None:
        spec["body"] = args.body
    elif args.body_file:
        spec["body"] = Path(args.body_file).read_text(encoding="utf-8")
    if args.attach:
        # CLI --attach 追加到 JSON 列表后（而非覆盖），更符合直觉。
        # CLI 路径按当前工作目录解析为绝对路径，与 JSON 分支（相对 JSON 文件目录）
        # 各自采用直觉一致的基准，合并后列表统一为绝对路径。
        spec["attachments"] = list(spec["attachments"]) + [
            str(Path(p).resolve()) for p in args.attach
        ]
    cli_inline = getattr(args, "inline_image", None) or []
    if cli_inline:
        # 归一化为 (绝对路径, cid) 元组，与 JSON 分支输出格式保持一致；
        # 同时在此尽早校验 path:cid 格式（rsplit 兼容 Windows 盘符 C:\x.png:cid）。
        cli_norm: List[Any] = []
        for item in cli_inline:
            if ":" not in item:
                raise SystemExit(
                    f"--inline-image 必须是 PATH:CID 形式，收到：{item!r}")
            p, cid = item.rsplit(":", 1)
            if not cid.strip():
                raise SystemExit(f"--inline-image 的 CID 不能为空：{item!r}")
            cli_norm.append((str(Path(p).resolve()), cid.strip()))
        spec["inline_images"] = list(spec["inline_images"]) + cli_norm
    # 线程合并相关头：CLI 显式提供则覆盖 JSON
    if getattr(args, "in_reply_to", None):
        spec["in_reply_to"] = args.in_reply_to
    if getattr(args, "references", None):
        spec["references"] = args.references
    # 自定义头部：CLI --header 追加（重名则覆盖）
    cli_headers = getattr(args, "header", None) or []
    for item in cli_headers:
        if not item or ":" not in item:
            raise SystemExit(
                f"--header 必须是 NAME:VALUE 形式，收到：{item!r}")
        name, value = item.split(":", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            raise SystemExit(f"--header 头名为空：{item!r}")
        spec["extra_headers"][name] = value

    # 3) 必填校验
    missing = [k for k in ("to", "subject") if not spec.get(k)]
    if spec.get("body") is None:
        missing.append("body/body_file/body_html")
    if missing:
        raise SystemExit(
            "send 缺少必填字段：" + ", ".join(missing) +
            "（可通过 CLI 参数或 --from-json 提供）"
        )
    return spec




def _emit_json(obj: Any, output_path: Optional[str]) -> None:
    """把结果输出到 stdout 或写入文件（避免大邮箱在终端被截断）。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        summary = {"output": output_path}
        if isinstance(obj, list):
            summary["count"] = len(obj)
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(text)


def _force_utf8_stdio() -> None:
    """Windows 控制台默认 GBK，输出中文 JSON 会乱码。
    在 main 启动时把 stdout/stderr 切到 UTF-8。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig is not None:
            try:
                reconfig(encoding="utf-8", errors="replace")
            except Exception:
                pass


class ExmailAuthError(Exception):
    """登录失败（IMAP 或 SMTP）。"""


def _friendly_login_hint(raw: str) -> str:
    """把底层登录错误翻译成对用户友好的诊断提示。"""
    base = (
        "登录企业邮箱失败。常见原因：\n"
        "  1) 密码错误：必须使用「客户端专用密码」（16 位），不是网页登录密码。\n"
        "     获取方式：https://exmail.qq.com 登录后 → 设置 → 客户端专用密码 → 新增\n"
        "  2) 账号未启用 IMAP/SMTP：登录企业邮箱网页版 → 设置 → 收发信设置 → "
        "启用 IMAP/SMTP\n"
        "  3) 登录频率受限：短时间内失败次数过多，等待 5–15 分钟后再试\n"
        "  4) 账号被冻结或所属企业被限制服务\n"
        f"\n服务器返回原始信息：{raw}"
    )
    return base


def _run_with_friendly_errors(func):
    """装饰 main，让 imaplib/smtplib 登录异常输出友好提示而非 traceback。"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except imaplib.IMAP4.error as e:
            msg = e.args[0] if e.args else str(e)
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            # 启发式：登录类错误才走友好提示，其他 IMAP 错误（SELECT/EXAMINE/SEARCH 等）
            # 直接给出原始信息，避免误导用户去查密码
            login_signals = ("login fail", "auth", "lookup", "credentials",
                             "username", "password")
            lowered = str(msg).lower()
            is_login = any(s in lowered for s in login_signals)
            if is_login:
                print(_friendly_login_hint(msg), file=sys.stderr)
                return 2
            print(f"IMAP 操作失败：{msg}\n"
                  f"提示：检查 --uid / --folder 是否正确，"
                  f"文件夹名含空格的用引号或先调用 list 查看真实名称。",
                  file=sys.stderr)
            return 6
        except smtplib.SMTPAuthenticationError as e:
            print(_friendly_login_hint(f"SMTP {e.smtp_code} {e.smtp_error!r}"),
                  file=sys.stderr)
            return 2
        except smtplib.SMTPException as e:
            print(f"SMTP 发送失败：{e}", file=sys.stderr)
            return 3
        except FileNotFoundError as e:
            # 必须排在 OSError 之前：FileNotFoundError 是 OSError 子类，
            # 否则会被下面的网络分支抢先捕获、误报为“网络连接失败”。
            print(f"文件不存在：{e}", file=sys.stderr)
            return 5
        except (ConnectionError, OSError) as e:
            print(f"网络连接失败：{e}\n请检查网络/代理设置，或服务器是否可达。",
                  file=sys.stderr)
            return 4
        except (RuntimeError, ValueError) as e:
            # 客户端方法在参数/IMAP 响应异常时会抛这两类（如选文件夹失败、
            # UID 不存在、附件路径缺失、日期格式错误等）。给出简洁错误而非 traceback。
            print(f"操作失败：{e}", file=sys.stderr)
            return 6
        except Exception as e:  # 兜底：任何未预期异常也返回非零退出码
            print(f"未预期的错误：{type(e).__name__}: {e}", file=sys.stderr)
            return 1
    return wrapper


@_run_with_friendly_errors
def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)
    cli = _make_client(args)

    if args.cmd == "inbox":
        results = cli.list_inbox(
            folder=args.folder,
            unread_only=args.unread,
            from_addr=args.from_addr,
            subject=args.subject,
            body_kw=args.body_kw,
            since=args.since,
            before=args.before,
            raw_search=args.raw_search,
            limit=args.limit,
        )
        _emit_json(results, getattr(args, "output", None))

    elif args.cmd == "folders":
        results = cli.list_folders()
        _emit_json(results, getattr(args, "output", None))

    elif args.cmd == "read":
        result = cli.read(
            uid=args.uid,
            folder=args.folder,
            mark_seen=args.mark_seen,
            save_attachments_to=args.save_attachments,
        )
        # 长邮件友好处理
        if getattr(args, "no_html", False):
            result.pop("body_html", None)
        body_lines = getattr(args, "body_lines", 0) or 0
        if body_lines > 0:
            for k in ("body_text", "body_html"):
                v = result.get(k)
                if isinstance(v, str) and v:
                    lines = v.splitlines()
                    if len(lines) > body_lines:
                        truncated = "\n".join(lines[:body_lines])
                        result[k] = (
                            f"{truncated}\n... [truncated {len(lines) - body_lines} more lines]"
                        )
        _emit_json(result, getattr(args, "output", None))

    elif args.cmd == "flag":
        seen = True if args.seen else (False if args.unseen else None)
        flagged = True if args.flagged else (False if args.unflagged else None)
        cli.flag(uid=args.uid, folder=args.folder, seen=seen, flagged=flagged)
        print(json.dumps({"ok": True, "uid": args.uid}, ensure_ascii=False))

    elif args.cmd == "move":
        cli.move(uid=args.uid, dest_folder=args.dest, src_folder=args.folder)
        print(json.dumps({"ok": True, "uid": args.uid, "to": args.dest},
                         ensure_ascii=False))

    elif args.cmd == "delete":
        cli.delete(uid=args.uid, folder=args.folder)
        print(json.dumps({"ok": True, "uid": args.uid, "deleted": True},
                         ensure_ascii=False))

    elif args.cmd == "send":
        spec = _resolve_send_spec(args)
        to_list = _split_addresses(spec["to"])
        if args.send_interval and len(to_list) > 1:
            results = []
            for i, addr in enumerate(to_list):
                r = cli.send(
                    to=addr,
                    subject=spec["subject"],
                    body=spec["body"],
                    html=spec["html"],
                    cc=spec.get("cc"),
                    bcc=spec.get("bcc"),
                    attachments=spec.get("attachments") or [],
                    inline_images=spec.get("inline_images") or [],
                    from_name=spec.get("from_name"),
                    text_alt=spec.get("text_alt"),
                    in_reply_to=spec.get("in_reply_to"),
                    references=spec.get("references"),
                    extra_headers=spec.get("extra_headers") or None,
                )
                results.append(r)
                if i < len(to_list) - 1:
                    time.sleep(args.send_interval)
            print(json.dumps({"sent": results}, ensure_ascii=False, indent=2))
        else:
            r = cli.send(
                to=to_list,
                subject=spec["subject"],
                body=spec["body"],
                html=spec["html"],
                cc=spec.get("cc"),
                bcc=spec.get("bcc"),
                attachments=spec.get("attachments") or [],
                inline_images=spec.get("inline_images") or [],
                from_name=spec.get("from_name"),
                text_alt=spec.get("text_alt"),
                in_reply_to=spec.get("in_reply_to"),
                references=spec.get("references"),
                extra_headers=spec.get("extra_headers") or None,
            )
            print(json.dumps(r, ensure_ascii=False, indent=2))

    elif args.cmd == "reply":
        body = _read_body(args)
        r = cli.reply(
            uid=args.uid,
            body=body,
            html=args.html,
            attachments=args.attach,
            inline_images=getattr(args, "inline_image", None) or None,
            include_quote=args.include_quote,
            folder=args.folder,
        )
        print(json.dumps(r, ensure_ascii=False, indent=2))

    elif args.cmd == "modify-date":
        # 修改邮件日期：拉取 → 改日期 → APPEND → 删原件
        tmp_dir = None
        try:
            # 1) 解析新日期
            new_dt = _parse_date_string(args.new_date, args.timezone)

            # 2) 拉取原始邮件并保存为临时 .eml
            tmp_dir = tempfile.mkdtemp(prefix="exmail_modify_date_")
            result = cli.read(
                uid=args.uid,
                folder=args.folder,
                save_eml_to=tmp_dir,
            )
            eml_path = result.get("eml_path")
            if not eml_path:
                raise RuntimeError("无法保存原始邮件为 .eml 文件")

            # 3) 全局替换邮件中所有 RFC 2822 日期串（Date / Received / X-Received /
            #    Message-ID 等），而非只改 Date 头
            replaced = modify_eml_date(eml_path, new_dt)

            # 4) APPEND 修改后的邮件回原文件夹。
            #    关键：同时把 IMAP 内部日期（INTERNALDATE）设为新日期——很多客户端
            #    （含腾讯企业邮 WebMail）按 INTERNALDATE 排序/显示到达时间。
            modified_raw = Path(eml_path).read_bytes()
            new_uid = cli.append(
                folder=args.folder,
                raw_email=modified_raw,
                flags=["\\Seen"],
                date=new_dt,
            )

            # 5) 删除原邮件（除非 --keep-original）
            if not args.keep_original:
                cli.delete(uid=args.uid, folder=args.folder)

            # 6) 输出结果
            print(json.dumps({
                "success": True,
                "old_uid": args.uid,
                "new_uid": new_uid,
                "folder": args.folder,
                "new_date": email.utils.format_datetime(new_dt),
                "replaced_dates": replaced,
            }, ensure_ascii=False, indent=2))

        finally:
            # 清理临时文件
            if tmp_dir:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)

    else:
        parser.error(f"未知子命令：{args.cmd}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
