"""
User model - main user entity
"""
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Date, String, BigInteger, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .subscription import Subscription
    from .streak import UserStreak
    from .achievement import UserAchievement
    from .referral import Referral
    from .progress import UserProgress


class User(Base, TimestampMixin):
    """User model"""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    
    # Basic info
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="uz")
    language: Mapped[str] = mapped_column(String(10), default="uz")  # UI language
    
    # Status
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    # Stats
    total_quizzes: Mapped[int] = mapped_column(default=0)
    total_correct: Mapped[int] = mapped_column(default=0)
    total_questions: Mapped[int] = mapped_column(default=0)
    
    
    # XP va Level
    xp: Mapped[int] = mapped_column(default=0)
    level: Mapped[int] = mapped_column(default=1)

    # Stars (virtual valyuta - turnir mukofotlari, achievements, va h.k.)
    stars: Mapped[int] = mapped_column(default=0)

    # Referral
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)
    referred_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    referral_count: Mapped[int] = mapped_column(default=0)
    
    # Settings
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Spaced Repetition Algorithm Settings
    # "sm2" = SM-2 algoritmi (default)
    # "anki" = Anki algoritmi
    sr_algorithm: Mapped[str] = mapped_column(String(10), default="sm2")
    
    # Activity
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_quiz_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Bio/Notes
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription",
        back_populates="user",
        foreign_keys="Subscription.user_id",
        primaryjoin="User.user_id == Subscription.user_id",
        uselist=False,
        lazy="selectin"
    )
    streak: Mapped[Optional["UserStreak"]] = relationship(
        "UserStreak",
        back_populates="user",
        foreign_keys="UserStreak.user_id",
        primaryjoin="User.user_id == UserStreak.user_id",
        uselist=False,
        lazy="selectin"
    )
    achievements: Mapped[list["UserAchievement"]] = relationship(
        "UserAchievement",
        back_populates="user",
        foreign_keys="UserAchievement.user_id",
        primaryjoin="User.user_id == UserAchievement.user_id",
        lazy="selectin"
    )
    referrals_made: Mapped[list["Referral"]] = relationship(
        "Referral",
        back_populates="referrer",
        foreign_keys="Referral.referrer_id",
        primaryjoin="User.user_id == Referral.referrer_id",
        lazy="selectin"
    )
    progress: Mapped[list["UserProgress"]] = relationship(
        "UserProgress",
        back_populates="user",
        foreign_keys="UserProgress.user_id",
        primaryjoin="User.user_id == UserProgress.user_id",
        lazy="selectin"
    )
    
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Anonim"
    
    @property
    def display_name(self) -> str:
        """Get display name (username or full name)"""
        if self.username:
            return f"@{self.username}"
        return self.full_name
    
    @property
    def accuracy(self) -> float:
        """Calculate accuracy percentage"""
        if self.total_questions == 0:
            return 0.0
        return (self.total_correct / self.total_questions) * 100
    
    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_active_at = datetime.utcnow()
    
    def update_stats(self, correct: int, total: int) -> None:
        """Update quiz statistics"""
        self.total_quizzes += 1
        self.total_correct += correct
        self.total_questions += total
        self.last_quiz_at = datetime.utcnow()

    def add_stars(self, amount: int) -> None:
        """Stars qo'shish (turnir, achievement mukofotlari)"""
        if amount > 0:
            self.stars = (self.stars or 0) + amount

    def remove_stars(self, amount: int) -> bool:
        """Stars ayirish (do'kon xaridlari). Muvaffaqiyatli bo'lsa True qaytaradi."""
        current = self.stars or 0
        if current >= amount:
            self.stars = current - amount
            return True
        return False

    # Quiz sozlamalari
    quiz_questions_count: Mapped[int] = mapped_column(default=10)  # 5, 10, 15, 20
    quiz_time_limit: Mapped[int] = mapped_column(default=15)  # sekundlarda: 10, 15, 20, 30
    quiz_daily_limit: Mapped[int] = mapped_column(default=50)  # kunlik limit: 20, 50, 100, 0=cheksiz
    quiz_difficulty: Mapped[str] = mapped_column(String(20), default="mixed")  # easy, medium, hard, mixed
    quizzes_today: Mapped[int] = mapped_column(default=0)  # bugungi o'yinlar soni
    quiz_last_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # oxirgi o'ynagan sana

    # =====================================================
    # O'RGANISH SOZLAMALARI (Learning Settings)
    # =====================================================

    # Onboarding
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Joriy o'rganish holati (Quick Start uchun)
    current_language_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    current_level_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    current_day_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    current_day_number: Mapped[int] = mapped_column(default=1)  # 1-kun, 2-kun, ...

    # Kunlik maqsadlar
    daily_word_goal: Mapped[int] = mapped_column(default=20)  # kunlik so'z maqsadi: 10, 20, 30, 50
    daily_quiz_goal: Mapped[int] = mapped_column(default=3)  # kunlik quiz maqsadi: 3, 5, 10

    # Bugungi progress
    words_learned_today: Mapped[int] = mapped_column(default=0)
    last_learning_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # O'rganish statistikasi
    total_words_learned: Mapped[int] = mapped_column(default=0)
    total_days_completed: Mapped[int] = mapped_column(default=0)

    def reset_daily_progress(self) -> None:
        """Kunlik progressni yangilash (yangi kun boshlanganda)"""
        today = date.today()
        if self.last_learning_date != today:
            self.words_learned_today = 0
            self.quizzes_today = 0
            self.last_learning_date = today
            self.quiz_last_date = today

    def add_words_learned(self, count: int) -> None:
        """O'rganilgan so'zlarni qo'shish"""
        self.reset_daily_progress()
        self.words_learned_today += count
        self.total_words_learned += count

    @property
    def daily_word_progress(self) -> float:
        """Kunlik so'z maqsadiga erishish foizi"""
        if self.daily_word_goal == 0:
            return 100.0
        return min(100.0, (self.words_learned_today / self.daily_word_goal) * 100)

    @property
    def daily_quiz_progress(self) -> float:
        """Kunlik quiz maqsadiga erishish foizi"""
        if self.daily_quiz_goal == 0:
            return 100.0
        return min(100.0, (self.quizzes_today / self.daily_quiz_goal) * 100)

    @property
    def daily_goal_reached(self) -> bool:
        """Kunlik maqsadga erishilganmi"""
        return self.words_learned_today >= self.daily_word_goal

    @property
    def has_learning_settings(self) -> bool:
        """O'rganish sozlamalari mavjudmi (Quick Start uchun)"""
        return self.current_level_id is not None
