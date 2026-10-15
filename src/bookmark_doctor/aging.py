"""长期未访问画像（M5，plan/04 §4.1）。

口径 [冻结草案]：浏览器不导出真实访问记录，以 ``add_date``（添加时间）
**近似** "未访问时长"——代理指标，报告必须显式注明，不得表述为实测。

- 分档阈值取 ruleset ``aging.tiers_days``（引擎零内联、零默认值：
  缺失/非法 → ``AgingConfigError``，与 probe 参数纪律一致）；
  tiers_days = [365, 730, 1095] → "1年+ / 2年+ / 3年+"（其余为 1年内）；
  档位标签由阈值换算（days // tiers_days[0]），不写死年份字面量；
- ``add_date=None`` 的条目**不参与分档**，单列 "添加时间未知" 计数
  （"缺失不猜补" 口径）；
- 分档判定用 ``aging_date``（由调用方传入的参考日期，如探测日期）与
  add_date 的日历日差——不用 ``time.time()``，保产物确定性（K18）。
"""

_AGING_KEY = "aging"
_TIERS_KEY = "tiers_days"

# 分档标签模板：N 年+（N 由 tiers_days 换算，非字面量内联）
_TIER_LABEL_YEARS = "%d年+"
_TIER_LABEL_WITHIN = "1年内"


class AgingConfigError(ValueError):
    """ruleset ``aging.tiers_days`` 缺失/非法（引擎零默认值纪律）。"""


def load_aging_tiers(ruleset):
    """ruleset dict → 升序 int 分档天数列表（空/非升序/非正 int → AgingConfigError）。"""
    aging = ruleset.get(_AGING_KEY)
    if not isinstance(aging, dict):
        raise AgingConfigError("ruleset 缺少 aging 对象")
    tiers = aging.get(_TIERS_KEY)
    if not isinstance(tiers, list) or not tiers:
        raise AgingConfigError("ruleset 缺少 aging.tiers_days（非空列表）")
    for value in tiers:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise AgingConfigError("aging.tiers_days 含非正整数项: %r" % (value,))
    if any(b <= a for a, b in zip(tiers, tiers[1:])):
        raise AgingConfigError("aging.tiers_days 必须严格升序: %r" % (tiers,))
    return list(tiers)


def _days_between(aging_date, add_date):
    """(date, epoch 秒) → 相差的整天数；add_date 早于参考日为正。"""
    from datetime import date, datetime, timezone

    moment = datetime.fromtimestamp(add_date, tz=timezone.utc).date()
    return (aging_date - moment).days


def build_aging_profile(bookmarks, tiers_days, aging_date):
    """UIR 条目 + 分档阈值 + 参考日 → 画像（计数 + 逐条分档归属）。

    返回::

        {
          "as_of_date": "YYYY-MM-DD",   // 参考日（确定性，无时钟）
          "tiers": [                     // 按 tiers_days 升序
            {"tier": "1年+", "min_days": 365, "count": N, "ids": [...]}
          ],
          "within": {"tier": "1年内", "count": N, "ids": [...]},
          "unknown_add_date": {"count": N, "ids": [...]},
          "note": "以添加时间近似未访问；浏览器不导出真实访问记录",
        }
    """
    from datetime import date

    if not isinstance(aging_date, date):
        raise TypeError("aging_date 须为 datetime.date（确定性参考日）")
    tiers = []
    year_base = tiers_days[0]  # 年份标签以首档为基准换算（阈值本身取 ruleset）
    for days in tiers_days:
        tiers.append(
            {
                "tier": _TIER_LABEL_YEARS % (days // year_base),
                "min_days": days,
                "count": 0,
                "ids": [],
            }
        )
    within = {"tier": _TIER_LABEL_WITHIN, "count": 0, "ids": []}
    unknown = {"count": 0, "ids": []}
    for bm in bookmarks:
        add_date = bm.get("add_date")
        if add_date is None:
            unknown["count"] += 1
            unknown["ids"].append(bm["id"])
            continue
        age = _days_between(aging_date, add_date)
        placed = False
        # 分档取"满足的最高档"（2年+ 的条目不得落 1年+）：从高档往低档判。
        for index in range(len(tiers_days) - 1, -1, -1):
            if age >= tiers_days[index]:
                tiers[index]["count"] += 1
                tiers[index]["ids"].append(bm["id"])
                placed = True
                break
        if not placed:
            within["count"] += 1
            within["ids"].append(bm["id"])
    return {
        "as_of_date": aging_date.isoformat(),
        "tiers": tiers,
        "within": within,
        "unknown_add_date": unknown,
        "note": "以添加时间近似未访问；浏览器不导出真实访问记录",
    }
