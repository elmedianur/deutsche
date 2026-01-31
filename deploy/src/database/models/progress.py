"""
Progress and Streak models
"""
from datetime import datetime, date, timedelta, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Float, ForeignKey, Integer, BigInteger, Date, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin


def utc_today() -> date:
    """UTC timezone bo'yicha bugungi sanani qaytaradi.

    Bu funksiya server timezone'dan qat'i nazar,
    doim UTC vaqtini ishlatadi.
    """
    return datetime.now(timezone.utc).date()

if TYPE_CHECKING:
    from .user import User
    from .language import Day, Level, Language


class UserProgress(Base, TimestampMixin):
    """User quiz progress/history"""
    
    __tablename__ = "user_progress"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False, 
        index=True
    )
    
    # Quiz context
    language_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("languages.id", ondelete="SET NULL"),
        nullable=True
    )
    level_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("levels.id", ondelete="SET NULL"),
        nullable=True
    )
    day_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("days.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Quiz results
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    wrong_answers: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    
    # Score and time
    score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_time: Mapped[float] = mapped_column(Float, default=0.0)
    total_time: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Metadata
    quiz_type: Mapped[str] = mapped_column(String(20), default="personal")  # personal, group, duel
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="progress",
        foreign_keys=[user_id],
        primaryjoin="User.user_id == UserProgress.user_id",
        lazy="joined"
    )
    
    @property
    def percentage(self) -> float:
        """Score as percentage"""
        if self.total_questions == 0:
            return 0.0
        return (self.correct_answers / self.total_questions) * 100


class UserStreak(Base, TimestampMixin):
    """User daily streak tracking"""
    
    __tablename__ = "user_streaks"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    
    # Current streak
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    
    # Tracking dates
    last_activity_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    streak_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Freeze protection
    freeze_used_today: Mapped[bool] = mapped_column(Boolean, default=False)
    freeze_count: Mapped[int] = mapped_column(Integer, default=0)  # Premium users get freeze
    
    # Bonus tracking
    total_bonus_earned: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="streak",
        foreign_keys=[user_id],
        primaryjoin="User.user_id == UserStreak.user_id"
    )
    
    def check_and_update(self) -> dict:
        """
        Check streak status and update accordingly.
        Returns dict with status info.

        UTC timezone ishlatiladi barcha sana hisoblari uchun.
        """
        today = utc_today()  # UTC timezone ishlatiladi

        result = {
            "streak_maintained": False,
            "streak_increased": False,
            "streak_lost": False,
            "freeze_used": False,
            "bonus_earned": 0,
            "new_streak": self.current_streak
        }

        # Yangi kun boshlansa freeze flagni reset qilish
        if self.last_activity_date and self.last_activity_date < today:
            self.freeze_used_today = False

        if self.last_activity_date is None:
            # First activity
            self.current_streak = 1
            self.last_activity_date = today
            self.streak_start_date = today
            result["streak_increased"] = True
            result["new_streak"] = 1

        elif self.last_activity_date == today:
            # Already recorded today
            result["streak_maintained"] = True

        elif self.last_activity_date == today - timedelta(days=1):
            # Consecutive day
            self.current_streak += 1
            self.last_activity_date = today
            result["streak_increased"] = True
            result["new_streak"] = self.current_streak

            # Milestone bonuses
            if self.current_streak in [7, 30, 100, 365]:
                result["bonus_earned"] = self._calculate_milestone_bonus()
                self.total_bonus_earned += result["bonus_earned"]

        else:
            # Streak broken
            days_missed = (today - self.last_activity_date).days

            # TUZATILDI: days_missed >= 2 (oldin == 2 edi)
            # Freeze 2 yoki undan ko'p kun o'tkazib yuborilganda ishlaydi
            if days_missed >= 2 and self.freeze_count > 0 and not self.freeze_used_today:
                # Use freeze - streak saqlanadi
                self.freeze_count -= 1
                self.freeze_used_today = True
                # last_activity ni kechagi kunga o'rnatish (streak davom etadi deb hisoblanadi)
                self.last_activity_date = today - timedelta(days=1)
                result["streak_maintained"] = True
                result["freeze_used"] = True
                # Endi bugungi faollikni qayta tekshirish
                self.current_streak += 1
                self.last_activity_date = today
                result["streak_increased"] = True
                result["new_streak"] = self.current_streak
            else:
                # Reset streak
                result["streak_lost"] = True
                result["previous_streak"] = self.current_streak
                self.current_streak = 1
                self.streak_start_date = today
                self.last_activity_date = today
                result["new_streak"] = self.current_streak

        # Update longest streak
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak

        return result
    
    def _calculate_milestone_bonus(self) -> int:
        """Calculate bonus for streak milestone"""
        bonuses = {
            7: 50,     # 1 week
            30: 200,   # 1 month
            100: 500,  # 100 days
            365: 2000  # 1 year
        }
        return bonuses.get(self.current_streak, 0)
    
    @property
    def days_until_milestone(self) -> tuple[int, int]:
        """Returns (days_needed, milestone)"""
        milestones = [7, 30, 100, 365]
        for m in milestones:
            if self.current_streak < m:
                return (m - self.current_streak, m)
        return (0, self.current_streak)
    
    @property
    def is_active_today(self) -> bool:
        """Check if user was active today (UTC)"""
        return self.last_activity_date == utc_today()


