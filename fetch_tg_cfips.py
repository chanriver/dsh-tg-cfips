#!/usr/bin/env python3
"""
fetch_tg_cfips.py
抓取 Telegram 公开频道 @danfeng2 当天（UTC 00:00 之后）发布的
单 IP 优选帖，输出 DSH-TG-CFIPS-DAILY.TXT

格式：IP:PORT#原生位置(国家·州·城市)→CF落地位置(大洲·国家·城市)

数据源（无需登录）：
  https://t.me/s/danfeng2

筛选规则：
- 仅保留包含 #CF优选IP 的单 IP 帖（跳过 CSV 附件、转发广告、Snippet 公告等）
- 仅保留时间戳 ≥ 今天 UTC 00:00 的帖子
- 仅保留 IPv4
"""
import html as htmllib
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from ssl import create_default_context

# 北京时间 (UTC+8)
CST = timezone(timedelta(hours=8))

CHANNEL = "danfeng2"
PREVIEW_URL = f"https://t.me/s/{CHANNEL}"
OUTPUT = Path(__file__).parent / "DSH-TG-CFIPS-DAILY.TXT"


def fetch_preview(url: str, timeout: int = 30) -> str:
    """抓 t.me/s/<channel> 公共预览页 HTML"""
    req = Request(url, headers={"User-Agent": "DSH-TG-CFIPS/1.0 (+https://github.com/chanriver/dsh-tg-cfips)"})
    ctx = create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(s: str) -> str:
    """去 HTML 标签、还原实体、合并空白"""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    # 合并多余空白但保留换行
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    return "\n".join(lines)


def parse_posts(html_text: str) -> list[dict]:
    """
    解析预览页所有单 IP 帖。
    返回 [{id, time(UTC datetime), ip, port, native_loc, cf_loc}, ...]

    时间窗口：以北京时间（UTC+8）为"天"的边界。
    频道虽然带 +00:00 后缀，但发布时间是按北京时间作息（12:00/18:00/24:00/06:00 北京），
    所以"当天"用北京时间定义，与频道发贴节奏一致。
    """
    today_cst = datetime.now(CST).date()
    results: list[dict] = []

    # 按帖子切片
    for m in re.finditer(r'data-post="danfeng2/(\d+)"(.*?)(?=data-post="danfeng2/|</section>)', html_text, re.DOTALL):
        pid = m.group(1)
        body = m.group(2)

        # 时间
        tm = re.search(r'datetime="([^"]+)"', body)
        if not tm:
            continue
        try:
            post_time_utc = datetime.fromisoformat(tm.group(1).replace("Z", "+00:00"))
        except Exception:
            continue

        # 转北京时间后判断"今天"
        post_time_cst = post_time_utc.astimezone(CST)
        if post_time_cst.date() < today_cst:
            continue

        # 抓正文
        txt_blocks = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', body, re.DOTALL)
        text = "\n".join(strip_html(b) for b in txt_blocks)

        # 只取 #CF优选IP 单 IP 帖
        if "#CF优选IP" not in text:
            continue
        # 跳过 CSV 附件（文件名含 .csv）
        title = re.search(r'tgme_widget_message_document_title[^>]*>(.*?)</div>', body, re.DOTALL)
        if title and ".csv" in title.group(1).lower():
            continue

        # 抽 IP（IPv4）
        ip_m = re.search(r"IP地址[:：]\s*((?:\d{1,3}\.){3}\d{1,3})", text)
        if not ip_m:
            continue
        ip = ip_m.group(1)
        if not all(0 <= int(p) <= 255 for p in ip.split(".")):
            continue

        # 抽端口
        port_m = re.search(r"端口[:：]\s*(\d{1,5})", text)
        if not port_m:
            continue
        port = port_m.group(1)

        # 抽原生位置（IP原生位置: ...）
        # 例：└ 🗺️ United States · California · Los Angeles
        native_loc = ""
        nat_m = re.search(
            r"IP原生位置[:：]\s*\n?\s*[└>»\s]*\s*🗺️?\s*([^\n]+)", text
        )
        if nat_m:
            native_loc = nat_m.group(1).strip()

        # 抽 CF 落地位置（CF落地位置: ...）
        # 例：└ 🌐 北美洲 · 美国洛杉矶
        cf_loc = ""
        cf_m = re.search(
            r"CF落地位置[:：]\s*\n?\s*[└>»\s]*\s*🌐?\s*([^\n]+)", text
        )
        if cf_m:
            cf_loc = cf_m.group(1).strip()

        results.append({
            "id": pid,
            "time": post_time_utc,
            "time_cst": post_time_cst,
            "ip": ip,
            "port": port,
            "native_loc": native_loc,
            "cf_loc": cf_loc,
        })

    return results


def render(posts: list[dict]) -> str:
    """生成 TXT 内容"""
    # 按发布时间升序（旧→新），保持时间线
    posts = sorted(posts, key=lambda x: x["time"])

    lines: list[str] = []
    for p in posts:
        parts = [f"{p['ip']}:{p['port']}"]
        loc_parts = []
        if p["native_loc"]:
            loc_parts.append(f"原生={p['native_loc']}")
        if p["cf_loc"]:
            loc_parts.append(f"CF={p['cf_loc']}")
        if loc_parts:
            parts.append("#" + " · ".join(loc_parts))
        lines.append("".join(parts))

    if not lines:
        return ""  # 空字符串让上层判断"无变化"
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        html_text = fetch_preview(PREVIEW_URL)
    except Exception as e:
        print(f"[err] failed to fetch {PREVIEW_URL}: {e}", file=sys.stderr)
        return 1

    posts = parse_posts(html_text)
    today_cst = datetime.now(CST).strftime("%Y-%m-%d")
    print(f"[info] today (CST) = {today_cst}, parsed {len(posts)} posts", file=sys.stderr)

    content = render(posts)
    if not content:
        print(f"[warn] no #CF优选IP posts found for {today_cst}, writing empty placeholder", file=sys.stderr)
        # 仍然写入一个空文件（不带 BOM），让 git diff 可以识别"今日无数据"
        OUTPUT.write_text("", encoding="utf-8")
        return 0

    OUTPUT.write_text(content, encoding="utf-8")
    print(f"[done] wrote {len(posts)} entries to {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
