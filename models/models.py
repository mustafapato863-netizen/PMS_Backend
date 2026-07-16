import uuid
from sqlalchemy import Column, String, Integer, SmallInteger, Numeric, Boolean, DateTime, ForeignKey, Text, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Enum as SQLEnum, JSON, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base
from utils.performance_levels import PerformanceLevel


JSON_COMPAT_TYPE = JSON().with_variant(JSONB, "postgresql")
INET_COMPAT_TYPE = String(45).with_variant(INET, "postgresql")

# ============================================================
# 1. CONFIGURATION MODELS
# ============================================================

class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    db_name = Column(String(100), nullable=False, unique=True)
    region = Column(String(10), nullable=False, default="UAE")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    employees = relationship("Employee", back_populates="team")


class TeamKPIConfig(Base):
    __tablename__ = "team_kpi_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    performance_level = Column(String(20), nullable=False, default=PerformanceLevel.EMPLOYEE.value, server_default=PerformanceLevel.EMPLOYEE.value)
    position_name = Column(String(255), nullable=False, default="", server_default="")
    perspective = Column(String(50), nullable=True)
    kpi_key = Column(String(50), nullable=False)
    kpi_label = Column(String(100), nullable=False)
    weight = Column(Numeric(5, 4), nullable=False)
    direction = Column(String(20), nullable=False, default="higher_better")  # maps to enum kpi_direction
    unit = Column(String(20), nullable=False, default="%")
    color = Column(String(20), nullable=False, default="#10B981")
    actual_col = Column(String(100), nullable=False)
    target_col = Column(String(100), nullable=False)
    achievement_col = Column(String(100), nullable=True)
    volume_unit = Column(String(20), nullable=True)
    display_order = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint('team_id', 'performance_level', 'position_name', 'kpi_key', name='uq_kpi_team_level_position_key'),
        CheckConstraint(f"performance_level IN ('{PerformanceLevel.EMPLOYEE.value}', '{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')", name='ck_team_kpi_performance_level'),
        Index('idx_kpi_config_team_level', 'team_id', 'performance_level', 'position_name'),
    )


class ManagementKPIConfig(Base):
    __tablename__ = "management_kpi_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    performance_level = Column(String(20), nullable=False)
    position_name = Column(String(255), nullable=True)
    employee_identifier = Column(String(50), nullable=True)
    perspective_key = Column(String(50), nullable=False)
    kpi_key = Column(String(100), nullable=False)
    kpi_label = Column(String(255), nullable=False)
    direction = Column(String(20), nullable=False, default="higher_better")
    weight = Column(Numeric(7, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=True)
    target_unit = Column(String(20), nullable=True, default="%")
    display_order = Column(SmallInteger, nullable=False, default=0)
    effective_month = Column(String(20), nullable=False)
    effective_year = Column(SmallInteger, nullable=False)
    upload_batch_id = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "performance_level",
            "effective_month",
            "effective_year",
            "position_name",
            "employee_identifier",
            "kpi_key",
            name="uq_management_kpi_config_scope",
        ),
        CheckConstraint(
            f"performance_level IN ('{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')",
            name="ck_management_kpi_config_level",
        ),
        CheckConstraint(
            "((position_name IS NOT NULL AND employee_identifier IS NULL) OR "
            "(position_name IS NULL AND employee_identifier IS NOT NULL))",
            name="ck_management_kpi_config_scope",
        ),
        CheckConstraint("weight > 0", name="ck_management_kpi_config_weight_positive"),
        Index(
            "idx_management_kpi_config_lookup",
            "team_id",
            "performance_level",
            "effective_year",
            "effective_month",
            "position_name",
            "employee_identifier",
        ),
        Index("idx_management_kpi_config_batch", "upload_batch_id"),
    )


class ManagementKPIConfigHistory(Base):
    __tablename__ = "management_kpi_config_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(20), nullable=False, default="replace")
    old_values = Column(JSON_COMPAT_TYPE, nullable=True)
    new_values = Column(JSON_COMPAT_TYPE, nullable=True)
    upload_batch_id = Column(UUID(as_uuid=True), nullable=True)
    source_filename = Column(String(255), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_management_kpi_config_history_team", "team_id", "changed_at"),
        Index("idx_management_kpi_config_history_batch", "upload_batch_id"),
    )


