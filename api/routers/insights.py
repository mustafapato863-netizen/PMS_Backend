from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from api.dependencies import performance_repo, planning_service, require_authenticated_scope, require_role
from config.database import get_db
from models.insight_schemas import InsightsWorkspaceResponse
from services.insights_service import InsightAccessError, InsightValidationError, InsightsService


router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("/workspace", response_model=InsightsWorkspaceResponse)
def get_insights_workspace(
    request: Request,
    db: Session = Depends(get_db),
    month: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    region: str | None = Query(default=None),
    team: str | None = Query(default=None),
    performance_level: str | None = Query(default=None),
    position: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    kpi: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    insight_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    _role: str = Depends(require_role(["Admin", "Manager", "Executive"])),
):
    if bool(month) != bool(year):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Month and year must be selected together",
        )
    scope = require_authenticated_scope(db, request)
    try:
        workspace = InsightsService(
            performance_repo,
            planning_service,
            db=db,
        ).generate_workspace(
            scope,
            month=month,
            year=year,
            region=region,
            team=team,
            performance_level=performance_level,
            position=position,
            employee_id=employee_id,
            kpi=kpi,
            severity=severity,
            insight_type=insight_type,
            insight_status=status_filter,
        )
    except InsightAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InsightValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return InsightsWorkspaceResponse(success=True, message="Authorized insights generated", data=workspace)
