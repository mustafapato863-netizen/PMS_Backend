from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import Action
import logging

logger = logging.getLogger(__name__)


class ActionRepository(BaseRepository[Action]):
    """Repository for Action model"""
    
    def get_by_employee(self, employee_id) -> list:
        """Get all actions for employee"""
        return self.db.query(Action).filter(Action.employee_id == employee_id).all()
    
    def get_by_team(self, team_id) -> list:
        """Get all actions for team"""
        return self.db.query(Action).filter(Action.team_id == team_id).all()
    
    def get_by_team_month(self, team_id, month: str, year: int) -> list:
        """Get actions for team in specific month"""
        return self.db.query(Action).filter(
            (Action.team_id == team_id) &
            (Action.month == month) &
            (Action.year == year)
        ).all()
    
    def get_by_status(self, status: str) -> list:
        """Get actions by status"""
        return self.db.query(Action).filter(Action.status == status).all()
    
    def get_by_type(self, action_type: str) -> list:
        """Get actions by type"""
        return self.db.query(Action).filter(Action.action_type == action_type).all()
    
    def get_open_actions(self) -> list:
        """Get all open actions"""
        return self.db.query(Action).filter(
            Action.status.in_(['Open', 'In Progress'])
        ).all()
    
    def count_by_status(self, status: str) -> int:
        """Count actions by status"""
        return self.db.query(Action).filter(Action.status == status).count()
    
    def count_by_type(self, action_type: str) -> int:
        """Count actions by type"""
        return self.db.query(Action).filter(Action.action_type == action_type).count()
    
    def get_employee_actions_month(self, employee_id, month: str, year: int) -> list:
        """Get actions for employee in specific month"""
        return self.db.query(Action).filter(
            (Action.employee_id == employee_id) &
            (Action.month == month) &
            (Action.year == year)
        ).all()
