"""
Language hierarchy models - Language, Level, Day
"""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin, ActiveMixin

if TYPE_CHECKING:
    from .question import Question


class Language(Base, TimestampMixin, ActiveMixin):
    """Language model - e.g., German, English"""
    
    __tablename__ = "languages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    flag: Mapped[str] = mapped_column(String(10), default="🌐")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Order for display
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Premium only language
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    levels: Mapped[list["Level"]] = relationship(
        "Level",
        back_populates="language",
        lazy="selectin",
        order_by="Level.display_order"
    )
    
    @property
    def levels_count(self) -> int:
        """Number of active levels"""
        return len([l for l in self.levels if l.is_active])
    
    def __str__(self) -> str:
        return f"{self.flag} {self.name}"


class Level(Base, TimestampMixin, ActiveMixin):
    """Level model - e.g., A1, A2, B1"""
    
    __tablename__ = "levels"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    language_id: Mapped[int] = mapped_column(
        ForeignKey("languages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Order for display
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Premium only level
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    language: Mapped["Language"] = relationship(
        "Language",
        back_populates="levels",
        lazy="joined"
    )
    days: Mapped[list["Day"]] = relationship(
        "Day",
        back_populates="level",
        lazy="selectin",
        order_by="Day.day_number"
    )
    
    __table_args__ = (
        UniqueConstraint('language_id', 'name', name='uq_level_language_name'),
    )
    
    @property
    def days_count(self) -> int:
        """Number of active days"""
        return len([d for d in self.days if d.is_active])
    
    @property
    def questions_count(self) -> int:
        """Total questions in level"""
        return sum(d.questions_count for d in self.days if d.is_active)
    
    def __str__(self) -> str:
        return f"{self.language.flag} {self.name}"


class Day(Base, TimestampMixin, ActiveMixin):
    """Day model - represents a lesson day"""
    
    __tablename__ = "days"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    level_id: Mapped[int] = mapped_column(
        ForeignKey("levels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Topic/theme of the day
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Premium only day
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    price: Mapped[int] = mapped_column(Integer, default=0)  # Stars narxi (0 = bepul)

    # Relationships
    level: Mapped["Level"] = relationship(
        "Level",
        back_populates="days",
        lazy="joined"
    )
    questions: Mapped[list["Question"]] = relationship(
        "Question",
        back_populates="day",
        lazy="selectin"
    )
    
    __table_args__ = (
        UniqueConstraint('level_id', 'day_number', name='uq_day_level_number'),
    )
    
    @property
    def display_name(self) -> str:
        """Get display name"""
        if self.name:
            return self.name
        return f"Kun {self.day_number}"
    
    @property
    def questions_count(self) -> int:
        """Number of active questions"""
        return len([q for q in self.questions if q.is_active])
    
    @property
    def full_path(self) -> str:
        """Full path like 'German > A1 > Day 1'"""
        return f"{self.level.language.name} > {self.level.name} > {self.display_name}"
    
    def __str__(self) -> str:
        return f"{self.level} - {self.display_name}"
