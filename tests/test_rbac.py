"""Role-Based Access Control (RBAC) Tests
"""

import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient

from models.models import Base, User, RolePermission, UserTeamAssignment, Team
from services.permission_seed import seed_role_permissions, PERMISSION_MATRIX
from api.middleware.rbac_middleware import AuthorizationMiddleware, require_permission
from api.middleware.auth_middleware import AuthMiddleware
from services.auth_service import AuthenticationService
from config.database import get_db


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        RolePermission.__table__,
        UserTeamAssignment.__table__,
        Team.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def test_client(db_session):
    """FastAPI TestClient with Auth & RBAC setup"""
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)
    
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    test_app.dependency_overrides[get_db] = override_get_db
    
    @test_app.get("/api/reports")
    async def view_reports_route(user=Depends(require_permission("view_reports"))):
        return {"success": True, "message": "Access granted"}
        
    @test_app.post("/api/users")
    async def manage_users_route(user=Depends(require_permission("manage_users"))):
        return {"success": True, "message": "Access granted"}
        
    @test_app.post("/api/teams/{team_id}/upload")
    async def upload_team_route(team_id: str, user=Depends(require_permission("upload_data"))):
        return {"success": True, "message": "Access granted"}

    client = TestClient(test_app)
    yield client
    test_app.dependency_overrides.clear()


class TestRBACSeeding:
    """Tests for permission seeding logic"""

    def test_seed_role_permissions_empty(self, db_session):
        """Verify seeding adds role permissions to empty DB"""
        assert db_session.query(RolePermission).count() == 0
        seed_role_permissions(db_session)
        
        # Verify seed records count matches PERMISSION_MATRIX
        expected_count = sum(len(perms) for perms in PERMISSION_MATRIX.values())
        assert db_session.query(RolePermission).count() == expected_count
        
        # Verify specific role mapping exists
        admin_view_audit = db_session.query(RolePermission).filter(
            RolePermission.role == "Admin",
            RolePermission.permission == "view_audit_logs"
        ).first()
        assert admin_view_audit is not None

    def test_seed_role_permissions_idempotent(self, db_session):
        """Verify seeding is idempotent (does not duplicate)"""
        seed_role_permissions(db_session)
        count_first = db_session.query(RolePermission).count()
        
        # Run seed again
        seed_role_permissions(db_session)
        count_second = db_session.query(RolePermission).count()
        assert count_first == count_second


class TestRBACPermissionChecks:
    """Tests for AuthorizationMiddleware.check_permission"""

    @pytest.mark.asyncio
    async def test_admin_has_all_permissions(self, db_session):
        """Admin role should pass any permission check, even random ones"""
        user = AuthenticationService.create_user(db_session, "admin_user", "admin@test.com", "SecurePassword123!", "Admin")
        
        # Seed permissions just in case, though Admin doesn't strictly need it in code
        seed_role_permissions(db_session)
        
        assert await AuthorizationMiddleware.check_permission(db_session, str(user.id), "some_arbitrary_permission")

    @pytest.mark.asyncio
    async def test_manager_permissions(self, db_session):
        """Manager has restricted write permissions but not user management"""
        user = AuthenticationService.create_user(db_session, "manager_user", "manager@test.com", "SecurePassword123!", "Manager")
        seed_role_permissions(db_session)
        
        # Allowed
        assert await AuthorizationMiddleware.check_permission(db_session, str(user.id), "upload_data")
        assert await AuthorizationMiddleware.check_permission(db_session, str(user.id), "edit_performance")
        
        # Denied
        assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), "manage_users")
        assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), "delete_team")

    @pytest.mark.asyncio
    async def test_viewer_permissions(self, db_session):
        """Viewer role has only read access"""
        user = AuthenticationService.create_user(db_session, "viewer_user", "viewer@test.com", "SecurePassword123!", "Viewer")
        seed_role_permissions(db_session)
        
        # Allowed
        assert await AuthorizationMiddleware.check_permission(db_session, str(user.id), "view_reports")
        
        # Denied
        assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), "upload_data")
        assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), "edit_performance")

    @pytest.mark.asyncio
    async def test_team_scoped_access(self, db_session):
        """Verify check_permission enforces team assignments for non-admins"""
        # Create user (Manager), team, and team assignments
        user = AuthenticationService.create_user(db_session, "team_manager", "team_mgr@test.com", "SecurePassword123!", "Manager")
        team1 = Team(id=uuid.uuid4(), name="Inbound", db_name="inbound_db", region="UAE")
        team2 = Team(id=uuid.uuid4(), name="Outbound", db_name="outbound_db", region="UAE")
        db_session.add_all([team1, team2])
        db_session.commit()
        
        # Assign user to team1 only
        assignment = UserTeamAssignment(
            id=uuid.uuid4(),
            user_id=user.id,
            team_id=team1.id,
            access_level="write",
            assigned_by="Admin"
        )
        db_session.add(assignment)
        db_session.commit()
        
        # Check permissions with team scopes
        # Permitted on assigned team1
        assert await AuthorizationMiddleware.check_permission(db_session, str(user.id), "upload_data", str(team1.id))
        
        # Denied on unassigned team2
        assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), "upload_data", str(team2.id))


class TestRBACEndpoints:
    """Integration/endpoint verification tests for require_permission"""

    def test_endpoint_permission_allowed(self, test_client, db_session):
        """Verify endpoint access is allowed when user has the permission"""
        user = AuthenticationService.create_user(db_session, "exec_user", "exec@test.com", "SecurePassword123!", "Executive")
        token = AuthenticationService.authenticate_user(db_session, "exec_user", "SecurePassword123!")
        
        # Executive has 'view_reports' permission
        response = test_client.get("/api/reports", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_endpoint_permission_denied(self, test_client, db_session):
        """Verify endpoint returns 403 Forbidden when user lacks permission"""
        user = AuthenticationService.create_user(db_session, "viewer_user", "viewer2@test.com", "SecurePassword123!", "Viewer")
        token = AuthenticationService.authenticate_user(db_session, "viewer_user", "SecurePassword123!")
        
        # Viewer does not have 'manage_users' permission
        response = test_client.post("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert "denied" in response.json()["detail"].lower()
