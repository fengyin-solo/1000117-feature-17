"""告警中心业务规则：状态流转、字段校验、筛选口径与值班看板汇总都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["告警编号", "告警类型", "告警等级"]
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
# 值班看板固定的等级口径：紧急在前，交接时从上往下处理；
# 数据里若出现新等级，会追加在矩阵末尾，不打乱既有顺序。
LEVEL_ORDER = ["紧急", "重要", "次要"]
ACTION_RULES = {"确认告警": "已确认", "处置告警": "已处置", "忽略告警": "已忽略"}
NEGATIVE_ACTIONS = ["忽略告警"]
# 交接先办口径：待确认 > 已确认；已处置、已忽略不再占待办。
ACTIVE_STATUSES = ["待确认", "已确认"]
TOP_TYPE_LIMIT = 3


def _text(value: Any) -> str:
    """把字段值统一成去空格的字符串，None/空值都按空串处理。"""
    if value is None:
        return ""
    return str(value).strip()


def _ordered(values: list[str], canonical: list[str]) -> list[str]:
    """按 canonical 既定顺序排列，未收录的值按名称补在末尾。"""
    present = {value for value in values if value}
    ordered = [value for value in canonical if value in present]
    ordered.extend(sorted(present - set(canonical)))
    return ordered


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
        alarm_type: str | None = None,
        device: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter(
            keyword=keyword, status=status, level=level, alarm_type=alarm_type, device=device
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summarize(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
        alarm_type: str | None = None,
        device: str | None = None,
    ) -> dict[str, Any]:
        """值班看板汇总：告警等级 × 处理状态矩阵，加上触发设备最多的告警类型。

        汇总口径与列表完全一致，传入的筛选条件会同时收窄矩阵和榜单，
        保证列表切换等级条件后看板同步变化。
        """
        all_rows = store.rows(MODULE)
        scoped = self._filter(
            keyword=keyword, status=status, level=level, alarm_type=alarm_type, device=device
        )

        matrix = [
            {
                "level": alarm_level,
                "cells": [
                    {
                        "status": alarm_status,
                        "count": sum(
                            1
                            for row in scoped
                            if _text(row.get("告警等级")) == alarm_level
                            and _text(row.get("status")) == alarm_status
                        ),
                    }
                    for alarm_status in STATUS_ORDER
                ],
            }
            for alarm_level in self._level_options(scoped)
        ]
        status_totals = [
            {
                "status": alarm_status,
                "count": sum(
                    1 for row in scoped if _text(row.get("status")) == alarm_status
                ),
            }
            for alarm_status in STATUS_ORDER
        ]

        # 触发设备最多的告警类型：先看去重设备数，设备数相同再比待办量。
        device_sets: dict[str, set[str]] = {}
        active_by_type: dict[str, int] = {}
        total_by_type: dict[str, int] = {}
        for row in scoped:
            type_name = _text(row.get("告警类型"))
            if not type_name:
                continue
            device_name = _text(row.get("触发设备"))
            if device_name:
                device_sets.setdefault(type_name, set()).add(device_name)
            total_by_type[type_name] = total_by_type.get(type_name, 0) + 1
            if _text(row.get("status")) in ACTIVE_STATUSES:
                active_by_type[type_name] = active_by_type.get(type_name, 0) + 1

        ranked = sorted(
            device_sets,
            key=lambda name: (
                -len(device_sets[name]),
                -active_by_type.get(name, 0),
                name,
            ),
        )
        top_types = [
            {
                "type": name,
                "device_count": len(device_sets[name]),
                "alarm_count": total_by_type.get(name, 0),
                "active_count": active_by_type.get(name, 0),
            }
            for name in ranked[:TOP_TYPE_LIMIT]
        ]

        return {
            "levels": self._level_options(scoped),
            "statuses": list(STATUS_ORDER),
            "matrix": matrix,
            "status_totals": status_totals,
            "total": len(scoped),
            "total_all": len(all_rows),
            "active_total": sum(item["count"] for item in status_totals
                                if item["status"] in ACTIVE_STATUSES),
            "top_types": top_types,
            # 下拉选项始终取全量数据，保证筛选后还能切回其他条件。
            "filter_options": {
                "levels": self._level_options(all_rows),
                "types": self._type_options(all_rows),
            },
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
        entry["pending"] = target in ACTIVE_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"告警事件已{action}"

    def _filter(
        self,
        *,
        keyword: str | None,
        status: str | None,
        level: str | None,
        alarm_type: str | None,
        device: str | None,
    ) -> list[dict[str, Any]]:
        """列表与看板共用的筛选口径：编号模糊，状态/等级/类型精确，设备模糊。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword.strip() in _text(row.get("告警编号"))]
        if status:
            rows = [row for row in rows if _text(row.get("status")) == status]
        if level:
            rows = [row for row in rows if _text(row.get("告警等级")) == level]
        if alarm_type:
            rows = [row for row in rows if _text(row.get("告警类型")) == alarm_type]
        if device:
            rows = [row for row in rows if device.strip() in _text(row.get("触发设备"))]
        return rows

    def _level_options(self, rows: list[dict[str, Any]]) -> list[str]:
        return _ordered([_text(row.get("告警等级")) for row in rows], LEVEL_ORDER)

    def _type_options(self, rows: list[dict[str, Any]]) -> list[str]:
        return sorted({_text(row.get("告警类型")) for row in rows if _text(row.get("告警类型"))})
