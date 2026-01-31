import enum
from typing import List, Optional
from datetime import datetime, date
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    Text,
    ForeignKey,
    Enum,
    Index,
    func,
    UniqueConstraint,
    CheckConstraint,
    Date,
)
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from .custom_types import StringUUID


class Base(DeclarativeBase):
    pass


# Enums
class UserType(enum.Enum):
    STUDENT = "student"
    STAFF = "staff"


class EnrollmentStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    GRADUATED = "graduated"


class SubmissionStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"


class VerificationType(enum.Enum):
    MANUAL = "manual"
    AGENT = "agent"


class ActorType(enum.Enum):
    USER = "user"
    SYSTEM = "system"
    SCHEDULED = "scheduled"


class Priority(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ChannelType(enum.Enum):
    IN_APP = "in_app"
    LINE_APP = "line_app"


class TemplateFormat(enum.Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


class NotificationStatus(enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    EXPIRED = "expired"


class ProgReqRecurrenceType(enum.Enum):
    ONCE = "once"
    ANNUAL = "annual"


class SubmissionTiming(enum.Enum):
    ON_TIME = "on_time"
    LATE = "late"
    OVERDUE = "overdue"


# Base model with common audit fields
class AuditMixin:
    """Mixin for common audit fields"""

    created_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.getutcdate(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.getutcdate(), onupdate=func.getutcdate()
    )


# Models
class User(Base, AuditMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    username: Mapped[str] = mapped_column(
        String(320), unique=True
    )  # RFC 5321 max length
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_type: Mapped[UserType] = mapped_column(Enum(UserType), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DATETIME2)

    # Relationships
    student: Mapped[Optional["Student"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    staff: Mapped[Optional["Staff"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notification_recipients: Mapped[List["NotificationRecipient"]] = relationship(
        back_populates="recipient", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_type_active", "user_type", "is_active"),
        Index("idx_users_last_login", "last_login"),
    )


class AcademicYear(Base, AuditMixin):
    __tablename__ = "academic_years"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    year_code: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DATETIME2, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DATETIME2, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    students: Mapped[List["Student"]] = relationship(back_populates="academic_year")
    requirement_schedules: Mapped[List["ProgramRequirementSchedule"]] = relationship(
        back_populates="academic_year"
    )
    dashboard_stats: Mapped[List["DashboardStats"]] = relationship(
        back_populates="academic_year"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "end_date > start_date", name="ck_academic_years_end_after_start"
        ),
        Index("idx_academic_years_year_code", "year_code"),
        Index("idx_academic_years_is_current", "is_current"),
        Index("idx_academic_years_dates", "start_date", "end_date"),
    )


class CertificateType(Base, AuditMixin):
    __tablename__ = "certificate_types"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    cert_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    cert_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    has_expiration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    program_requirements: Mapped[List["ProgramRequirement"]] = relationship(
        back_populates="certificate_type"
    )
    certificate_submissions: Mapped[List["CertificateSubmission"]] = relationship(
        back_populates="certificate_type"
    )
    dashboard_stats: Mapped[List["DashboardStats"]] = relationship(
        back_populates="certificate_type"
    )

    # Constraints
    __table_args__ = (
        Index("idx_certificate_types_cert_code", "cert_code"),
        Index("idx_certificate_types_is_active", "is_active"),
    )


class NotificationType(Base, AuditMixin):
    __tablename__ = "notification_types"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    default_priority: Mapped[Priority] = mapped_column(
        Enum(Priority), default=Priority.MEDIUM, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    channel_templates: Mapped[List["NotificationChannelTemplate"]] = relationship(
        back_populates="notification_type", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        back_populates="notification_type"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "code", name="uq_notification_types_entity_code"
        ),
        Index("idx_notification_types_code", "code"),
        Index("idx_notification_types_entity_type", "entity_type"),
        Index("idx_notification_types_is_active", "is_active"),
    )


# LINE API access token management
class LineChannelAccessToken(Base, AuditMixin):
    __tablename__ = "line_channel_access_tokens"

    key_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    access_token: Mapped[str] = mapped_column(String(500), nullable=False)
    token_type: Mapped[str] = mapped_column(
        String(20), default="Bearer", nullable=False
    )
    expires_in: Mapped[int] = mapped_column(Integer, nullable=False)  # seconds
    expires_at: Mapped[datetime] = mapped_column(DATETIME2, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DATETIME2)

    # Constraints
    __table_args__ = (
        Index("idx_line_tokens_active", "is_active", "expires_at"),
        Index("idx_line_tokens_expires_at", "expires_at"),
        CheckConstraint("expires_in > 0", name="ck_line_tokens_expires_in_positive"),
        CheckConstraint(
            "revoked_at IS NULL OR is_revoked = 1",
            name="ck_line_tokens_revoked_consistency",
        ),
    )


class Program(Base, AuditMixin):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    program_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    program_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_years: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    students: Mapped[List["Student"]] = relationship(back_populates="program")
    program_requirements: Mapped[List["ProgramRequirement"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    dashboard_stats: Mapped[List["DashboardStats"]] = relationship(
        back_populates="program"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("duration_years > 0", name="ck_programs_duration_positive"),
        Index("idx_programs_code", "program_code"),
        Index("idx_programs_is_active", "is_active"),
    )


class ProgramRequirement(Base, AuditMixin):
    __tablename__ = "program_requirements"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    program_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("programs.id", ondelete="NO ACTION"),
        nullable=False,
    )
    cert_type_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("certificate_types.id", ondelete="NO ACTION"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    grace_period_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    special_instruction: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recurrence_type: Mapped[ProgReqRecurrenceType] = mapped_column(
        Enum(ProgReqRecurrenceType),
        default=ProgReqRecurrenceType.ANNUAL,
        nullable=False,
    )
    last_recurrence_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.getutcdate(), nullable=False
    )
    notification_days_before_deadline: Mapped[int] = mapped_column(
        Integer, default=90, nullable=False
    )
    effective_from_year: Mapped[Optional[int]] = mapped_column(Integer)
    effective_until_year: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # Up to this academic year
    months_before_deadline: Mapped[Optional[int]] = mapped_column(Integer, default=1)

    # Relationships
    program: Mapped["Program"] = relationship(back_populates="program_requirements")
    certificate_type: Mapped["CertificateType"] = relationship(
        back_populates="program_requirements"
    )
    requirement_schedules: Mapped[List["ProgramRequirementSchedule"]] = relationship(
        back_populates="program_requirement", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "program_id",
            "cert_type_id",
            "target_year",
            name="uq_program_req_prog_cert_year",
        ),
        CheckConstraint("target_year >= 1", name="ck_program_req_target_year_pos"),
        CheckConstraint(
            "YEAR(deadline_date) = 2000",
            name="ck_program_req_deadline_year_2000",
        ),
        Index("idx_program_req_program_id", "program_id"),
        Index("idx_program_req_cert_type_id", "cert_type_id"),
        Index("idx_program_req_prog_active", "program_id", "is_active"),
        CheckConstraint(
            "months_before_deadline IS NULL OR (months_before_deadline >= 1 AND months_before_deadline <= 6)",
            name="ck_program_req_months_range",
        ),
    )


class ProgramRequirementSchedule(Base, AuditMixin):
    """Academic year-specific deadlines for program requirements"""

    __tablename__ = "program_requirement_schedules"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    program_requirement_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("program_requirements.id", ondelete="CASCADE"),
        nullable=False,
    )
    academic_year_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("academic_years.id", ondelete="NO ACTION"),
        nullable=False,
    )
    submission_deadline: Mapped[datetime] = mapped_column(DATETIME2, nullable=False)
    grace_period_deadline: Mapped[datetime] = mapped_column(DATETIME2, nullable=False)
    start_notify_at: Mapped[datetime] = mapped_column(DATETIME2, nullable=False)
    last_notified_at: Mapped[datetime] = mapped_column(DATETIME2, nullable=True)

    # Relationships
    program_requirement: Mapped["ProgramRequirement"] = relationship(
        back_populates="requirement_schedules"
    )
    academic_year: Mapped["AcademicYear"] = relationship(
        back_populates="requirement_schedules"
    )
    certificate_submissions: Mapped[List["CertificateSubmission"]] = relationship(
        back_populates="requirement_schedule"
    )
    dashboard_stats: Mapped[List["DashboardStats"]] = relationship(
        back_populates="requirement_schedule", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "program_requirement_id",
            "academic_year_id",
            name="uq_req_sched_req_year",
        ),
        Index("idx_req_sched_academic_year", "academic_year_id"),
        Index("idx_req_sched_deadline", "submission_deadline"),
        Index("idx_req_sched_program_req", "program_requirement_id"),
    )


class Staff(Base, AuditMixin):
    __tablename__ = "staff"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    user_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,  # One-to-one relationship
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="staff")

    # Constraints
    __table_args__ = (Index("idx_staff_user_id", "user_id"),)


class Student(Base, AuditMixin):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    user_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,  # One-to-one relationship
        nullable=False,
    )
    sit_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    student_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    program_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("programs.id", ondelete="NO ACTION"),
        nullable=False,
    )
    academic_year_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("academic_years.id", ondelete="NO ACTION"),
        nullable=False,
    )
    line_application_id: Mapped[Optional[str]] = mapped_column(String(100))
    enrollment_status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus), default=EnrollmentStatus.ACTIVE, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="student")
    program: Mapped["Program"] = relationship(back_populates="students")
    academic_year: Mapped["AcademicYear"] = relationship(back_populates="students")
    certificate_submissions: Mapped[List["CertificateSubmission"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        Index(
            "idx_students_line_application_id",
            "line_application_id",
            unique=True,
            mssql_where="line_application_id IS NOT NULL",
        ),
        Index("idx_students_user_id", "user_id"),
        Index("idx_students_program_id", "program_id"),
        Index("idx_students_academic_year_id", "academic_year_id"),
        Index("idx_students_enrollment_status", "enrollment_status"),
        Index("idx_students_student_id", "student_id"),
    )


class CertificateSubmission(Base, AuditMixin):
    __tablename__ = "certificate_submissions"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    student_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    cert_type_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("certificate_types.id", ondelete="NO ACTION"),
        nullable=False,
    )
    requirement_schedule_id: Mapped[Optional[str]] = mapped_column(
        StringUUID,
        ForeignKey("program_requirement_schedules.id", ondelete="SET NULL"),
    )
    file_object_name: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.PENDING, nullable=False
    )
    submission_timing: Mapped[SubmissionTiming] = mapped_column(
        Enum(SubmissionTiming), default=SubmissionTiming.ON_TIME, nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.getutcdate(), nullable=False
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(DATETIME2)

    # Relationships
    student: Mapped["Student"] = relationship(back_populates="certificate_submissions")
    certificate_type: Mapped["CertificateType"] = relationship(
        back_populates="certificate_submissions"
    )
    requirement_schedule: Mapped["ProgramRequirementSchedule"] = relationship(
        back_populates="certificate_submissions"
    )
    verification_history: Mapped[List["VerificationHistory"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "cert_type_id",
            "requirement_schedule_id",
            name="uq_cert_sub_student_cert_sched",
        ),
        CheckConstraint("file_size > 0", name="ck_cert_sub_file_size_positive"),
        CheckConstraint(
            "expired_at IS NULL OR expired_at > submitted_at",
            name="ck_cert_sub_expired_after_submitted",
        ),
        Index("idx_cert_sub_student_id", "student_id"),
        Index("idx_cert_sub_cert_type_id", "cert_type_id"),
        Index("idx_cert_sub_req_sched_id", "requirement_schedule_id"),
        Index("idx_cert_sub_submission_status", "submission_status"),
        Index("idx_cert_sub_submission_timing", "submission_timing"),
        Index("idx_cert_sub_submitted_at", "submitted_at"),
        Index("idx_cert_sub_expired_at", "expired_at"),
    )


class VerificationHistory(Base, AuditMixin):
    __tablename__ = "verification_history"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    submission_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("certificate_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    verifier_id: Mapped[Optional[str]] = mapped_column(StringUUID)
    verification_type: Mapped[VerificationType] = mapped_column(
        Enum(VerificationType), nullable=False
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), nullable=False
    )
    comments: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    submission: Mapped["CertificateSubmission"] = relationship(
        back_populates="verification_history"
    )

    # Constraints
    __table_args__ = (
        Index("idx_verif_hist_submission_id", "submission_id"),
        Index("idx_verif_hist_verifier_id", "verifier_id"),
        Index("idx_verif_hist_verification_type", "verification_type"),
        Index("idx_verif_hist_created_at", "created_at"),
    )


class Notification(Base, AuditMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    notification_type_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("notification_types.id", ondelete="NO ACTION"),
        nullable=False,
    )
    entity_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(StringUUID)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority), default=Priority.MEDIUM, nullable=False
    )
    # JSON stored as Text - serialize/deserialize in application
    notification_metadata: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DATETIME2)

    # Relationships
    notification_type: Mapped["NotificationType"] = relationship(
        back_populates="notifications"
    )
    recipients: Mapped[List["NotificationRecipient"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_notif_expires_after_created",
        ),
        CheckConstraint(
            "scheduled_for IS NULL OR scheduled_for >= created_at",
            name="ck_notif_scheduled_not_before_created",
        ),
        Index("idx_notif_entity_type", "entity_id", "notification_type_id"),
        Index("idx_notif_created_at", "created_at"),
        Index("idx_notif_scheduled_for", "scheduled_for"),
        Index("idx_notif_expires_at", "expires_at"),
        Index("idx_notif_priority", "priority"),
        Index("idx_notif_actor", "actor_type", "actor_id"),
    )


