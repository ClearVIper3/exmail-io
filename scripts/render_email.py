#!/usr/bin/env python3
"""render_email.py — 邮件正文拼装工具

将 assets/templates/ 骨架 + assets/components/ 组件 + 占位符替换 → 完整 HTML 正文。
可选进一步输出 exmail.py send --from-json 所需的 JSON 描述文件。

用法：
    # 渲染模板 → 输出 HTML
    python scripts/render_email.py render \\
        --template boss_request.html \\
        --set BODY="请确认本周3个核心场景能否优化完成" \\
        --set DEADLINE_LINE="<p style='color:#f53f3f'>截止：今天18:00</p>" \\
        --set 'IMG_TAG_OR_EMPTY=<img src="cid:arch1" width="100%">' \\
        --set LINK_HTML="" \\
        --output ./assembled_body.html

    # 渲染模板 + 嵌入组件（组件也做占位符替换）
    python scripts/render_email.py render \\
        --template approval_email.html \\
        --embed "CARD=approval_card.html:TYPE=差旅费报销,APPLICANT=张伟,AMOUNT=¥38000,REASON=深圳出差,DEADLINE=明天,STATUS=待我审批,STATUS_COLOR=#ff7d00" \\
        --output ./approval_body.html

    # 一步到位：渲染 + 生成 JSON（可直接 exmail.py send --from-json）
    python scripts/render_email.py compose \\
        --template boss_request.html \\
        --set BODY="请确认排期" \\
        --set 'IMG_TAG_OR_EMPTY=<img src="cid:arch1" width="100%">' \\
        --set DEADLINE_LINE="" --set LINK_HTML="" \\
        --to me@example.com \\
        --subject "Q3产品路线图确认" \\
        --from-name "技术负责人" \\
        --inline-image "assets/inline_images/architecture.png:arch1" \\
        --in-reply-to "<original@host>" \\
        --header "X-Priority:1" \\
        --output ./mail.json

Python API：
    from scripts.render_email import render_template, compose_json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Windows 终端默认 GBK，强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 默认 assets 目录（相对本脚本）
_SCRIPT_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _SCRIPT_DIR.parent / "assets"
_TEMPLATES_DIR = _ASSETS_DIR / "templates"
_COMPONENTS_DIR = _ASSETS_DIR / "components"


def render_template(
    template_name: str,
    replacements: Optional[Dict[str, str]] = None,
    embeds: Optional[List[Tuple[str, str, Dict[str, str]]]] = None,
    templates_dir: Optional[Path] = None,
    components_dir: Optional[Path] = None,
) -> str:
    """渲染模板：读取模板文件 → 嵌入组件 → 替换占位符 → 返回 HTML 字符串。

    参数：
        template_name: 模板文件名（在 templates_dir 下）
        replacements: {占位符名: 替换值} 字典，占位符格式为 {{NAME}}
        embeds: [(占位符名, 组件文件名, {组件内占位符: 值}), ...]
            先渲染组件（替换组件内占位符），再把结果填入模板的对应占位符
        templates_dir: 模板目录，默认 assets/templates/
        components_dir: 组件目录，默认 assets/components/
    """
    t_dir = templates_dir or _TEMPLATES_DIR
    c_dir = components_dir or _COMPONENTS_DIR

    tpl_path = t_dir / template_name
    if not tpl_path.exists():
        raise FileNotFoundError(f"模板不存在：{tpl_path}")
    html = tpl_path.read_text(encoding="utf-8")

    # 先处理组件嵌入
    if embeds:
        for placeholder, comp_name, comp_vars in embeds:
            comp_path = c_dir / comp_name
            if not comp_path.exists():
                raise FileNotFoundError(f"组件不存在：{comp_path}")
            comp_html = comp_path.read_text(encoding="utf-8")
            for k, v in comp_vars.items():
                comp_html = comp_html.replace("{{" + k + "}}", v)
            html = html.replace("{{" + placeholder + "}}", comp_html)

    # 再处理普通占位符替换
    if replacements:
        for k, v in replacements.items():
            html = html.replace("{{" + k + "}}", v)

    # 校验：任何残留的 {{占位符}} 都会原样出现在最终邮件里。与其静默发出带
    # "{{FOO}}" 的邮件，不如直接报错，提示补齐 --set（不需要的填空串）。
    # 检测覆盖所有 {{...}} 形态（含 {{ GREETING }} / {{DEADLINE-LINE}} 这类带
    # 空格/连字符的写法）——它们同样无法被替换逻辑填充，必须报出来。
    remaining = sorted(set(re.findall(r"\{\{[^{}]+\}\}", html)))
    if remaining:
        raise SystemExit(
            f"模板 {template_name} 存在未替换占位符：{' '.join(remaining)}；"
            f"请用 --set NAME=VALUE 补齐（不需要的填空串 --set NAME=）")

    return html


def compose_json(
    html_body: str,
    to: str,
    subject: str,
    from_name: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    inline_images: Optional[List[str]] = None,
    text_alt: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> dict:
    """生成 exmail.py send --from-json 所需的 JSON 字典。

    参数说明（仅列出易混淆项）：
        inline_images: 字符串列表，每项为 "path:cid" 形式
            （如 "assets/inline_images/architecture.png:arch1"）。这里保持字符串
            原样写入 JSON；exmail.py send --from-json 读取时会把它们归一化为
            (绝对路径, cid) 元组，路径相对该 JSON 文件所在目录解析。
        attachments: 路径字符串列表，同样相对生成的 JSON 文件目录解析。
    """
    data: dict = {
        "to": to,
        "subject": subject,
        "html": True,
        "body_html": html_body,
    }
    if from_name:
        data["from_name"] = from_name
    if cc:
        data["cc"] = cc
    if bcc:
        data["bcc"] = bcc
    if text_alt:
        data["text_alt"] = text_alt
    if attachments:
        data["attachments"] = attachments
    if inline_images:
        # 保持 path:cid 字符串格式
        data["inline_images"] = inline_images
    if in_reply_to:
        data["in_reply_to"] = in_reply_to
    if references:
        data["references"] = references
    if headers:
        data["headers"] = headers
    return data


# ─── CLI 解析 ───────────────────────────────────────────────────────────────


def _parse_set(items: List[str]) -> Dict[str, str]:
    """解析 --set KEY=VALUE 列表为字典。

    键与值均去除首尾空白，与 _parse_embed / _parse_headers 的处理保持一致，
    避免命令行里 `--set 'K= v'` 意外带入前导空格到 HTML 占位符。
    """
    result: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--set 格式错误（需 KEY=VALUE）：{item!r}")
        k, v = item.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def _parse_embed(items: List[str]) -> List[Tuple[str, str, Dict[str, str]]]:
    """解析 --embed 'PLACEHOLDER=component.html:K1=V1,K2=V2' 列表。"""
    result = []
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--embed 格式错误：{item!r}")
        placeholder, rest = item.split("=", 1)
        placeholder = placeholder.strip()
        # rest = "component.html:K1=V1,K2=V2" 或 "component.html"
        if ":" in rest:
            comp_name, vars_str = rest.split(":", 1)
            comp_vars: Dict[str, str] = {}
            for pair in vars_str.split(","):
                if "=" not in pair:
                    raise SystemExit(
                        f"--embed 组件变量格式错误（需 K=V）：{pair!r} in {item!r}")
                ck, cv = pair.split("=", 1)
                comp_vars[ck.strip()] = cv.strip()
        else:
            comp_name = rest.strip()
            comp_vars = {}
        result.append((placeholder, comp_name.strip(), comp_vars))
    return result


def _parse_headers(items: List[str]) -> Dict[str, str]:
    """解析 --header NAME:VALUE 列表。"""
    result: Dict[str, str] = {}
    for item in items:
        if ":" not in item:
            raise SystemExit(f"--header 格式错误（需 NAME:VALUE）：{item!r}")
        name, value = item.split(":", 1)
        result[name.strip()] = value.strip()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="邮件正文拼装工具：模板 + 组件 → HTML / JSON")
    sub = parser.add_subparsers(dest="command")

    # ── render 子命令 ──
    p_render = sub.add_parser("render", help="渲染模板为 HTML 文件")
    p_render.add_argument("--template", "-t", required=True,
                          help="模板文件名（在 assets/templates/ 下）")
    p_render.add_argument("--set", "-s", action="append", default=[],
                          help='占位符替换，格式 KEY=VALUE（可重复）')
    p_render.add_argument("--embed", "-e", action="append", default=[],
                          help='嵌入组件，格式 PLACEHOLDER=comp.html:K1=V1,K2=V2')
    p_render.add_argument("--output", "-o", default="-",
                          help="输出文件路径（默认 stdout）")
    p_render.add_argument("--templates-dir", default=None,
                          help="自定义模板目录")
    p_render.add_argument("--components-dir", default=None,
                          help="自定义组件目录")

    # ── compose 子命令 ──
    p_compose = sub.add_parser("compose",
                               help="渲染模板 + 生成 send --from-json 的 JSON")
    p_compose.add_argument("--template", "-t", required=True,
                           help="模板文件名")
    p_compose.add_argument("--set", "-s", action="append", default=[],
                           help='占位符替换 KEY=VALUE')
    p_compose.add_argument("--embed", "-e", action="append", default=[],
                           help='嵌入组件 PLACEHOLDER=comp.html:K1=V1,K2=V2')
    p_compose.add_argument("--to", required=True, help="收件人")
    p_compose.add_argument("--subject", required=True, help="主题")
    p_compose.add_argument("--from-name", default=None, help="发件人显示名")
    p_compose.add_argument("--cc", default=None, help="抄送")
    p_compose.add_argument("--bcc", default=None, help="密送")
    p_compose.add_argument("--attach", action="append", default=[],
                           help="附件路径（可重复）")
    p_compose.add_argument("--inline-image", action="append", default=[],
                           help="内联图 PATH:CID（可重复）")
    p_compose.add_argument("--text-alt", default=None,
                           help="纯文本替代版本")
    p_compose.add_argument("--in-reply-to", default=None,
                           help="In-Reply-To 头")
    p_compose.add_argument("--references", default=None,
                           help="References 头")
    p_compose.add_argument("--header", action="append", default=[],
                           help="自定义头 NAME:VALUE（可重复）")
    p_compose.add_argument("--output", "-o", default="-",
                           help="输出 JSON 文件路径（默认 stdout）")
    p_compose.add_argument("--templates-dir", default=None)
    p_compose.add_argument("--components-dir", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 公共参数
    t_dir = Path(args.templates_dir) if args.templates_dir else None
    c_dir = Path(args.components_dir) if args.components_dir else None
    replacements = _parse_set(args.set)
    embeds = _parse_embed(args.embed)

    # 渲染
    html = render_template(
        template_name=args.template,
        replacements=replacements,
        embeds=embeds,
        templates_dir=t_dir,
        components_dir=c_dir,
    )

    if args.command == "render":
        if args.output == "-":
            sys.stdout.write(html)
        else:
            Path(args.output).write_text(html, encoding="utf-8")
            print(f"✅ 已写入：{args.output}", file=sys.stderr)

    elif args.command == "compose":
        # 校验内联图 cid 是否真被正文引用：未被引用的内联图会以孤立 MIME part 发送，
        # 收件方看到的是空白/断链图片。用 rsplit 而非 split，兼容 Windows 绝对路径
        # 里的盘符冒号（C:\x.png:cid）。
        if args.inline_image:
            for item in args.inline_image:
                if ":" not in item:
                    raise SystemExit(
                        f"内联图格式错误（需 PATH:CID）：{item!r}")
                cid = item.rsplit(":", 1)[1].strip()
                if not cid:
                    raise SystemExit(f"内联图 CID 不能为空：{item!r}")
                # 必须带词边界匹配：纯子串判断会让 cid 前缀碰撞误判通过
                # （如正文引用 cid:monitor_capacity 时，"cid:monitor" 是其子串，
                # 但两者是不同的 Content-ID，发出的邮件会断链）
                if not re.search(
                        r"cid:" + re.escape(cid) + r"(?![A-Za-z0-9_.\-])", html):
                    raise SystemExit(
                        f"内联图 cid {cid!r} 未在正文 HTML 中被引用；"
                        f"请在模板占位符里写 <img src=\"cid:{cid}\">，"
                        f"或去掉该 --inline-image")

        headers = _parse_headers(args.header) if args.header else None
        data = compose_json(
            html_body=html,
            to=args.to,
            subject=args.subject,
            from_name=args.from_name,
            cc=args.cc,
            bcc=args.bcc,
            attachments=args.attach or None,
            inline_images=args.inline_image or None,
            text_alt=args.text_alt,
            in_reply_to=args.in_reply_to,
            references=args.references,
            headers=headers,
        )
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output == "-":
            sys.stdout.write(json_str + "\n")
        else:
            Path(args.output).write_text(json_str, encoding="utf-8")
            print(f"✅ 已写入：{args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
