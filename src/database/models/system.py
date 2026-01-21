"""
System models - channels, settings, bot configuration
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, ActiveMixin


class RequiredChannel(Base, TimestampMixin, ActiveMixin):
    """Required channel for subscription check"""
    
    __tablename__ = "required_channels"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Channel info
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Type: telegram, instagram, youtube, etc.
    channel_type: Mapped[str] = mapped_column(String(20), default="telegram")
    
    # Display
    icon: Mapped[str] = mapped_column(String(10), default="📢")
    display_order: Mapped[int] = mapped_column(default=0)
    
    # Stats
    clicks_count: Mapped[int] = mapped_column(default=0)
    
    @property
    def is_telegram(self) -> bool:
        """Check if Telegram channel"""
        return self.channel_type == "telegram"
    
    @property
    def display_text(self) -> str:
        """Get display text"""
        return f"{self.icon} {self.title}"


class BotSettings(Base, TimestampMixin):
    """Bot settings key-value store"""
    
    __tablename__ = "bot_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type hint for validation
    value_type: Mapped[str] = mapped_column(String(20), default="string")  # string, int, bool, json
    
    @property
    def typed_value(self):
        """Get value with proper type"""
        if self.value is None:
            return None
        
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        elif self.value_type == "json":
            import json
            return json.loads(self.value)
        return self.value


class GroupQuizSettings(Base, TimestampMixin):
    """Per-group quiz settings"""
    
    __tablename__ = "group_quiz_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    
    # Language/Level defaults
    default_language_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    default_level_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Quiz settings
    time_per_question: Mapped[int] = mapped_column(default=15)
    questions_per_quiz: Mapped[int] = mapped_column(default=10)
    
    # Features
    sticky_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_service_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    show_leaderboard: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Restrictions
    admin_only_start: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Results channel
    results_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Stats
    total_quizzes: Mapped[int] = mapped_column(default=0)
    total_participants: Mapped[int] = mapped_column(default=0)


class BroadcastMessage(Base, TimestampMixin):
    """Broadcast message tracking"""
    
    __tablename__ = "broadcast_messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Content
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Media (if any)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    video_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Target
    target_type: Mapped[str] = mapped_column(String(20), default="all")  # all, premium, free
    
    # Stats
    total_recipients: Mapped[int] = mapped_column(default=0)
    successful_sends: Mapped[int] = mapped_column(default=0)
    failed_sends: Mapped[int] = mapped_column(default=0)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, sending, completed, cancelled
    
    # Timing
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Creator
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    @property
    def delivery_rate(self) -> float:
        """Calculate delivery success rate"""
        if self.total_recipients == 0:
            return 0.0
        return (self.successful_sends / self.total_recipients) * 100