class SpacedRepetition(Base, TimestampMixin):
    """
    Spaced Repetition data for individual question-user pairs.
    Implements SM-2 algorithm.
    """

    __tablename__ = "spaced_repetition"
    __table_args__ = (
        # Har bir user har bir savol uchun faqat 1 ta SR yozuvi
        UniqueConstraint('user_id', 'question_id', name='uq_user_question_sr'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # SM-2 parameters
    easiness_factor: Mapped[float] = mapped_column(Float, default=2.5)  # EF
    interval: Mapped[int] = mapped_column(Integer, default=1)  # Days
    repetitions: Mapped[int] = mapped_column(Integer, default=0)  # n
    
    # Tracking
    next_review_date: Mapped[date] = mapped_column(Date, default=utc_today)
    last_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Stats
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    correct_reviews: Mapped[int] = mapped_column(Integer, default=0)
    
    def update_after_review(self, quality: int) -> None:
        """
        Update SM-2 parameters after review.
        
        Quality rating:
        0 - Complete blackout
        1 - Incorrect, but remembered after seeing answer
        2 - Incorrect, but answer seemed easy to recall
        3 - Correct with serious difficulty
        4 - Correct with some hesitation
        5 - Perfect response
        """
        self.total_reviews += 1
        
        if quality >= 3:
            self.correct_reviews += 1
            
            if self.repetitions == 0:
                self.interval = 1
            elif self.repetitions == 1:
                self.interval = 6
            else:
                self.interval = int(self.interval * self.easiness_factor)
            
            self.repetitions += 1
        else:
            # Reset on failure
            self.repetitions = 0
            self.interval = 1
        
        # Update easiness factor
        self.easiness_factor = max(
            1.3,
            self.easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        )
        
        # Set next review date (UTC)
        self.last_review_date = utc_today()
        self.next_review_date = utc_today() + timedelta(days=self.interval)
    
    @property
    def is_due(self) -> bool:
        """Check if review is due (UTC)"""
        return utc_today() >= self.next_review_date

    @property
    def days_until_due(self) -> int:
        """Days until next review (UTC)"""
        return (self.next_review_date - utc_today()).days
    
    @property
    def mastery_level(self) -> str:
        """Get mastery level based on interval"""
        if self.interval <= 1:
            return "Yangi"
        elif self.interval <= 7:
            return "O'rganilmoqda"
        elif self.interval <= 30:
            return "O'zlashtirilmoqda"
        else:
            return "O'zlashtirilgan"
