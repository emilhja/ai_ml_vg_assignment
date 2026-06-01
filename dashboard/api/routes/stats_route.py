from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import schema_ready
from ..db import get_db
from ..schemas import DailyFinOpsResponse, StatsResponse, ToolErrorsDrillResponse
from ..services.stats import compute_stats, compute_tool_errors_drill, daily_finops

router = APIRouter(tags=["stats"])


def _db_dep():
    if not schema_ready():
        yield None
        return
    with get_db() as db:
        yield db


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    range: str = Query("7d", pattern="^(today|7d|30d)$"),
    db: Session | None = Depends(_db_dep),
) -> StatsResponse:
    if db is None:
        return StatsResponse(range=range)
    return compute_stats(db, range)


@router.get("/stats/tool-errors", response_model=ToolErrorsDrillResponse)
def get_stats_tool_errors(
    tool: str = Query(..., min_length=1),
    range: str = Query("7d", pattern="^(today|7d|30d)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session | None = Depends(_db_dep),
) -> ToolErrorsDrillResponse:
    if db is None:
        return ToolErrorsDrillResponse(tool=tool, range=range, total=0)
    return compute_tool_errors_drill(db, range, tool, limit=limit, offset=offset)


@router.get("/finops/daily", response_model=DailyFinOpsResponse)
def get_daily_finops() -> DailyFinOpsResponse:
    return daily_finops()
