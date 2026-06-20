"""
Comprehensive Service Tests
Testing service implementations with mocking.
"""

import pytest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from services.team_service import TeamService
from services.employee_service import EmployeeService
from services.performance_service import PerformanceService


# ============================================================
# TEAM SERVICE TESTS
# ============================================================

class TestTeamService:
    """Test suite for TeamService."""

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_all_teams(self, mock_session_local, mock_team_repo):
        """Test getting all teams."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        
        mock_team = MagicMock()
        mock_team.id = uuid.uuid4()
        mock_team.name = 'test_team'
        mock_team.db_name = 'test_team_db'
        mock_team.region = 'UAE'
        mock_team.is_active = True
        mock_team.created_at = datetime.now()
        mock_team.updated_at = datetime.now()
        
        mock_repo_instance.get_all.return_value = [mock_team]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        teams = TeamService.get_all_teams()
        
        # Verify
        assert len(teams) > 0
        assert teams[0]['name'] == 'test_team'
        mock_session.close.assert_called_once()

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_team(self, mock_session_local, mock_team_repo):
        """Test getting a single team."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        
        mock_team = MagicMock()
        mock_team.id = uuid.uuid4()
        mock_team.name = 'test_team'
        mock_team.db_name = 'test_team_db'
        mock_team.region = 'UAE'
        mock_team.is_active = True
        mock_team.created_at = datetime.now()
        mock_team.updated_at = datetime.now()
        
        mock_repo_instance.get_by_name.return_value = mock_team
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        team = TeamService.get_team('test_team')
        
        # Verify
        assert team is not None
        assert team['name'] == 'test_team'
        mock_session.close.assert_called_once()

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_team_not_found(self, mock_session_local, mock_team_repo):
        """Test getting non-existent team."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        mock_repo_instance.get_by_name.return_value = None
        
        # Execute
        team = TeamService.get_team('nonexistent')
        
        # Verify
        assert team is None
        mock_session.close.assert_called_once()

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_team_statistics(self, mock_session_local, mock_team_repo):
        """Test getting team statistics."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        
        mock_team = MagicMock()
        mock_team.region = 'UAE'
        
        mock_repo_instance.get_all.return_value = [mock_team]
        mock_repo_instance.get_active_teams.return_value = [mock_team]
        mock_session.query.return_value.all.return_value = []
        
        # Execute
        stats = TeamService.get_team_statistics()
        
        # Verify
        assert 'total_teams' in stats
        assert 'active_teams' in stats


# ============================================================
# EMPLOYEE SERVICE TESTS
# ============================================================