class NotificationChannelTemplate(Base, AuditMixin):
    __tablename__ = "notification_channel_templates"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    notification_type_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("notification_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_type: Mapped[ChannelType] = mapped_column(Enum(ChannelType), nullable=False)
    template_subject: Mapped[Optional[str]] = mapped_column(String(500))
    template_body: Mapped[str] = mapped_column(Text, nullable=False)
    template_format: Mapped[TemplateFormat] = mapped_column(
        Enum(TemplateFormat), default=TemplateFormat.TEXT, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    notification_type: Mapped["NotificationType"] = relationship(
        back_populates="channel_templates"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "notification_type_id",
            "channel_type",
            name="uq_notif_chan_templ_type_chan",
        ),
        Index("idx_notif_chan_templ_notif_type", "notification_type_id"),
        Index("idx_notif_chan_templ_channel_type", "channel_type"),
        Index("idx_notif_chan_templ_is_active", "is_active"),
    )


class NotificationRecipient(Base, AuditMixin):
    __tablename__ = "notification_recipients"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    notification_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id: Mapped[str] = mapped_column(
        StringUUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    line_app_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus), default=NotificationStatus.PENDING, nullable=False
    )
    # delivered_at will be set when the notification for this recipient is processed by the notification processing task
    # for each delivery channel, such as line, the corresponding sent_at will be set from the channel's delivery task
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    read_at: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    line_app_sent_at: Mapped[Optional[datetime]] = mapped_column(DATETIME2)

    # Relationships
    notification: Mapped["Notification"] = relationship(back_populates="recipients")
    recipient: Mapped["User"] = relationship(back_populates="notification_recipients")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "recipient_id",
            name="uq_notif_recip_notif_recip",
        ),
        CheckConstraint(
            "read_at IS NULL OR read_at >= delivered_at",
            name="ck_notif_recip_read_after_delivered",
        ),
        Index("idx_notif_recip_notification_id", "notification_id"),
        Index("idx_notif_recip_recipient_id", "recipient_id"),
        Index("idx_notif_recip_status", "status"),
        Index("idx_notif_recip_status_created", "status", "created_at"),
        Index("idx_notif_recip_recipient_status", "recipient_id", "status"),
    )


