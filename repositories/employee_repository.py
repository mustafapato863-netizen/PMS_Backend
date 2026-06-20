from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import Employee
import logging

logger = logging.getLogger(__name__)


class EmployeeRepository(BaseRepository[Employee]):
    """Repository for Employee model"""
    
    def get_by_employee_id(self, employee_id: str) -> Employee:
        """Get employee by external employee ID"""
        return self.db.query(Employee).filter(Employee.employee_id == employee_id).first()
    
    def get_by_team(self, team_id) -> list:
        """Get all employees in team"""
        return self.db.query(Employee).filter(Employee.team_id == team_id).all()
    
    def get_active_by_team(self, team_id) -> list:
        """Get active employees in team"""
        return self.db.query(Employee).filter(
            (Employee.team_id == team_id) &
            (Employee.is_active == True)
        ).all()
    
    def count_by_team(self, team_id) -> int:
        """Count employees in team"""
        return self.db.query(Employee).filter(Employee.team_id == team_id).count()
    
    def get_by_region(self, region: str) -> list:
        """Get employees by region"""
        return self.db.query(Employee).filter(Employee.region == region).all()
    
    def count_active(self) -> int:
        """Count all active employees"""
        return self.db.query(Employee).filter(Employee.is_active == True).count()
    
    def search_by_name(self, name: str) -> list:
        """Search employees by name (case insensitive)"""
        return self.db.query(Employee).filter(
            Employee.name.ilike(f"%{name}%")
        ).all()
