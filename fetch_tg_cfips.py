#!/usr/bin/env python3
"""
fetch_tg_cfips.py
抓取 Telegram 公开频道 @danfeng2 当天（北京时间）的单 IP 优选帖，
写入 snapshots/YYYY-MM-DD.txt，再合并最近 3 天的快照生成 DSH-TG-CFIPS-DAILY.TXT。

文件结构：
  snapshots/2026-09-12.txt   # 每天一个快照（北京时间日期）
  snapshots/2026-09-13.txt
  snapshots/2026-09-14.txt
  DSH-TG-CFIPS-DAILY.TXT     # = 最近 3 天快照去重合并（同 IP 最新覆盖旧）

格式：
  IP:PORT#原生=Country · State · City · CF=大洲 · Country · City

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
WINDOW_DAYS = 3  # 滑动窗口宽度


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


def parse_all_posts(html_text: str) -> list[dict]:
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

        # 组装成行：IP:PORT#原生=... · CF=...
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
            "raw_line": raw_line,
        })

    return results


def write_snapshot(date_obj, lines: list[str]) -> Path:
    """写 snapshots/YYYY-MM-DD.txt"""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{date_obj.isoformat()}.txt"
    if lines:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        # 写入空文件以"打点"
        path.write_text("", encoding="utf-8")
    return path


def load_snapshot(path: Path) -> list[str]:
    """读快照文件，返回非空行列表"""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln.strip()]


def cleanup_old_snapshots(keep_dates: set) -> list[Path]:
    """删除不在 keep_dates 中的快照文件，返回被删的路径列表"""
    if not SNAPSHOT_DIR.exists():
        return []
    removed = []
    for p in SNAPSHOT_DIR.glob("*.txt"):
        # 文件名形如 2026-09-14.txt
        date_str = p.stem
        try:
            # 简单校验是不是日期
            datetime.fromisoformat(date_str)
        except ValueError:
            continue
        if date_str not in {d.isoformat() for d in keep_dates}:
            p.unlink()
            removed.append(p)
    return removed


def merge_window(main_today: datetime.date) -> tuple[str, dict]:
    """合并最近 WINDOW_DAYS 天的快照（同 IP 去重，最新覆盖旧）"""
    keep_dates = {main_today - timedelta(days=i) for i in range(WINDOW_DAYS)}
    cleanup_old_snapshots(keep_dates)

    # 按日期降序遍历（最新优先）
    sorted_dates = sorted(keep_dates, reverse=True)
    seen_ips: dict[str, str] = {}  # IP -> raw_line（最新的赢）
    counts: dict[str, int] = {}

    for d in sorted_dates:
        path = SNAPSHOT_DIR / f"{d.isoformat()}.txt"
        lines = load_snapshot(path)
        counts[d.isoformat()] = len(lines)
        for line in lines:
            # 取 IP 部分作为去重键（IP:PORT 中的 IP）
            ip_key = line.split(":", 1)[0]
            if ip_key not in seen_ips:
                seen_ips[ip_key] = line

    # 合并后按 IP 排序（便于 diff 稳定）
    merged_lines = sorted(seen_ips.values())
    content = ("\n".join(merged_lines) + "\n") if merged_lines else ""
    return content, {"total": len(merged_lines), "by_date": counts, "kept_dates": [d.isoformat() for d in sorted_dates]}


def main() -> int:
    # 1. 抓预览页
    try:
        html_text = fetch_preview(PREVIEW_URL)
    except Exception as e:
        print(f"[err] failed to fetch {PREVIEW_URL}: {e}", file=sys.stderr)
        return 1

    # 2. 解析所有单 IP 帖
    all_posts = parse_all_posts(html_text)
    print(f"[info] parsed {len(all_posts)} single-IP posts from preview", file=sys.stderr)

    # 3. 按北京时间日期分组
    by_date: dict[str, list[str]] = {}
    for p in all_posts:
        d = p["cst_date"]
        by_date.setdefault(d.isoformat(), []).append(p["raw_line"])
    # 同一天内按 post id 升序（id 大致对应时间）
    for d_str in by_date:
        by_date[d_str].sort()

    # 4. 把所有有数据的日期都写快照（最近 WINDOW_DAYS 天内的）
    today_cst = datetime.now(CST).date()
    keep_dates = {today_cst - timedelta(days=i) for i in range(WINDOW_DAYS)}
    for d in keep_dates:
        lines = by_date.get(d.isoformat(), [])
        write_snapshot(d, lines)
    print(f"[info] today (CST) = {today_cst.isoformat()}, wrote snapshots for {sorted(d.isoformat() for d in keep_dates)}", file=sys.stderr)

    # 5. 合并最近 3 天快照生成主 TXT
    content, info = merge_window(today_cst)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"[info] window {info['kept_dates']}: per-day={info['by_date']}, merged total={info['total']}", file=sys.stderr)
    print(f"[done] wrote {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
