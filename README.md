# DSH-TG-CFIPS

每天北京时间 23:00 自动从 Telegram 公开频道 **[@danfeng2](https://t.me/danfeng2)** 抓取最近 **3 天**的 Cloudflare 优选 IP，**带地理位置标注**（IP 原生位置 + CF 落地位置），滑动窗口自动更新。

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

## 数据源与窗口策略

- [Telegram 公开频道 @danfeng2](https://t.me/danfeng2)（"CF代理，中转IP分享"，4.7K 订阅）
- 通过 `https://t.me/s/danfeng2` 公共预览页抓取（**无需登录、无需 Telegram API key**）
- 每天保留最近 **3 天**（北京时间）的单 IP 帖
- 同 IP 在多天出现时，**最新一天的覆盖旧天的**（去重 + 覆盖）
- 跳过 CSV 附件、转发广告、Snippet 公告等其他类型消息

> 💡 **时区说明**：虽然频道时间戳后缀是 `+00:00`（UTC），但发贴节奏按北京时间（每天 12:00/18:00/00:00/06:00 北京），所以"当天"按**北京时间**判定，与频道作息一致。

### 为什么是 3 天？
- 频道每天发 4 条左右（间隔 6 小时）
- 3 天窗口 = 12 条左右，订阅源大小可控
- 旧天自动清理，避免仓库无限膨胀
- 测试显示 3 天实际得到 **10~12 条**（少量去重后）

## 自动更新

- GitHub Actions 每天 **北京时间 23:00**（UTC 15:00）跑一次
  - 此时当天北京时间的全部单 IP 帖都已发布
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
├── DSH-TG-CFIPS-DAILY.TXT         # 订阅源（最近 3 天，自动生成）
├── snapshots/                     # 每日快照（北京时间日期）
│   ├── 2026-09-12.txt
│   ├── 2026-09-13.txt
│   └── 2026-09-14.txt
├── fetch_tg_cfips.py              # 抓取脚本
├── .github/workflows/             # GitHub Actions 配置
└── README.md
```

`snapshots/` 下的历史快照**仅保留最近 3 天**，过期文件自动删除。需要追溯更早历史请直接 clone git 历史。
