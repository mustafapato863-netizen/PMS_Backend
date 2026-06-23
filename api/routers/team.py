import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Dict

from api.middleware.rbac_middleware import require_permission
from models.schemas import StandardResponse, TeamAction
from repositories.json_repos import JSONTeamActionsRepository

router = APIRouter()

@router.get("/", response_model=StandardResponse)
async def get_team_action(
    team_id: str = Query(...),
    month: str = Query(...)
):
    try:
        action_repo = JSONTeamActionsRepository()
        act = action_repo.get_action(team_id, month)
        return StandardResponse(
            success=True,
            message="Team action retrieved successfully",
            data=act.model_dump() if act else None
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")

@router.post("/", response_model=StandardResponse)
async def save_team_action(
    payload: Dict[str, str],
    _user=Depends(require_permission("create_actions"))
):
    try:
        team_id = payload.get("team_id", "")
        month = payload.get("month", "")
        overall_action = payload.get("overall_action", "")
        if not team_id or not month:
            raise HTTPException(status_code=400, detail="team_id and month are required")
        
        action_repo = JSONTeamActionsRepository()
        act = TeamAction(
            team_id=team_id,
            month=month,
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
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")
