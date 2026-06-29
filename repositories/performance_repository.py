from sqlalchemy.orm import Session, selectinload
from repositories.base_repository import BaseRepository
from models.models import PerformanceRecord, Employee, Team
import logging

logger = logging.getLogger(__name__)


class PerformanceRepository(BaseRepository[PerformanceRecord]):
    """Repository for PerformanceRecord model"""

    def get_dashboard_record_keys(
        self,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
    ) -> list[tuple[str, str, str]]:
        """Return lightweight dashboard record identifiers filtered in SQL."""
        query = self.db.query(
            Employee.employee_id,
            Team.name,
            PerformanceRecord.month,
        ).join(
            Employee, PerformanceRecord.employee_id == Employee.id
        ).join(
            Team, PerformanceRecord.team_id == Team.id
        )

        if team:
            query = query.filter(Team.name == team)
        if month:
            query = query.filter(PerformanceRecord.month == month)
        if employee_id:
            query = query.filter(Employee.employee_id == employee_id)
        if grade:
            query = query.filter(PerformanceRecord.grade == grade)
        if status:
            query = query.filter(PerformanceRecord.status == status)
        if performance_level:
            query = query.filter(PerformanceRecord.performance_level == performance_level)

        return [
            (str(emp_id), str(team_name), str(record_month))
            for emp_id, team_name, record_month in query.distinct().all()
        ]

    def get_by_employee_month(self, employee_id, month: str, year: int):
        """Get performance record for specific month"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.employee_id == employee_id) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).first()
    
    def get_monthly_records(self, team_id, month: str, year: int) -> list:
        """Get all records for team in specific month"""
        return self.db.query(PerformanceRecord).options(
            selectinload(PerformanceRecord.kpi_values)
        ).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
    
    def get_employee_history(self, employee_id, year: int) -> list:
        """Get all records for employee in year"""
        return self.db.query(PerformanceRecord).options(
            selectinload(PerformanceRecord.kpi_values)
        ).filter(
            (PerformanceRecord.employee_id == employee_id) &
            (PerformanceRecord.year == year)
        ).order_by(PerformanceRecord.month).all()
    
    def get_team_yearly_records(self, team_id, year: int) -> list:
        """Get all records for team in year"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.year == year)
        ).all()
    
    def count_by_grade(self, team_id, grade: str, month: str, year: int) -> int:
        """Count records by grade"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.grade == grade) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).count()
    
    def get_by_grade(self, team_id, grade: str, month: str, year: int) -> list:
        """Get records by grade"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.grade == grade) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
    
    def get_by_status(self, team_id, status: str, month: str, year: int) -> list:
        """Get records by status"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.status == status) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
