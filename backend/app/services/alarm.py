"""告警中心业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["告警编号", "告警类型", "告警等级"]
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
ACTION_RULES = {"确认告警": "已确认", "处置告警": "已处置", "忽略告警": "已忽略"}
NEGATIVE_ACTIONS = ["忽略告警"]
# 值班看板固定按紧急程度从高到低排列；数据里出现新等级时追加在后，避免看板缺行。
LEVEL_ORDER = ["紧急", "重要", "次要", "提示"]
TOP_TYPE_LIMIT = 3


class AlarmService:
    def _filter_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        """列表与看板共用一套筛选口径，保证看板数字点下去能和列表对上。"""
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("告警编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if level:
            rows = [row for row in rows if str(row.get("告警等级") or "").strip() == level]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(
            store.rows(MODULE), keyword=keyword, status=status, level=level
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def board_summary(
        self,
        *,
        keyword: str | None = None,
        level: str | None = None,
    ) -> dict[str, Any]:
        """值班看板汇总：等级×处理状态矩阵，以及触发设备最多的告警类型。

        汇总只认告警编号关键字与等级条件（与列表页的条件保持一致）；状态不下钻，
        矩阵每个格子的数字代表该等级该状态下的告警量。
        """
        rows = self._filter_rows(store.rows(MODULE), keyword=keyword, level=level)

        # 固定等级在前、数据里的未知等级追加，矩阵行数保持稳定。
        levels = list(LEVEL_ORDER)
        for row in rows:
            name = str(row.get("告警等级") or "").strip()
            if name and name not in levels:
                levels.append(name)

        matrix: list[dict[str, Any]] = []
        focus: dict[str, Any] | None = None
        for name in levels:
            level_rows = [
                row for row in rows if str(row.get("告警等级") or "").strip() == name
            ]
            counts = {status: 0 for status in STATUS_ORDER}
            for row in level_rows:
                status = str(row.get("status") or "")
                if status in counts:
                    counts[status] += 1
            matrix.append({"level": name, "counts": counts, "total": len(level_rows)})
            # 交接提示：等级从高到低、状态按处置链路找第一个还需跟进的格子；
            # 已处置已经闭环、已忽略明确不跟进，因此只看待确认与已确认。
            if focus is None and level_rows:
                for status in ("待确认", "已确认"):
                    if counts[status] > 0:
                        focus = {"level": name, "status": status, "count": counts[status]}
                        break

        # 同一告警类型按“去重后的触发设备数”排名，并列时比告警总量，再比类型名保证稳定。
        type_stats: dict[str, dict[str, Any]] = {}
        for row in rows:
            alarm_type = str(row.get("告警类型") or "").strip() or "未分类"
            stat = type_stats.setdefault(alarm_type, {"devices": set(), "alarm_count": 0})
            device = str(row.get("触发设备") or "").strip()
            if device:
                stat["devices"].add(device)
            stat["alarm_count"] += 1
        ranked = sorted(
            type_stats.items(),
            key=lambda item: (-len(item[1]["devices"]), -item[1]["alarm_count"], item[0]),
        )
        top_types = [
            {
                "type": name,
                "device_count": len(stat["devices"]),
                "alarm_count": stat["alarm_count"],
            }
            for name, stat in ranked[:TOP_TYPE_LIMIT]
        ]

        return {
            "levels": levels,
            "statuses": list(STATUS_ORDER),
            "matrix": matrix,
            "total": len(rows),
            "top_types": top_types,
            "focus": focus,
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"告警事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于告警中心可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"告警事件已{action}"
