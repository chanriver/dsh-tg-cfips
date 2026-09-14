#!/usr/bin/env python3
"""
fetch_tg_cfips.py
抓取 Telegram 公开频道 @danfeng2 预览页中**位置最靠前**的 4 条单 IP 优选帖，
按发布时间升序输出到 DSH-TG-CFIPS-DAILY.TXT。

数据源（无需登录）：
  https://t.me/s/danfeng2

为什么"前 4 条"：
- 频道每天大约发 4 条单 IP 帖（间隔 6 小时）
- 抓"位置最靠前"的 4 条 ≈ 抓"最新 4 条"
- 跳过了之前的 CSV 附件、转发、公告等无关消息
- 极大减少解析量（之前要扫 16-20 条，现在只扫前 ~8 条）

格式：
  IP:PORT#原生=Country · State · City · CF=大洲 · Country · City
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
TOP_N = 4  # 只取最靠前的 4 条单 IP 帖
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
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    return "\n".join(lines)


def parse_top_n_posts(html_text: str, n: int) -> list[dict]:
    """
    解析预览页中**按发布时间排序**最新的 n 条单 IP 帖。

    关键点：
    - HTML 里 data-post 出现的顺序就是预览页的视觉顺序（最新在上）
    - 但开头通常是 CSV 附件、转发等非单 IP 帖，不能直接截前 n 条
    - 正确做法：解析所有单 IP 帖 → 按时间倒序 → 取最新 n 条
    - 跳过 CSV 附件、转发、Snippet 公告等
    - 跳过解析失败或不完整的数据

    返回 [{id, time_cst, ip, port, native_loc, cf_loc, raw_line}, ...]
    """
    results: list[dict] = []

    for m in re.finditer(r'data-post="danfeng2/(\d+)"(.*?)(?=data-post="danfeng2/|</section>)', html_text, re.DOTALL):
        pid = m.group(1)
        body = m.group(2)

        # 抓时间
        tm = re.search(r'datetime="([^"]+)"', body)
        if not tm:
            continue
        try:
            post_time_utc = datetime.fromisoformat(tm.group(1).replace("Z", "+00:00"))
        except Exception:
            continue
        post_time_cst = post_time_utc.astimezone(CST)

        # 抓正文
        txt_blocks = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', body, re.DOTALL)
        text = "\n".join(strip_html(b) for b in txt_blocks)

        # 只取 #CF优选IP 单 IP 帖
        if "#CF优选IP" not in text:
            continue
        # 跳过 CSV 附件
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

        # 原生位置
        native_loc = ""
        nat_m = re.search(r"IP原生位置[:：]\s*\n?\s*[└>»\s]*\s*🗺️?\s*([^\n]+)", text)
        if nat_m:
            native_loc = nat_m.group(1).strip()

        # CF 落地位置
        cf_loc = ""
        cf_m = re.search(r"CF落地位置[:：]\s*\n?\s*[└>»\s]*\s*🌐?\s*([^\n]+)", text)
        if cf_m:
            cf_loc = cf_m.group(1).strip()

        # 组装
        parts = [f"{ip}:{port}"]
        loc_parts = []
        if native_loc:
            loc_parts.append(f"原生={native_loc}")
        if cf_loc:
            loc_parts.append(f"CF={cf_loc}")
        if loc_parts:
            parts.append("#" + " · ".join(loc_parts))
        raw_line = "".join(parts)

        results.append({
            "id": pid,
            "time_cst": post_time_cst,
            "raw_line": raw_line,
        })

    # 按发布时间倒序，取最新 n 条
    results.sort(key=lambda x: x["time_cst"], reverse=True)
    top = results[:n]
    # 输出时改回升序（旧→新），与时间线一致
    top.sort(key=lambda x: x["time_cst"])
    return top


def render(posts: list[dict]) -> str:
    """生成 TXT 内容"""
    if not posts:
        return ""
    return "\n".join(p["raw_line"] for p in posts) + "\n"


def main() -> int:
    try:
        html_text = fetch_preview(PREVIEW_URL)
    except Exception as e:
        print(f"[err] failed to fetch {PREVIEW_URL}: {e}", file=sys.stderr)
        return 1

    posts = parse_top_n_posts(html_text, TOP_N)
    today_cst = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    print(f"[info] now (CST) = {today_cst}, fetched {len(posts)}/{TOP_N} top single-IP posts", file=sys.stderr)
    for p in posts:
        print(f"        {p['time_cst'].strftime('%Y-%m-%d %H:%M')}  {p['raw_line']}", file=sys.stderr)

    content = render(posts)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"[done] wrote {len(posts)} entries to {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