class ManagementKPISnapshot(Base):
    __tablename__ = "management_kpi_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    employee_identifier = Column(String(50), nullable=False)
    employee_name = Column(String(255), nullable=False)
    position_name = Column(String(255), nullable=False)
    performance_level = Column(String(20), nullable=False)
    month = Column(String(20), nullable=False)
    year = Column(SmallInteger, nullable=False)
    perspective_key = Column(String(50), nullable=False)
    kpi_key = Column(String(100), nullable=False)
    kpi_label = Column(String(255), nullable=False)
    actual_value = Column(Numeric(18, 4), nullable=True)
    upload_batch_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "employee_identifier",
            "performance_level",
            "month",
            "year",
            "kpi_key",
            name="uq_management_kpi_snapshot_scope",
        ),
        CheckConstraint(
            f"performance_level IN ('{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')",
            name="ck_management_kpi_snapshot_level",
        ),
        Index(
            "idx_management_kpi_snapshot_lookup",
            "team_id",
            "performance_level",
            "year",
            "month",
        ),
        Index("idx_management_kpi_snapshot_batch", "upload_batch_id"),
    )


# ============================================================
# 2. CORE EMPLOYEES MODEL
# ============================================================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String(50), nullable=False, unique=True)  # From Excel
    name = Column(String(255), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    region = Column(String(10), nullable=False, default="UAE")
    performance_level = Column(String(20), nullable=False, default=PerformanceLevel.EMPLOYEE.value, server_default=PerformanceLevel.EMPLOYEE.value)
    position_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team = relationship("Team", back_populates="employees")
    performance_records = relationship("PerformanceRecord", back_populates="employee")

    __table_args__ = (
        CheckConstraint(f"performance_level IN ('{PerformanceLevel.EMPLOYEE.value}', '{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')", name='ck_employee_performance_level'),
        Index('idx_employee_perf_level', 'performance_level'),
    )


# ============================================================
# 3. PERFORMANCE & LOG MODELS
# ============================================================

class UploadLog(Base):
    __tablename__ = "upload_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    month = Column(String(20), nullable=False)
    year = Column(SmallInteger, nullable=False)
    record_count = Column(Integer, nullable=False, default=0)
    uploaded_by_user_id = Column(UUID(as_uuid=True), nullable=True)  # Linked to users if auth enabled
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())


class PerformanceRecord(Base):
    __tablename__ = "performance_records"

    # Composite Primary Key for Partitioning support
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year = Column(SmallInteger, primary_key=True, nullable=False)  # Partition Key
    
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    month = Column(String(20), nullable=False)
    performance_level = Column(String(20), nullable=False, default=PerformanceLevel.EMPLOYEE.value, server_default=PerformanceLevel.EMPLOYEE.value)
    position_name = Column(String(255), nullable=True)
    region = Column(String(10), nullable=True)
    score = Column(Numeric(6, 2), nullable=False)
    grade = Column(String(5), nullable=False)  # A, B, C, D, E
    status = Column(String(20), nullable=False)  # Exceeds, Meets, Below
    upload_id = Column(UUID(as_uuid=True), ForeignKey("upload_log.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    employee = relationship("Employee", back_populates="performance_records")
    kpi_values = relationship("KPIValue", back_populates="performance_record")

    __table_args__ = (
        CheckConstraint(f"performance_level IN ('{PerformanceLevel.EMPLOYEE.value}', '{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')", name='ck_performance_record_level'),
        Index('idx_perf_record_filters', 'team_id', 'performance_level', 'month', 'year'),
    )


class KPIValue(Base):
    __tablename__ = "kpi_values"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    record_year = Column(SmallInteger, nullable=False)  # Required to match parent composite key
    kpi_key = Column(String(50), nullable=False)
    actual_value = Column(Numeric(18, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=False)
    achievement_ratio = Column(Numeric(10, 4), nullable=False)
    weight_applied = Column(Numeric(5, 4), nullable=False)
    contribution = Column(Numeric(7, 4), nullable=False)

    # Composite Foreign Key constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ['record_id', 'record_year'], 
            ['performance_records.id', 'performance_records.year'], 
            ondelete="CASCADE"
        ),
    )

    # Relationships
    performance_record = relationship("PerformanceRecord", back_populates="kpi_values")


# ============================================================
# 4. AUTHENTICATION & AUTHORIZATION MODELS
# ============================================================

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(50), nullable=False)
    permission = Column(String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint('role', 'permission', name='uq_role_permission'),
    )

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String(50), nullable=True)  # References employees.employee_id
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), nullable=False, default="Viewer")  # Admin, Manager, Executive, Viewer
    is_active = Column(Boolean, nullable=False, default=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team_assignments = relationship("UserTeamAssignment", back_populates="user")
    notifications = relationship("NotificationRecipient", back_populates="user")
    actions_created = relationship("Action", foreign_keys="Action.created_by_user_id", back_populates="created_by_user")
    actions_updated = relationship("Action", foreign_keys="Action.updated_by_user_id", back_populates="updated_by_user")
    # ponytail: keep deletes from loading audit rows when the live DB lags schema updates
    audit_logs = relationship("AuditLog", back_populates="performed_by_user", passive_deletes=True)


class UserTeamAssignment(Base):
    __tablename__ = "user_team_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    performance_level = Column(String(20), nullable=True)
    access_level = Column(String(20), nullable=False, default="read")  # read, write, admin
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(100), nullable=False)

    # Relationships
    user = relationship("User", back_populates="team_assignments")
    team = relationship("Team")

    __table_args__ = (
        CheckConstraint(
            "performance_level IS NULL OR performance_level IN ('Employee', 'Managerial', 'Corporate')",
            name="ck_user_team_assignment_performance_level",
        ),
        Index("idx_user_team_assignment_scope", "user_id", "team_id", "performance_level"),
    )


