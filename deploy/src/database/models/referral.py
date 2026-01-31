"""
Referral system models
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from enum import Enum
from sqlalchemy import String, ForeignKey, Integer, BigInteger, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class ReferralStatus(str, Enum):
    """Referral status"""
    PENDING = "pending"       # User registered but not completed requirements
    COMPLETED = "completed"   # User completed requirements, reward given
    EXPIRED = "expired"       # User didn't complete in time


class Referral(Base, TimestampMixin):
    """Referral tracking model"""
    
    __tablename__ = "referrals"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Referrer (who shared the link)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Referred user (who clicked the link)
    referred_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Referral code used
    referral_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    
    # Status
    status: Mapped[ReferralStatus] = mapped_column(
        SQLEnum(ReferralStatus),
        default=ReferralStatus.PENDING
    )
    
    # Progress tracking
    quizzes_completed: Mapped[int] = mapped_column(Integer, default=0)
    required_quizzes: Mapped[int] = mapped_column(Integer, default=5)  # From settings
    
    # Rewards
    referrer_reward_days: Mapped[int] = mapped_column(Integer, default=0)
    referred_reward_days: Mapped[int] = mapped_column(Integer, default=0)
    
    # Reward given
    reward_given_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    referrer: Mapped["User"] = relationship(
        "User",
        back_populates="referrals_made",
        foreign_keys=[referrer_id],
        primaryjoin="User.user_id == Referral.referrer_id"
    )
    referred_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referred_id],
        primaryjoin="User.user_id == Referral.referred_id"
    )
    
    @property
    def is_completed(self) -> bool:
        """Check if referral is completed"""
        return self.status == ReferralStatus.COMPLETED
    
    @property
    def progress_percent(self) -> float:
        """Get completion progress percentage"""
        if self.required_quizzes == 0:
            return 100.0
        return min(100.0, (self.quizzes_completed / self.required_quizzes) * 100)
    
    def increment_progress(self) -> bool:
        """
        Increment quiz completion count.
        Returns True if requirement is now met.
        """
        self.quizzes_completed += 1
        
        if self.quizzes_completed >= self.required_quizzes:
            return True
        return False
    
    def complete(self, referrer_days: int, referred_days: int) -> None:
        """Mark referral as completed and set rewards"""
        self.status = ReferralStatus.COMPLETED
        self.referrer_reward_days = referrer_days
        self.referred_reward_days = referred_days
        self.completed_at = datetime.utcnow()
        self.reward_given_at = datetime.utcnow()


class ReferralStats(Base, TimestampMixin):
    """Aggregated referral statistics for users"""
    
    __tablename__ = "referral_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    
    # Stats
    total_referrals: Mapped[int] = mapped_column(Integer, default=0)
    successful_referrals: Mapped[int] = mapped_column(Integer, default=0)
    pending_referrals: Mapped[int] = mapped_column(Integer, default=0)
    
    # Total rewards earned
    total_premium_days_earned: Mapped[int] = mapped_column(Integer, default=0)
    total_bonus_stars_earned: Mapped[int] = mapped_column(Integer, default=0)
    
    # Ranking
    referral_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    @property
    def conversion_rate(self) -> float:
        """Calculate referral conversion rate"""
        if self.total_referrals == 0:
            return 0.0
        return (self.successful_referrals / self.total_referrals) * 100