class TestEmployeeService:
    """Test suite for EmployeeService."""

    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_get_all_employees(self, mock_session_local, mock_emp_repo):
        """Test getting all employees."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_emp_repo.return_value = mock_repo_instance
        
        mock_emp = MagicMock()
        mock_emp.id = uuid.uuid4()
        mock_emp.employee_id = 'EMP001'
        mock_emp.name = 'John Doe'
        mock_emp.team_id = uuid.uuid4()
        mock_emp.region = 'UAE'
        mock_emp.is_active = True
        mock_emp.created_at = datetime.now()
        mock_emp.updated_at = datetime.now()
        mock_emp.team = None
        
        mock_repo_instance.get_all.return_value = [mock_emp]
        
        # Execute
        employees = EmployeeService.get_all_employees()
        
        # Verify
        assert len(employees) > 0
        assert employees[0]['employee_id'] == 'EMP001'
        mock_session.close.assert_called_once()

    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_get_employee_by_uuid(self, mock_session_local, mock_emp_repo):
        """Test getting employee by UUID."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_emp_repo.return_value = mock_repo_instance
        
        test_id = uuid.uuid4()
        mock_emp = MagicMock()
        mock_emp.id = test_id
        mock_emp.employee_id = 'EMP001'
        mock_emp.name = 'John Doe'
        mock_emp.team_id = uuid.uuid4()
        mock_emp.region = 'UAE'
        mock_emp.is_active = True
        mock_emp.created_at = datetime.now()
        mock_emp.updated_at = datetime.now()
        mock_emp.team = None
        
        mock_repo_instance.get_by_id.return_value = mock_emp
        
        # Execute
        emp = EmployeeService.get_employee(str(test_id))
        
        # Verify
        assert emp is not None
        assert emp['employee_id'] == 'EMP001'
        mock_session.close.assert_called_once()

    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_create_employee(self, mock_session_local, mock_emp_repo):
        """Test creating a new employee."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_emp_repo_instance = MagicMock()
        mock_emp_repo.return_value = mock_emp_repo_instance
        
        from services.employee_service import TeamRepository
        with patch('services.employee_service.TeamRepository') as mock_team_repo:
            mock_team_repo_instance = MagicMock()
            mock_team_repo.return_value = mock_team_repo_instance
            
            mock_team = MagicMock()
            mock_team.id = uuid.uuid4()
            mock_team.name = 'test_team'
            
            mock_team_repo_instance.get_by_id.return_value = mock_team
            mock_emp_repo_instance.get_by_employee_id.return_value = None
            
            mock_new_emp = MagicMock()
            mock_new_emp.id = uuid.uuid4()
            mock_new_emp.employee_id = 'EMP002'
            mock_new_emp.name = 'Jane Doe'
            mock_new_emp.team_id = mock_team.id
            mock_new_emp.region = 'UAE'
            mock_new_emp.is_active = True
            
            mock_emp_repo_instance.create.return_value = mock_new_emp
            
            # Execute
            success, emp_dict, errors = EmployeeService.create_employee(
                employee_id='EMP002',
                name='Jane Doe',
                team_id=mock_team.id,
                region='UAE'
            )
            
            # Verify
            assert success is True
            assert len(errors) == 0
            assert emp_dict['employee_id'] == 'EMP002'


# ============================================================
# PERFORMANCE SERVICE TESTS
# ============================================================

class TestPerformanceService:
    """Test suite for PerformanceService."""

    @patch('services.performance_service.PerformanceRepository')
    @patch('services.performance_service.SessionLocal')
    def test_get_monthly_records(self, mock_session_local, mock_perf_repo):
        """Test getting monthly performance records."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_perf_repo.return_value = mock_repo_instance
        
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.employee_id = uuid.uuid4()
        mock_record.team_id = uuid.uuid4()
        mock_record.month = 'January'
        mock_record.year = 2024
        mock_record.score = 85.5
        mock_record.grade = 'B'
        mock_record.status = 'Meets'
        mock_record.uploaded_at = datetime.now()
        
        mock_repo_instance.get_monthly_records.return_value = [mock_record]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        records = PerformanceService.get_monthly_records(
            mock_record.team_id,
            'January',
            2024
        )
        
        # Verify
        assert len(records) > 0
        assert records[0]['month'] == 'January'
        mock_session.close.assert_called_once()

    @patch('services.performance_service.PerformanceRepository')
    @patch('services.performance_service.SessionLocal')
    def test_get_employee_history(self, mock_session_local, mock_perf_repo):
        """Test getting employee performance history."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_perf_repo.return_value = mock_repo_instance
        
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.employee_id = uuid.uuid4()
        mock_record.team_id = uuid.uuid4()
        mock_record.month = 'January'
        mock_record.year = 2024
        mock_record.score = 85.5
        mock_record.grade = 'B'
        mock_record.status = 'Meets'
        mock_record.uploaded_at = datetime.now()
        
        mock_repo_instance.get_employee_history.return_value = [mock_record]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        records = PerformanceService.get_employee_history(
            mock_record.employee_id,
            2024
        )
        
        # Verify
        assert len(records) > 0
        mock_session.close.assert_called_once()


# ============================================================
# ERROR HANDLING TESTS
# ============================================================

class TestErrorHandling:
    """Test error handling across services."""

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_team_service_handles_missing_team(self, mock_session_local, mock_team_repo):
        """Test that TeamService handles missing team gracefully."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        mock_repo_instance.get_by_name.return_value = None
        
        # Execute
        team = TeamService.get_team('nonexistent_team')
        
        # Verify
        assert team is None

    @patch('services.performance_service.PerformanceRepository')
    @patch('services.performance_service.SessionLocal')
    def test_performance_service_handles_missing_record(self, mock_session_local, mock_perf_repo):
        """Test that PerformanceService handles missing record gracefully."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_perf_repo.return_value = mock_repo_instance
        mock_repo_instance.get_by_id.return_value = None
        
        # Execute
        success, errors = PerformanceService.delete_performance_record(
            uuid.uuid4(),
            2024
        )
        
        # Verify
        assert success is False
        assert len(errors) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

