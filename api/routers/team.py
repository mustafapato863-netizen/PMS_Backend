import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Any, Dict
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_scope
from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.models import Team
from models.schemas import StandardResponse, TeamAction
from repositories.json_repos import JSONTeamActionsRepository
from utils.report_scope import user_can_access_team
from utils.team_identity import logical_team_name

router = APIRouter()


def _logical_team(db: Session, team_id: str) -> str:
    normalized = team_id.strip().casefold().replace("_", "-")
    for team in db.query(Team).filter(Team.is_active.is_(True)).all():
        candidates = {str(team.id).casefold(), team.name.casefold(), team.db_name.casefold(), logical_team_name(team).casefold()}
        candidates |= {value.replace(" ", "-").replace("_", "-") for value in candidates}
        if normalized in candidates or team_id.strip().casefold() in candidates:
            return logical_team_name(team)
    raise HTTPException(status_code=404, detail="Team not found")


def _authorize_team(db: Session, request: Request, team_id: str) -> None:
    team_name = _logical_team(db, team_id)
    scope = get_current_user_scope(db, request)
    if not user_can_access_team(scope, team_name):
        raise HTTPException(status_code=403, detail="The team is outside your authorized action scope")

@router.get("/", response_model=StandardResponse)
async def get_team_action(
    request: Request,
    team_id: str = Query(...),
    month: str = Query(...),
    year: int | None = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_actions")),
):
    try:
        _authorize_team(db, request, team_id)
        action_repo = JSONTeamActionsRepository()
        act = action_repo.get_action(team_id, month, year)
        return StandardResponse(
            success=True,
            message="Team action retrieved successfully",
            data=act.model_dump() if act else None
        )
    except HTTPException:
        raise
    except Exception:
        return StandardResponse(success=False, message="Failed to load teams.")

@router.post("/", response_model=StandardResponse)
async def save_team_action(
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("create_actions"))
):
    try:
        team_id = payload.get("team_id", "")
        month = payload.get("month", "")
        overall_action = payload.get("overall_action", "")
        year = int(payload["year"]) if payload.get("year") is not None else None
        if not team_id or not month:
            raise HTTPException(status_code=400, detail="team_id and month are required")
        _authorize_team(db, request, team_id)
        
        action_repo = JSONTeamActionsRepository()
        act = TeamAction(
            team_id=team_id,
            month=month,
            year=year,
            overall_action=overall_action,
            updated_at=datetime.datetime.now().isoformat(),
            updated_by="Admin"
        )
        action_repo.save(act)
        return StandardResponse(
            success=True,
            message="Team action saved successfully",
            data=act.model_dump()
        )
    except HTTPException:
        raise
    except Exception:
        return StandardResponse(success=False, message="Failed to load team performance.")