class DashboardStats(Base, AuditMixin):
    __tablename__ = "dashboard_stats"

    id: Mapped[str] = mapped_column(
        StringUUID,
        primary_key=True,
        server_default=func.newid(),
    )
    requirement_schedule_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("program_requirement_schedules.id", ondelete="NO ACTION"),
        nullable=False,
    )
    program_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("programs.id", ondelete="NO ACTION"),
        nullable=False,
    )
    academic_year_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("academic_years.id", ondelete="NO ACTION"),
        nullable=False,
    )
    cert_type_id: Mapped[str] = mapped_column(
        StringUUID,
        ForeignKey("certificate_types.id", ondelete="NO ACTION"),
        nullable=False,
    )
    total_submissions_required: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    # submitted_count includes approved_count, rejected_count, pending_count, and manual_review_count
    submitted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    not_submitted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    on_time_submissions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    late_submissions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overdue_submissions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_verification_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    agent_verification_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_calculated_at: Mapped[datetime] = mapped_column(
        DATETIME2,
        server_default=func.getutcdate(),
        onupdate=func.getutcdate(),
        nullable=False,
    )

    # Relationships
    requirement_schedule: Mapped["ProgramRequirementSchedule"] = relationship(
        back_populates="dashboard_stats"
    )
    academic_year: Mapped["AcademicYear"] = relationship(
        back_populates="dashboard_stats"
    )
    program: Mapped["Program"] = relationship(back_populates="dashboard_stats")
    certificate_type: Mapped["CertificateType"] = relationship(
        back_populates="dashboard_stats"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "requirement_schedule_id", name="uq_dashboard_stats_req_sched"
        ),
        CheckConstraint(
            "submitted_count = approved_count + rejected_count + pending_count + manual_review_count",
            name="ck_dashboard_stats_submitted_consistency",
        ),
        CheckConstraint(
            "total_submissions_required = submitted_count + not_submitted_count",
            name="ck_dashboard_stats_total_consistency",
        ),
        CheckConstraint(
            "submitted_count = on_time_submissions + late_submissions",
            name="ck_dashboard_stats_timing_consistency",
        ),
        Index("idx_dashboard_stats_req_sched", "requirement_schedule_id"),
        Index("idx_dashboard_stats_program_id", "program_id"),
        Index("idx_dashboard_stats_academic_year_id", "academic_year_id"),
        Index("idx_dashboard_stats_cert_type_id", "cert_type_id"),
        Index("idx_dashboard_stats_created_at", "created_at"),
        Index("idx_dashboard_stats_last_calculated_at", "last_calculated_at"),
        Index("idx_dashboard_stats_prog_acad_year", "program_id", "academic_year_id"),
        Index("idx_dashboard_stats_prog_cert_type", "program_id", "cert_type_id"),
        Index("idx_dashboard_stats_acad_year_cert", "academic_year_id", "cert_type_id"),
        Index(
            "idx_dashboard_stats_prog_year_cert",
            "program_id",
            "academic_year_id",
            "cert_type_id",
        ),
        Index("idx_dashboard_stats_overdue_submissions", "overdue_submissions"),
        Index("idx_dashboard_stats_pending_count", "pending_count"),
        Index("idx_dashboard_stats_manual_review_count", "manual_review_count"),
        # Covering index for common dashboard queries
        Index(
            "idx_dashboard_stats_summary_covering",
            "program_id",
            "academic_year_id",
            "cert_type_id",
            "total_submissions_required",
            "submitted_count",
            "approved_count",
            "last_calculated_at",
        ),
    )
