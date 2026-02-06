"""
Database base model and mixins
Async SQLAlchemy 2.0 style
"""
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr


def _utc_now() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all database models"""
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name"""
        # Convert CamelCase to snake_case
        name = cls.__name__
        return ''.join(
            ['_' + c.lower() if c.isupper() else c for c in name]
        ).lstrip('_') + 's'
    
    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def __repr__(self) -> str:
        """String representation"""
        pk = getattr(self, 'id', None)
        return f"<{self.__class__.__name__}(id={pk})>"


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utc_now,
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utc_now,
        server_default=func.now(),
        onupdate=_utc_now,
        nullable=False
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality"""
    
    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        default=None,
        nullable=True
    )
    
    def soft_delete(self) -> None:
        """Mark record as deleted"""
        self.is_deleted = True
        self.deleted_at = _utc_now()
    
    def restore(self) -> None:
        """Restore soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None


class ActiveMixin:
    """Mixin for is_active flag"""
    
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True
    )
    
    def activate(self) -> None:
        """Activate record"""
        self.is_active = True
    
    def deactivate(self) -> None:
        """Deactivate record"""
        self.is_active = False
