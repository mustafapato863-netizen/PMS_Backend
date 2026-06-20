"""Role-Based Access Control Permission Seeder
Seeds the role_permissions table with the enterprise permission matrix.
"""

import logging
import uuid
from sqlalchemy.orm import Session
from models.models import RolePermission

logger = logging.getLogger(__name__)

# Permission definitions mapped to enterprise roles
PERMISSION_MATRIX = {
    "Admin": [
        "create_team", "delete_team", "edit_team_config",
        "upload_data", "edit_performance", "delete_performance",
        "view_reports", "export_data", "manage_users",
        "manage_permissions", "view_audit_logs", "restore_data",
        "manage_batch_operations", "configure_kpi",
        "manage_alerts", "view_system_metrics"
    ],
    "Manager": [
        "upload_data", "edit_performance", "view_reports",
        "export_data", "manage_team_members", "view_actions",
        "create_actions", "manage_team_kpi"
    ],
    "Executive": [
        "view_reports", "export_data", "view_aggregated_analytics",
        "view_audit_logs"
    ],
    "Viewer": [
        "view_reports"
    ]
}


def seed_role_permissions(db: Session) -> None:
    """
    Seeds the role_permissions table if it is currently empty.
    Useful for application initialization.
    """
    try:
        # Check if already seeded
        count = db.query(RolePermission).count()
        if count > 0:
            logger.info("Role permissions table is already populated. Skipping seeding.")
            return

        logger.info("🌱 Seeding role permissions matrix...")
        seeded_count = 0
        for role, permissions in PERMISSION_MATRIX.items():
            for perm in permissions:
                role_perm = RolePermission(
                    id=uuid.uuid4(),
                    role=role,
                    permission=perm
                )
                db.add(role_perm)
                seeded_count += 1
        
        db.commit()
        logger.info(f"🌱 Seeded {seeded_count} role permission mapping(s).")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed role permissions: {e}")
        # We don't raise here to prevent startup crash, but log error
