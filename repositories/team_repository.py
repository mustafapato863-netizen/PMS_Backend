from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import Team
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TeamRepository(BaseRepository[Team]):
    """Repository for Team model"""
    
    def get_by_name(self, name: str) -> Team:
        """Get team by name"""
        return self.db.query(Team).filter(Team.name == name).first()
    
    def get_by_db_name(self, db_name: str) -> Team:
        """Get team by database name"""
        return self.db.query(Team).filter(Team.db_name == db_name).first()
    
    def get_active_teams(self) -> list:
        """Get all active teams"""
        return self.db.query(Team).filter(Team.is_active == True).all()
    
    def get_by_region(self, region: str) -> list:
        """Get teams by region"""
        return self.db.query(Team).filter(Team.region == region).all()
    
    def count_active(self) -> int:
        """Count active teams"""
        return self.db.query(Team).filter(Team.is_active == True).count()
    
    def soft_delete(self, id: any) -> bool:
        """Soft delete (mark as inactive)"""
        team = self.get_by_id(id)
        if team:
            team.is_active = False
            team.updated_at = datetime.now()
            self.db.commit()
            logger.info(f"Soft deleted team: {id}")
            return True
        return False
    
    def restore(self, id: any) -> bool:
        """Restore soft-deleted team"""
        team = self.get_by_id(id)
        if team:
            team.is_active = True
            team.updated_at = datetime.now()
            self.db.commit()
            logger.info(f"Restored team: {id}")
            return True
        return False
