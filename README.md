# DSH-TG-CFIPS

每天北京时间 23:00 自动从 Telegram 公开频道 **[@danfeng2](https://t.me/danfeng2)** 抓取最近 **3 天**的 Cloudflare 优选 IP，**带地理位置标注**（IP 原生位置 + CF 落地位置）。

## 订阅地址

```
https://raw.githubusercontent.com/chanriver/dsh-tg-cfips/main/DSH-TG-CFIPS-DAILY.TXT
```

## 文件格式

每行一条记录：

```
IP:PORT#原生=Country · State · City · CF=大洲 · Country · City
```

示例：

```
147.78.246.169:22658#原生=Japan · Tokyo · Tokyo · CF=亚太 · 日本东京
```

字段说明：
| 字段 | 含义 |
|------|------|
| `IP:PORT` | Cloudflare 反向代理入口，端口来自频道原帖（**非默认 443**） |
| `原生=` | IP 注册地（whois 数据库层面），例如 `United States · California · Los Angeles` |
| `CF=` | Cloudflare 数据中心实际"落地"位置，例如 `北美洲 · 美国洛杉矶` |

> ⚠️ **使用建议**：CF 节点选择器（v2ray/xray/clash 插件等）通常按 `CF=` 字段筛选，因为代理访问的实际出口是 Cloudflare 数据中心，不是 IP 注册地。

## 数据源

- [Telegram 公开频道 @danfeng2](https://t.me/danfeng2)（"CF代理，中转IP分享"，4.7K 订阅）
- 通过 `https://t.me/s/danfeng2` 公共预览页抓取（**无需登录、无需 Telegram API key**）
- 跳过 CSV 附件、转发广告、Snippet 公告等其他类型消息

## 累积式 3 天窗口

主订阅文件 `DSH-TG-CFIPS-DAILY.TXT` 由**最近 3 天的每日快照**合并去重而成。频道每天约发 4 条，所以：

| 跑第几次 | 当天日期 | 快照数 | 主 TXT 总数 |
|---------|---------|-------|------------|
| 第 1 次 | D1 | 1 份 (4 条) | **4 条** |
| 第 2 次 | D2 | 2 份 (8 条) | **≤ 8 条** |
| 第 3 次 | D3 | 3 份 (≤12 条) | **≤ 12 条** ← 稳定 |
| 第 4 次 | D4 | 仍 3 份（删 D1 加 D4） | 仍 ≤ 12 条 |

> 实际数量略少于 4×3=12，因为：
> - 同 IP 多日出现会去重
> - 偶尔频道少发

## 自动更新

- GitHub Actions 每天 **北京时间 23:00**（UTC 15:00）跑一次
  - cron 表达式：`0 15 * * *`
- 内容有变化才 commit + push
- 也支持手动触发：Actions 页 → `Update DSH-TG-CFIPS` → `Run workflow`

## 本地运行

```bash
python3 fetch_tg_cfips.py
```

依赖：仅 Python 3.8+ 标准库。

## 相关项目

- [dsh-cloudflare-ips](https://github.com/chanriver/dsh-cloudflare-ips) — 来自 uouin.com 和 wetest.vip 的批量优选 IP（电信+多线 IPv4）

## 筛选规则速查

| 帖子类型 | 是否抓取 |
|----------|----------|
| `#CF优选IP` 单 IP 帖 | ✅ |
| CSV 附件帖 | ❌ |
| Snippet/XHTTP 公告 | ❌ |
| 转发广告 | ❌ |

## 文件结构

```
.
├── DSH-TG-CFIPS-DAILY.TXT         # 订阅源（最近 3 天累计，自动生成）
├── snapshots/                     # 每日快照（北京时间日期，最多 3 份）
│   ├── 2026-09-12.txt
│   ├── 2026-09-13.txt
│   └── 2026-09-14.txt
├── fetch_tg_cfips.py              # 抓取脚本
├── .github/workflows/             # GitHub Actions 配置
└── README.md
```

`snapshots/` 下的历史快照**仅保留最近 3 天**，过期文件自动删除。需要追溯更早历史请直接 clone git 历史。