# ============================================================
# 5. CONFIGURATION - GRADE THRESHOLDS
# ============================================================

class GradeThreshold(Base):
    __tablename__ = "grade_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    grade_a = Column(Numeric(5, 2), nullable=False, default=95)
    grade_b = Column(Numeric(5, 2), nullable=False, default=85)
    grade_c = Column(Numeric(5, 2), nullable=False, default=75)
    grade_d = Column(Numeric(5, 2), nullable=False, default=65)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    # Relationships
    team = relationship("Team")


class KPIWeightHistory(Base):
    __tablename__ = "kpi_weight_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    kpi_key = Column(String(50), nullable=False)
    old_weight = Column(Numeric(5, 4), nullable=False)
    new_weight = Column(Numeric(5, 4), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(100), nullable=False)
    reason = Column(Text, nullable=True)

    # Relationships
    team = relationship("Team")


# ============================================================
# 6. ACTIONS - MANAGER INTERVENTIONS
# ============================================================

class Action(Base):
    __tablename__ = "actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    month = Column(String(20), nullable=False)
    year = Column(SmallInteger, nullable=False)
    action_type = Column(String(50), nullable=False)  # Training, Reward, PIP, Monitor, Coaching, Warning, Promotion
    action_text = Column(Text, nullable=False)
    root_cause_note = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="Open")  # Open, In Progress, Completed, Cancelled
    is_active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    employee = relationship("Employee")
    team = relationship("Team")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="actions_created")
    updated_by_user = relationship("User", foreign_keys=[updated_by_user_id], back_populates="actions_updated")


# ============================================================
# 7. NOTIFICATIONS - MULTI-RECIPIENT
# ============================================================

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)  # data_upload, action_recorded, grade_alert, system, warning
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    room = Column(String(100), nullable=False)  # Socket.io room
    payload = Column(JSON_COMPAT_TYPE, nullable=True)
    link = Column(String(255), nullable=True)  # New column for navigation link
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    recipients = relationship("NotificationRecipient", back_populates="notification")


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = Column(UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    notification = relationship("Notification", back_populates="recipients")
    user = relationship("User", back_populates="notifications")


# ============================================================
# 8. AUDIT LOG - COMPLETE CHANGE TRACKING
# ============================================================

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name = Column(String(100), nullable=False)
    operation = Column(String(50), nullable=False)  # INSERT, UPDATE, DELETE, SOFT_DELETE
    record_id = Column(UUID(as_uuid=True), nullable=True)
    old_values = Column(JSON_COMPAT_TYPE, nullable=True)
    new_values = Column(JSON_COMPAT_TYPE, nullable=True)
    performed_by_user_id = Column("performed_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(INET_COMPAT_TYPE, nullable=True)
    request_id = Column(String(100), nullable=True)

    # Relationships
    performed_by_user = relationship("User", back_populates="audit_logs")


# ============================================================
# 9. ONBOARDING STATE - TEAM SETUP TRACKING
# ============================================================

class OnboardingState(Base):
    __tablename__ = "onboarding_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")  # pending, in_progress, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team = relationship("Team")


class PerformanceRecordVersion(Base):
    __tablename__ = "performance_record_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_record_id = Column(UUID(as_uuid=True), nullable=False)
    original_record_year = Column(SmallInteger, nullable=False)
    version_number = Column(Integer, nullable=False)
    score = Column(Numeric(6, 2), nullable=False)
    grade = Column(String(5), nullable=False)
    status = Column(String(20), nullable=False)
    changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    change_reason = Column(Text, nullable=True)

    # Relationships
    changed_by_user = relationship("User")

    __table_args__ = (
        ForeignKeyConstraint(
            ['original_record_id', 'original_record_year'],
            ['performance_records.id', 'performance_records.year'],
            ondelete="CASCADE"
        ),
        UniqueConstraint('original_record_id', 'version_number', name='uq_record_version'),
    )


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(100), nullable=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    error_class = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
