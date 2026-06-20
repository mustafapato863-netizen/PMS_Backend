"""
Integration Tests for API Routers
Tests all API endpoints with database backend.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from datetime import datetime
from uuid import uuid4

# Import routers
from api.routers import router as api_router

# Create test app
app = FastAPI()
app.include_router(api_router, prefix="/api")

client = TestClient(app)


# ============================================================
# TEAM MANAGEMENT ROUTER TESTS
# ============================================================

class TestTeamManagementRouter:
    """Test Team Management Router"""
    
    def test_list_teams_success(self):
        """Test listing all teams"""
        with patch('api.routers.team_management.TeamService.get_all_teams') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'name': 'inbound',
                    'display_name': 'Inbound Team',
                    'db_name': 'inbound_db',
                    'region': 'UAE',
                    'description': 'Inbound team',
                    'kpi_keys': ['attendance', 'quality'],
                    'kpi_weights': {'attendance': 0.5, 'quality': 0.5},
                    'data_source': 'Excel',
                    'team_lead': 'Ahmed',
                    'team_lead_email': 'ahmed@test.com',
                    'is_active': True,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                }
            ]
            
            response = client.get("/api/team-management/teams")
            
            assert response.status_code == 200
            data = response.json()
            assert data['total'] == 1
            assert data['active_count'] == 1
    
    def test_get_team_success(self):
        """Test getting single team"""
        with patch('api.routers.team_management.TeamService.get_team') as mock_get:
            mock_get.return_value = {
                'id': str(uuid4()),
                'name': 'inbound',
                'display_name': 'Inbound Team',
                'db_name': 'inbound_db',
                'region': 'UAE',
                'description': 'Inbound team',
                'kpi_keys': ['attendance', 'quality'],
                'kpi_weights': {'attendance': 0.5, 'quality': 0.5},
                'data_source': 'Excel',
                'team_lead': 'Ahmed',
                'team_lead_email': 'ahmed@test.com',
                'is_active': True,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            }
            
            response = client.get("/api/team-management/teams/inbound")
            
            assert response.status_code == 200
            data = response.json()
            assert data['name'] == 'inbound'
    
    def test_get_team_not_found(self):
        """Test get team when team doesn't exist"""
        with patch('api.routers.team_management.TeamService.get_team') as mock_get:
            mock_get.return_value = None
            
            response = client.get("/api/team-management/teams/nonexistent")
            
            assert response.status_code == 404
    
    def test_create_team_success(self):
        """Test creating a team"""
        with patch('api.routers.team_management.TeamService.create_team') as mock_create:
            team_id = str(uuid4())
            mock_create.return_value = (
                True,
                {
                    'id': team_id,
                    'name': 'test_team',
                    'display_name': 'Test Team',
                    'db_name': 'test_db',
                    'region': 'UAE',
                    'description': 'Test team',
                    'kpi_keys': [],
                    'kpi_weights': {},
                    'data_source': 'Excel',
                    'team_lead': None,
                    'team_lead_email': None,
                    'is_active': True,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                },
                []
            )
            
            response = client.post(
                "/api/team-management/teams",
                json={
                    "name": "test_team",
                    "display_name": "Test Team",
                    "db_name": "test_db",
                    "region": "UAE"
                }
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data['name'] == 'test_team'
    
    def test_update_team_success(self):
        """Test updating a team"""
        with patch('api.routers.team_management.TeamService.update_team') as mock_update:
            mock_update.return_value = (
                True,
                {
                    'id': str(uuid4()),
                    'name': 'inbound',
                    'display_name': 'Updated Inbound',
                    'db_name': 'inbound_db',
                    'region': 'UAE',
                    'description': 'Inbound team',
                    'kpi_keys': ['attendance', 'quality'],
                    'kpi_weights': {'attendance': 0.5, 'quality': 0.5},
                    'data_source': 'Excel',
                    'team_lead': 'Ahmed',
                    'team_lead_email': 'ahmed@test.com',
                    'is_active': True,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                },
                []
            )
            
            response = client.put(
                "/api/team-management/teams/inbound",
                json={"display_name": "Updated Inbound"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['display_name'] == 'Updated Inbound'
    
    def test_delete_team_success(self):
        """Test deleting a team"""
        with patch('api.routers.team_management.TeamService.delete_team') as mock_delete:
            mock_delete.return_value = (True, [])
            
            response = client.delete("/api/team-management/teams/test_team")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True


# ============================================================
# EMPLOYEE ROUTER TESTS
# ============================================================

class TestEmployeeRouter:
    """Test Employee Router"""
    
    def test_get_all_employees(self):
        """Test getting all employees"""
        with patch('api.routers.employee.EmployeeService.get_all_employees') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': 'EMP001',
                    'name': 'John Doe',
                    'team_id': str(uuid4()),
                    'region': 'UAE',
                    'is_active': True,
                }
            ]
            
            response = client.get("/api/employee")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
            assert len(data['data']) == 1
    
    def test_get_employee_profile(self):
        """Test getting employee profile"""
        emp_id = str(uuid4())
        
        with patch('api.routers.employee.EmployeeService.get_employee') as mock_get, \
             patch('api.routers.employee.performance_repo.get_all') as mock_perf:
            mock_get.return_value = {
                'id': emp_id,
                'employee_id': 'EMP001',
                'name': 'John Doe',
                'team_id': str(uuid4()),
                'region': 'UAE',
                'is_active': True,
            }
            mock_perf.return_value = []
            
            with patch('api.routers.employee.actions_repo.get_history') as mock_hist:
                mock_hist.return_value = []
                
                response = client.get(f"/api/employee/{emp_id}")
                
                assert response.status_code == 200
                data = response.json()
                assert data['success'] == True
                assert 'employee' in data['data']
    
    def test_get_employee_not_found(self):
        """Test get employee when not found"""
        with patch('api.routers.employee.EmployeeService.get_employee') as mock_get:
            mock_get.return_value = None
            
            response = client.get(f"/api/employee/nonexistent")
            
            assert response.status_code == 404
    
    def test_get_employees_by_team(self):
        """Test getting employees by team"""
        team_id = str(uuid4())
        
        with patch('api.routers.employee.EmployeeService.get_employees_by_team') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': 'EMP001',
                    'name': 'John Doe',
                    'team_id': team_id,
                    'region': 'UAE',
                    'is_active': True,
                }
            ]
            
            response = client.get(f"/api/employee/team/{team_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_get_active_employees_by_team(self):
        """Test getting active employees by team"""
        team_id = str(uuid4())
        
        with patch('api.routers.employee.EmployeeService.get_active_employees_by_team') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': 'EMP001',
                    'name': 'John Doe',
                    'team_id': team_id,
                    'region': 'UAE',
                    'is_active': True,
                }
            ]
            
            response = client.get(f"/api/employee/team/{team_id}/active")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_search_employees(self):
        """Test searching employees by name"""
        with patch('api.routers.employee.EmployeeService.search_employees') as mock_search:
            mock_search.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': 'EMP001',
                    'name': 'John Doe',
                    'team_id': str(uuid4()),
                    'region': 'UAE',
                    'is_active': True,
                }
            ]
            
            response = client.get("/api/employee/search?name=John")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_create_employee(self):
        """Test creating an employee"""
        with patch('api.routers.employee.EmployeeService.create_employee') as mock_create:
            emp_id = str(uuid4())
            mock_create.return_value = (
                True,
                {
                    'id': emp_id,
                    'employee_id': 'EMP001',
                    'name': 'John Doe',
                    'team_id': str(uuid4()),
                    'region': 'UAE',
                    'is_active': True,
                },
                []
            )
            
            response = client.post(
                "/api/employee",
                params={
                    "employee_id": "EMP001",
                    "name": "John Doe",
                    "team_id": str(uuid4()),
                    "region": "UAE"
                },
                headers={"X-User-Role": "Admin"}
            )
            
            assert response.status_code == 201 or response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_update_employee(self):
        """Test updating an employee"""
        emp_id = str(uuid4())
        
        with patch('api.routers.employee.EmployeeService.update_employee') as mock_update:
            mock_update.return_value = (
                True,
                {
                    'id': emp_id,
                    'employee_id': 'EMP001',
                    'name': 'Jane Doe',
                    'team_id': str(uuid4()),
                    'region': 'UAE',
                    'is_active': True,
                },
                []
            )
            
            response = client.put(
                f"/api/employee/{emp_id}",
                params={"name": "Jane Doe"},
                headers={"X-User-Role": "Admin"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_delete_employee(self):
        """Test deleting an employee"""
        emp_id = str(uuid4())
        
        with patch('api.routers.employee.EmployeeService.delete_employee') as mock_delete:
            mock_delete.return_value = (True, [])
            
            response = client.delete(
                f"/api/employee/{emp_id}",
                headers={"X-User-Role": "Admin"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True


# ============================================================
# PERFORMANCE ROUTER TESTS
# ============================================================

class TestPerformanceRouter:
    """Test Performance Router"""
    
    def test_get_monthly_records(self):
        """Test getting monthly performance records"""
        team_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.get_monthly_records') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': str(uuid4()),
                    'team_id': team_id,
                    'month': 'January',
                    'year': 2024,
                    'score': 85.5,
                    'grade': 'A',
                    'status': 'Meets',
                }
            ]
            
            response = client.get(
                "/api/performance/records",
                params={"team_id": team_id, "month": "January"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_get_employee_history(self):
        """Test getting employee performance history"""
        emp_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.get_employee_history') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': emp_id,
                    'team_id': str(uuid4()),
                    'month': 'January',
                    'year': 2024,
                    'score': 85.5,
                    'grade': 'A',
                    'status': 'Meets',
                }
            ]
            
            response = client.get(f"/api/performance/employee/{emp_id}/2024")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_get_team_yearly_records(self):
        """Test getting team yearly records"""
        team_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.get_team_yearly_records') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': str(uuid4()),
                    'team_id': team_id,
                    'month': 'January',
                    'year': 2024,
                    'score': 85.5,
                    'grade': 'A',
                    'status': 'Meets',
                }
            ]
            
            response = client.get(f"/api/performance/team/{team_id}/2024")
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_get_by_grade(self):
        """Test getting records by grade"""
        team_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.get_by_grade') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': str(uuid4()),
                    'team_id': team_id,
                    'month': 'January',
                    'year': 2024,
                    'score': 95.0,
                    'grade': 'A',
                    'status': 'Exceeds',
                }
            ]
            
            response = client.get(
                f"/api/performance/grade/{team_id}",
                params={"grade": "A", "month": "January"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_get_by_status(self):
        """Test getting records by status"""
        team_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.get_by_status') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': str(uuid4()),
                    'team_id': team_id,
                    'month': 'January',
                    'year': 2024,
                    'score': 85.5,
                    'grade': 'A',
                    'status': 'Meets',
                }
            ]
            
            response = client.get(
                f"/api/performance/status/{team_id}",
                params={"status": "Meets", "month": "January"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_create_performance_record(self):
        """Test creating a performance record"""
        emp_id = str(uuid4())
        team_id = str(uuid4())
        record_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.create_performance_record') as mock_create:
            mock_create.return_value = (
                True,
                {
                    'id': record_id,
                    'employee_id': emp_id,
                    'team_id': team_id,
                    'month': 'January',
                    'year': 2024,
                    'score': 85.5,
                    'grade': 'A',
                    'status': 'Meets',
                },
                []
            )
            
            response = client.post(
                "/api/performance/records",
                params={
                    "employee_id": emp_id,
                    "team_id": team_id,
                    "month": "January",
                    "year": 2024,
                    "score": 85.5,
                    "grade": "A",
                    "status": "Meets"
                },
                headers={"X-User-Role": "Admin"}
            )
            
            assert response.status_code == 201 or response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_update_performance_record(self):
        """Test updating a performance record"""
        record_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.update_performance_record') as mock_update:
            mock_update.return_value = (
                True,
                {
                    'id': record_id,
                    'employee_id': str(uuid4()),
                    'team_id': str(uuid4()),
                    'month': 'January',
                    'year': 2024,
                    'score': 90.0,
                    'grade': 'A',
                    'status': 'Exceeds',
                },
                []
            )
            
            response = client.put(
                f"/api/performance/records/{record_id}",
                params={"year": 2024, "score": 90.0},
                headers={"X-User-Role": "Admin"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
    
    def test_delete_performance_record(self):
        """Test deleting a performance record"""
        record_id = str(uuid4())
        
        with patch('api.routers.performance.PerformanceService.delete_performance_record') as mock_delete:
            mock_delete.return_value = (True, [])
            
            response = client.delete(
                f"/api/performance/records/{record_id}",
                params={"year": 2024},
                headers={"X-User-Role": "Admin"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True


# ============================================================
# ERROR HANDLING TESTS
# ============================================================

class TestErrorHandling:
    """Test error handling across routers"""
    
    def test_404_error_handling(self):
        """Test 404 error responses"""
        with patch('api.routers.employee.EmployeeService.get_employee') as mock_get:
            mock_get.return_value = None
            
            response = client.get("/api/employee/nonexistent")
            assert response.status_code == 404
    
    def test_400_error_handling(self):
        """Test 400 error responses for invalid input"""
        with patch('api.routers.performance.PerformanceService.get_monthly_records') as mock_get:
            # Missing required parameters
            response = client.get("/api/performance/records")
            
            # This should fail or return 400/422
            assert response.status_code in [400, 422]
    
    def test_500_error_handling(self):
        """Test 500 error handling for database errors"""
        with patch('api.routers.employee.EmployeeService.get_all_employees') as mock_get:
            mock_get.side_effect = Exception("Database connection error")
            
            response = client.get("/api/employee")
            
            assert response.status_code == 200  # Still 200 because we catch and return StandardResponse
            data = response.json()
            assert data['success'] == False


# ============================================================
# RESPONSE SCHEMA TESTS
# ============================================================

class TestResponseSchemas:
    """Test response schemas are correct"""
    
    def test_team_response_schema(self):
        """Test team response schema"""
        with patch('api.routers.team_management.TeamService.get_all_teams') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'name': 'inbound',
                    'display_name': 'Inbound Team',
                    'db_name': 'inbound_db',
                    'region': 'UAE',
                    'description': 'Inbound team',
                    'kpi_keys': ['attendance', 'quality'],
                    'kpi_weights': {'attendance': 0.5, 'quality': 0.5},
                    'data_source': 'Excel',
                    'team_lead': 'Ahmed',
                    'team_lead_email': 'ahmed@test.com',
                    'is_active': True,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                }
            ]
            
            response = client.get("/api/team-management/teams")
            data = response.json()
            
            # Check response structure
            assert 'teams' in data
            assert 'total' in data
            assert 'active_count' in data
            assert 'inactive_count' in data
    
    def test_employee_response_schema(self):
        """Test employee response schema"""
        with patch('api.routers.employee.EmployeeService.get_all_employees') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': 'EMP001',
                    'name': 'John Doe',
                    'team_id': str(uuid4()),
                    'region': 'UAE',
                    'is_active': True,
                }
            ]
            
            response = client.get("/api/employee")
            data = response.json()
            
            # Check response structure
            assert 'success' in data
            assert 'message' in data
            assert 'data' in data
            assert isinstance(data['data'], list)
            if data['data']:
                emp = data['data'][0]
                assert 'id' in emp
                assert 'employee_id' in emp
                assert 'name' in emp
    
    def test_performance_response_schema(self):
        """Test performance response schema"""
        with patch('api.routers.performance.PerformanceService.get_monthly_records') as mock_get:
            mock_get.return_value = [
                {
                    'id': str(uuid4()),
                    'employee_id': str(uuid4()),
                    'team_id': str(uuid4()),
                    'month': 'January',
                    'year': 2024,
                    'score': 85.5,
                    'grade': 'A',
                    'status': 'Meets',
                }
            ]
            
            response = client.get(
                "/api/performance/records",
                params={"team_id": str(uuid4()), "month": "January"}
            )
            data = response.json()
            
            # Check response structure
            assert 'success' in data
            assert 'message' in data
            assert 'data' in data
            assert isinstance(data['data'], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

