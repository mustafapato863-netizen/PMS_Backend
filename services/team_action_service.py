from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from models.models import Action, Team, User
from repositories.action_repository import ActionRepository
from utils.report_scope import user_can_access_team
from utils.team_identity import logical_team_name


class TeamActionService:
    def __init__(self, db: Session):
        self.db = db
        self.actions = ActionRepository(db)

    def _team(self, reference: str) -> Team:
        normalized = reference.strip().casefold().replace("_", "-")
        teams = self.db.query(Team).filter(Team.is_active.is_(True), Team.team_level == "employee").all()
        for team in teams:
            candidates = {
                str(team.id).casefold(),
                team.name.casefold(),
                team.db_name.casefold(),
                logical_team_name(team).casefold(),
            }
            candidates |= {value.replace(" ", "-").replace("_", "-") for value in candidates}
            if normalized in candidates or reference.strip().casefold() in candidates:
                return team
        raise ValueError("Team not found")

    @staticmethod
    def _serialize(action: Action) -> dict:
        return {
            "team_id": logical_team_name(action.team),
            "month": action.month,
            "year": action.year,
            "overall_action": action.action_text,
            "updated_at": (action.updated_at or action.created_at).isoformat() if (action.updated_at or action.created_at) else None,
            "updated_by": action.updated_by_user.username if action.updated_by_user else "Admin",
        }

    def get(self, *, team_reference: str, month: str, year: int, scope: dict) -> dict | None:
        team = self._team(team_reference)
        team_name = logical_team_name(team)
        if not user_can_access_team(scope, team_name):
            raise PermissionError("The team is outside your authorized action scope")
        action = self.actions.get_active_team_summary(team.id, month, year)
        return self._serialize(action) if action else None

    def save(
        self,
        *,
        team_reference: str,
        month: str,
        year: int,
        overall_action: str,
        scope: dict,
        user_id: str | None,
    ) -> dict:
        team = self._team(team_reference)
        team_name = logical_team_name(team)
        if not user_can_access_team(scope, team_name):
            raise PermissionError("The team is outside your authorized action scope")

        actor_id = None
        try:
            candidate = uuid.UUID(str(user_id)) if user_id else None
            if candidate and self.db.query(User.id).filter(User.id == candidate).first():
                actor_id = candidate
        except (TypeError, ValueError):
            actor_id = None

        try:
            action = self.actions.get_active_team_summary(team.id, month, year)
            if action:
                action.action_text = overall_action.strip()
                action.updated_by_user_id = actor_id
                action.updated_at = dt.datetime.now(dt.timezone.utc)
            else:
                action = Action(
                    team_id=team.id,
                    employee_id=None,
                    month=month,
                    year=year,
                    action_type="Team Action",
                    action_text=overall_action.strip(),
                    status="Open",
                    is_active=True,
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
                self.actions.add(action)
            self.db.commit()
            self.db.refresh(action)
            return self._serialize(action)
        except Exception:
            self.db.rollback()
            raise
