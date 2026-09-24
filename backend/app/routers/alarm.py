"""告警中心接口：维护告警事件，覆盖确认告警、处置告警、忽略告警等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.alarm import AlarmService, LEVEL_ORDER, STATUS_ORDER

router = APIRouter(prefix="/api/alarm", tags=["告警中心"])

service = AlarmService()

LIST_FIELDS = ["告警编号", "告警类型", "告警等级", "触发设备", "触发时间", "处理状态", "处理人"]
STATUSES = STATUS_ORDER
LEVELS = LEVEL_ORDER


class ActionPayload(BaseModel):
    """动作请求体：兼容列表页直传 action 与统一的 values 包裹两种写法。"""

    action: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按告警编号检索"),
    status: str | None = Query(default=None, description="待确认、已确认、已处置、已忽略"),
    level: str | None = Query(default=None, description="紧急、重要、次要、提示"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按告警编号、状态与告警等级过滤告警中心列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"处理状态仅支持：{'、'.join(STATUSES)}",
        )
    if level and level not in LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"告警等级仅支持：{'、'.join(LEVELS)}",
        )
    items, total = service.list_entries(
        keyword=keyword, status=status, level=level, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def board_summary(
    keyword: str | None = Query(default=None, description="按告警编号检索，与列表条件一致"),
    level: str | None = Query(default=None, description="紧急、重要、次要、提示"),
) -> dict[str, Any]:
    """值班看板汇总：返回告警等级×处理状态矩阵，以及触发设备最多的告警类型。"""
    if level and level not in LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"告警等级仅支持：{'、'.join(LEVELS)}",
        )
    return service.board_summary(keyword=keyword, level=level)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条告警事件明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"告警事件 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条告警事件，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="告警事件已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    """对单条告警事件执行确认告警、处置告警、忽略告警；不允许的动作会被拦下并说明原因。"""
    action = str(payload.action or payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出告警中心清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "alarm", "total": total, "items": items}
