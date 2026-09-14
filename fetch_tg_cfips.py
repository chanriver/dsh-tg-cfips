#!/usr/bin/env python3
"""
fetch_tg_cfips.py
抓取 Telegram 公开频道 @danfeng2 当天（北京时间）的单 IP 优选帖，
按发布顺序写到 snapshots/YYYY-MM-DD.txt；合并最近 3 天的快照去重后
生成主订阅文件 DSH-TG-CFIPS-DAILY.TXT。

文件结构：
  snapshots/2026-09-12.txt   # 当天的单 IP 帖（按发布时间升序）
  snapshots/2026-09-13.txt
  snapshots/2026-09-14.txt
  DSH-TG-CFIPS-DAILY.TXT     # = 最近 3 天快照去重合并（同 IP 只保留最新一份）

格式：
  IP:PORT#原生=Country · State · City · CF=大洲 · Country · City

为什么用快照 + 3 天窗口：
- 频道每天发 4 条左右（间隔 6 小时）
- 第一天跑：snapshots 只有 1 份（4 条），主 TXT 4 条
- 第二天跑：snapshots 有 2 份（4+4=8 条），主 TXT 去重后 ≤ 8 条
- 第三天跑：snapshots 有 3 份（≤12 条），主 TXT 累计达 12 条
- 第四天起：每天删最旧的 1 份 + 加 1 份新的，主 TXT 稳定在 10-12 条

数据源（无需登录）：
  https://t.me/s/danfeng2
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
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
OUTPUT = Path(__file__).parent / "DSH-TG-CFIPS-DAILY.TXT"
WINDOW_DAYS = 3


def fetch_preview(url: str, timeout: int = 30) -> str:
    """抓 t.me/s/<channel> 公共预览页 HTML"""
    req = Request(url, headers={"User-Agent": "DSH-TG-CFIPS/1.0 (+https://github.com/chanriver/dsh-tg-cfips)"})
    ctx = create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    return "\n".join(lines)


def parse_single_ip_posts(html_text: str) -> list[dict]:
    """
    解析预览页所有单 IP 帖（不限时间）。
    返回 [{id, time_cst(date), ip, port, native_loc, cf_loc, raw_line}, ...]
    """
    results: list[dict] = []

    for m in re.finditer(r'data-post="danfeng2/(\d+)"(.*?)(?=data-post="danfeng2/|</section>)', html_text, re.DOTALL):
        pid = m.group(1)
        body = m.group(2)

        tm = re.search(r'datetime="([^"]+)"', body)
        if not tm:
            continue
        try:
            post_time_utc = datetime.fromisoformat(tm.group(1).replace("Z", "+00:00"))
        except Exception:
            continue
        post_time_cst = post_time_utc.astimezone(CST)

        txt_blocks = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', body, re.DOTALL)
        text = "\n".join(strip_html(b) for b in txt_blocks)

        if "#CF优选IP" not in text:
            continue
        title = re.search(r'tgme_widget_message_document_title[^>]*>(.*?)</div>', body, re.DOTALL)
        if title and ".csv" in title.group(1).lower():
            continue

        ip_m = re.search(r"IP地址[:：]\s*((?:\d{1,3}\.){3}\d{1,3})", text)
        if not ip_m:
            continue
        ip = ip_m.group(1)
        if not all(0 <= int(p) <= 255 for p in ip.split(".")):
            continue

        port_m = re.search(r"端口[:：]\s*(\d{1,5})", text)
        if not port_m:
            continue
        port = port_m.group(1)

        native_loc = ""
        nat_m = re.search(r"IP原生位置[:：]\s*\n?\s*[└>»\s]*\s*🗺️?\s*([^\n]+)", text)
        if nat_m:
            native_loc = nat_m.group(1).strip()

        cf_loc = ""
        cf_m = re.search(r"CF落地位置[:：]\s*\n?\s*[└>»\s]*\s*🌐?\s*([^\n]+)", text)
        if cf_m:
            cf_loc = cf_m.group(1).strip()

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
            "cst_date": post_time_cst.date(),
            "time_cst": post_time_cst,
            "raw_line": raw_line,
        })

    return results


def write_snapshot(date_obj, posts: list[dict]) -> Path:
    """写 snapshots/YYYY-MM-DD.txt（同一天内按发布时间升序）"""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{date_obj.isoformat()}.txt"
    posts_sorted = sorted(posts, key=lambda x: x["time_cst"])
    if posts_sorted:
        content = "\n".join(p["raw_line"] for p in posts_sorted) + "\n"
    else:
        content = ""
    path.write_text(content, encoding="utf-8")
    return path


def load_snapshot(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def cleanup_old_snapshots(keep_dates: set) -> list[Path]:
    """删除不在 keep_dates 中的快照"""
    if not SNAPSHOT_DIR.exists():
        return []
    removed = []
    keep_strs = {d.isoformat() for d in keep_dates}
    for p in SNAPSHOT_DIR.glob("*.txt"):
        try:
            datetime.fromisoformat(p.stem)
        except ValueError:
            continue
        if p.stem not in keep_strs:
            p.unlink()
            removed.append(p)
    return removed


def merge_window(today: datetime.date) -> tuple[str, dict]:
    """合并最近 WINDOW_DAYS 天的快照（同 IP 去重，最新覆盖旧）"""
    keep_dates = {today - timedelta(days=i) for i in range(WINDOW_DAYS)}
    cleanup_old_snapshots(keep_dates)

    sorted_dates = sorted(keep_dates, reverse=True)  # 最新→最旧
    seen: dict[str, str] = {}  # IP -> raw_line
    counts: dict[str, int] = {}

    for d in sorted_dates:
        path = SNAPSHOT_DIR / f"{d.isoformat()}.txt"
        lines = load_snapshot(path)
        counts[d.isoformat()] = len(lines)
        for line in lines:
            ip_key = line.split(":", 1)[0]
            if ip_key not in seen:
                seen[ip_key] = line

    merged_lines = sorted(seen.values())
    content = ("\n".join(merged_lines) + "\n") if merged_lines else ""
    return content, {"total": len(merged_lines), "by_date": counts, "kept_dates": [d.isoformat() for d in sorted_dates]}


def main() -> int:
    try:
        html_text = fetch_preview(PREVIEW_URL)
    except Exception as e:
        print(f"[err] failed to fetch {PREVIEW_URL}: {e}", file=sys.stderr)
        return 1

    all_posts = parse_single_ip_posts(html_text)
    print(f"[info] parsed {len(all_posts)} single-IP posts from preview", file=sys.stderr)

    # 按北京时间日期分组
    by_date: dict[object, list[dict]] = {}
    for p in all_posts:
        by_date.setdefault(p["cst_date"], []).append(p)

    today_cst = datetime.now(CST).date()
    keep_dates = {today_cst - timedelta(days=i) for i in range(WINDOW_DAYS)}

    # 把最近 3 天内的所有日期都写快照
    for d in keep_dates:
        write_snapshot(d, by_date.get(d, []))
    per_day = {d.isoformat(): len(by_date.get(d, [])) for d in keep_dates}
    print(f"[info] today (CST) = {today_cst.isoformat()}, wrote snapshots per-day={per_day}", file=sys.stderr)

    # 合并生成主 TXT
    content, info = merge_window(today_cst)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"[info] window {info['kept_dates']}: per-day={info['by_date']}, merged total={info['total']}", file=sys.stderr)
    print(f"[done] wrote {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
