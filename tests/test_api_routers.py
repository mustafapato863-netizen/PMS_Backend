"""
Integration tests for the current API router contracts.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import router as api_router
from models.schemas import Employee as EmployeeSchema


app = FastAPI()
app.include_router(api_router, prefix="/api")
client = TestClient(app)


def _performance_record(employee_id: str = "EMP001", team: str = "Sales", month: str = "January", score: float = 85.5):
    root_cause = MagicMock()
    root_cause.kpi = "booking"
    root_cause.model_dump.return_value = {
        "kpi": "booking",
        "impact_pct": 12.0,
        "actual": 80.0,
        "target": 100.0,
    }
    record = MagicMock()
    record.id = str(uuid4())
    record.employee_id = employee_id
    record.employee_name = "John Doe"
    record.team = team
    record.month = month
    record.region = "UAE"
    record.calls = MagicMock(inbound=10, outbound=0, total_handled=10, abandoned=1, aht_raw="00:05:00")
    record.geo = MagicMock(
        bookings=MagicMock(dubai=1, sharjah=2, ajman=3, clinics=4),
        attended=MagicMock(dubai=1, sharjah=1, ajman=1, clinics=1),
    )
    record.actual = MagicMock(
        booking_rate=0.8,
        attend_rate=0.9,
        abandon_rate=0.1,
        reachability_rate=0.0,
        rejection_rate=0.0,
        initial_error_rate=0.0,
        submission_rate=0.0,
        quality_rate=0.95,
        utz_rate=0.0,
    )
    record.achievement = MagicMock(
        booking_ach=80.0,
        attend_ach=90.0,
        quality_ach=95.0,
        aht_ach=88.0,
        reachability_ach=0.0,
        abandon_ach=90.0,
        rejection_ach=0.0,
        initial_error_ach=0.0,
        submission_ach=0.0,
        op_census_ach=0.0,
        op_revenue_ach=0.0,
        ip_census_ach=0.0,
        ip_revenue_ach=0.0,
        activity_ach=0.0,
    )
    record.evaluation = MagicMock()
    record.evaluation.score = score
    record.evaluation.grade = "B"
    record.evaluation.root_cause = root_cause
    record.evaluation.suggested_action = "Coach"
    record.evaluation.corrective_action = None
    record.evaluation.manager_notes = None
    record.evaluation.planning_category = []
    record.evaluation.trend_status = "Stable"
    record.raw_data = {}
    return record


class TestTeamManagementRouter:
    def test_list_teams_success(self):
        with patch("api.routers.team_management.TeamService.get_all_teams") as mock_get:
            mock_get.return_value = [
                {
                    "id": str(uuid4()),
                    "name": "inbound",
                    "display_name": "Inbound Team",
                    "db_name": "inbound_db",
                    "region": "UAE",
                    "description": "Inbound team",
                    "kpi_keys": ["attendance", "quality"],
                    "kpi_weights": {"attendance": 0.5, "quality": 0.5},
                    "data_source": "Excel",
                    "team_lead": "Ahmed",
                    "team_lead_email": "ahmed@test.com",
                    "is_active": True,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            ]

            response = client.get("/api/team-management/teams")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["active_count"] == 1


class TestEmployeeRouter:
    def test_get_all_employees(self):
        with patch("api.routers.employee.employee_repo.get_all") as mock_get:
            mock_get.return_value = [
                EmployeeSchema(id="EMP001", name="John Doe", team="Sales", region="UAE")
            ]

            response = client.get("/api/employee")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"][0]["id"] == "EMP001"
            assert data["data"][0]["team"] == "Sales"

    def test_search_employees(self):
        with patch("api.routers.employee.employee_repo.get_all") as mock_get:
            mock_get.return_value = [
                EmployeeSchema(id="EMP001", name="John Doe", team="Sales", region="UAE")
            ]

            response = client.get("/api/employee/search", params={"name": "john"})
            assert response.status_code == 200
            assert response.json()["data"][0]["name"] == "John Doe"

    def test_get_employee_profile(self):
        with (
            patch("api.routers.employee.employee_repo.get_all") as mock_employees,
            patch("api.routers.employee.performance_repo.get_all") as mock_records,
            patch("api.routers.employee.actions_repo.get_history") as mock_history,
        ):
            mock_employees.return_value = [
                EmployeeSchema(id="EMP001", name="John Doe", team="Sales", region="UAE")
            ]
            mock_records.return_value = [_performance_record()]
            mock_history.return_value = []

            response = client.get("/api/employee/EMP001")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["employee"]["id"] == "EMP001"
            assert len(data["performance_history"]) == 1

    def test_create_employee(self):
        with patch("api.routers.employee.employee_repo.save") as mock_save:
            response = client.post(
                "/api/employee",
                params={
                    "employee_id": "EMP001",
                    "name": "John Doe",
                    "team": "Sales",
                    "region": "UAE",
                },
                headers={"X-User-Role": "Admin"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["data"]["id"] == "EMP001"
            assert data["data"]["team"] == "Sales"
            mock_save.assert_called_once()

    def test_update_employee(self):
        with (
            patch("api.routers.employee.employee_repo.get_by_id") as mock_get,
            patch("api.routers.employee.employee_repo.save") as mock_save,
        ):
            mock_get.return_value = EmployeeSchema(id="EMP001", name="John Doe", team="Sales", region="UAE")

            response = client.put(
                "/api/employee/EMP001",
                params={"name": "Jane Doe"},
                headers={"X-User-Role": "Admin"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["name"] == "Jane Doe"
            mock_save.assert_called_once()

    def test_delete_employee(self):
        with patch("api.routers.employee.EmployeeService.delete_employee") as mock_delete:
            mock_delete.return_value = (True, [])

            response = client.delete("/api/employee/EMP001", headers={"X-User-Role": "Admin"})
            assert response.status_code == 200
            assert response.json()["success"] is True


class TestPerformanceRouter:
    def test_get_monthly_records(self):
        with patch("api.routers.performance.performance_repo.get_all") as mock_get:
            mock_get.return_value = [_performance_record(team="Sales", month="January")]

            response = client.get("/api/performance/records", params={"team": "Sales", "month": "January"})
            assert response.status_code == 200
            data = response.json()["data"]
            assert len(data) == 1
            assert data[0]["team"] == "Sales"
            assert data[0]["month"] == "January"

    def test_get_employee_history(self):
        with patch("api.routers.performance.performance_repo.get_all") as mock_get:
            mock_get.return_value = [_performance_record(employee_id="EMP001")]

            response = client.get("/api/performance/employee/EMP001")
            assert response.status_code == 200
            assert response.json()["data"][0]["employee_id"] == "EMP001"

    def test_get_team_yearly_records(self):
        with patch("api.routers.performance.performance_repo.get_all") as mock_get:
            mock_get.return_value = [_performance_record(team="Sales")]

            response = client.get("/api/performance/team/Sales")
            assert response.status_code == 200
            assert response.json()["data"][0]["team"] == "Sales"

    def test_get_by_grade(self):
        with patch("api.routers.performance.performance_repo.get_all") as mock_get:
            record = _performance_record(team="Sales", month="January", score=95.0)
            record.evaluation.grade = "A"
            mock_get.return_value = [record]

            response = client.get("/api/performance/grade/Sales", params={"grade": "A", "month": "January"})
            assert response.status_code == 200
            assert response.json()["data"][0]["evaluation"]["grade"] == "A"

    def test_get_by_status(self):
        with patch("api.routers.performance.performance_repo.get_all") as mock_get:
            mock_get.return_value = [_performance_record(team="Sales", month="January", score=85.5)]

            response = client.get("/api/performance/status/Sales", params={"status": "Meets", "month": "January"})
            assert response.status_code == 200
            assert response.json()["data"][0]["evaluation"]["score"] == 85.5


class TestSearchRouter:
    def test_global_search_returns_scoped_teams_and_employee_matches(self):
        employees = [
            EmployeeSchema(id="EMP001", name="John Doe", team="Sales", region="UAE", performance_level="Employee"),
            EmployeeSchema(id="EMP002", name="Jane Roe", team="Inbound", region="UAE", performance_level="Employee"),
        ]
        with (
            patch("api.routers.search.require_authenticated_scope") as mock_scope,
            patch("api.routers.search.employee_repo.get_all") as mock_get_all,
        ):
            mock_scope.return_value = {
                "role": "Manager",
                "accessible_teams": ["Sales"],
                "active_team_names": ["Sales", "Inbound"],
                "is_general_manager": False,
                "employee_id": None,
                "user_id": "manager-1",
            }
            mock_get_all.return_value = employees

            response = client.get("/api/search/global", params={"q": "jo"})

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["teams"] == []
            assert data["employees"] == [
                {
                    "id": "EMP001",
                    "name": "John Doe",
                    "employee_id": "EMP001",
                    "team": "Sales",
                    "performance_level": "Employee",
                }
            ]

    def test_global_search_empty_query_returns_accessible_teams_only(self):
        with patch("api.routers.search.require_authenticated_scope") as mock_scope:
            mock_scope.return_value = {
                "role": "Admin",
                "accessible_teams": [],
                "active_team_names": ["Sales", "Inbound"],
                "is_general_manager": True,
                "employee_id": None,
                "user_id": "admin-1",
            }

            response = client.get("/api/search/global")

            assert response.status_code == 200
            data = response.json()["data"]
            assert [team["name"] for team in data["teams"]] == ["Inbound", "Sales"]
            assert data["employees"] == []


class TestErrorHandling:
    def test_404_error_handling(self):
        with patch("api.routers.employee.employee_repo.get_all") as mock_get:
            mock_get.return_value = []
            response = client.get("/api/employee/nonexistent")
            assert response.status_code == 404

    def test_validation_error_for_missing_query_param(self):
        response = client.get("/api/employee/search")
        assert response.status_code == 422

    def test_500_style_error_returns_standard_response(self):
        with patch("api.routers.employee.employee_repo.get_all") as mock_get:
            mock_get.side_effect = Exception("Database connection error")
            response = client.get("/api/employee")
            assert response.status_code == 200
            assert response.json()["success"] is False


class TestResponseSchemas:
    def test_employee_response_schema(self):
        with patch("api.routers.employee.employee_repo.get_all") as mock_get:
            mock_get.return_value = [
                EmployeeSchema(id="EMP001", name="John Doe", team="Sales", region="UAE")
            ]

            response = client.get("/api/employee")
            data = response.json()
            assert "success" in data
            assert "message" in data
            assert isinstance(data["data"], list)
            emp = data["data"][0]
            assert "id" in emp
            assert "name" in emp
            assert "team" in emp

    def test_performance_response_schema(self):
        with patch("api.routers.performance.performance_repo.get_all") as mock_get:
            mock_get.return_value = [_performance_record()]

            response = client.get("/api/performance/records", params={"month": "January"})
            data = response.json()
            assert "success" in data
            assert "message" in data
            assert isinstance(data["data"], list)
            record = data["data"][0]
            assert "employee_id" in record
            assert "team" in record
            assert "evaluation" in record


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
