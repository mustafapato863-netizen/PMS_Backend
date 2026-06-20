import uuid
from sqlalchemy import Column, String, Integer, SmallInteger, Numeric, Boolean, DateTime, ForeignKey, Text, ForeignKeyConstraint, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

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
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team = relationship("Team", back_populates="employees")
    performance_records = relationship("PerformanceRecord", back_populates="employee")


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
    score = Column(Numeric(6, 2), nullable=False)
    grade = Column(String(5), nullable=False)  # A, B, C, D, E
    status = Column(String(20), nullable=False)  # Exceeds, Meets, Below
    upload_id = Column(UUID(as_uuid=True), ForeignKey("upload_log.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    employee = relationship("Employee", back_populates="performance_records")
    kpi_values = relationship("KPIValue", back_populates="performance_record")


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
    contribution = Column(Numeric(6, 2), nullable=False)

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
    audit_logs = relationship("AuditLog", back_populates="performed_by_user")


class UserTeamAssignment(Base):
    __tablename__ = "user_team_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    access_level = Column(String(20), nullable=False, default="read")  # read, write, admin
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(100), nullable=False)

    # Relationships
    user = relationship("User", back_populates="team_assignments")
    team = relationship("Team")


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
    payload = Column(JSONB, nullable=True)
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
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    performed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(INET, nullable=True)

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