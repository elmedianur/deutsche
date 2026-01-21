"""
Subscription and Payment models
Telegram Stars integration
"""
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
from enum import Enum
from sqlalchemy import String, Text, ForeignKey, Integer, BigInteger, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class SubscriptionPlan(str, Enum):
    """Subscription plan types"""
    FREE = "free"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


class PaymentStatus(str, Enum):
    """Payment status"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    """Payment method"""
    TELEGRAM_STARS = "telegram_stars"
    REFERRAL_BONUS = "referral_bonus"
    ADMIN_GRANT = "admin_grant"
    PROMO_CODE = "promo_code"


class Subscription(Base, TimestampMixin):
    """User subscription model"""
    
    __tablename__ = "subscriptions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    
    # Plan info
    plan: Mapped[SubscriptionPlan] = mapped_column(
        SQLEnum(SubscriptionPlan),
        default=SubscriptionPlan.FREE
    )
    
    # Dates
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Auto-renewal
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Trial
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Stats
    total_paid_stars: Mapped[int] = mapped_column(Integer, default=0)
    renewal_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="subscription",
        foreign_keys=[user_id],
        primaryjoin="User.user_id == Subscription.user_id"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="subscription",
        lazy="selectin"
    )
    
    @property
    def is_active(self) -> bool:
        """Check if subscription is active"""
        if self.plan == SubscriptionPlan.FREE:
            return False
        if self.plan == SubscriptionPlan.LIFETIME:
            return True
        if self.expires_at is None:
            return False
        return datetime.utcnow() < self.expires_at
    
    @property
    def is_premium(self) -> bool:
        """Alias for is_active"""
        return self.is_active
    
    @property
    def days_remaining(self) -> int:
        """Days remaining in subscription"""
        if not self.is_active:
            return 0
        if self.plan == SubscriptionPlan.LIFETIME:
            return 9999
        if self.expires_at is None:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)
    
    @property
    def status_text(self) -> str:
        """Human-readable status"""
        if self.plan == SubscriptionPlan.FREE:
            return "🆓 Bepul"
        elif self.plan == SubscriptionPlan.LIFETIME:
            return "⭐ Lifetime Premium"
        elif self.is_active:
            return f"⭐ Premium ({self.days_remaining} kun qoldi)"
        else:
            return "❌ Muddati tugagan"
    
    def extend(self, days: int) -> None:
        """Extend subscription by days"""
        if self.expires_at is None or self.expires_at < datetime.utcnow():
            self.expires_at = datetime.utcnow() + timedelta(days=days)
        else:
            self.expires_at = self.expires_at + timedelta(days=days)
        
        if self.plan == SubscriptionPlan.FREE:
            self.plan = SubscriptionPlan.MONTHLY
    
    def activate_monthly(self) -> None:
        """Activate monthly subscription"""
        self.plan = SubscriptionPlan.MONTHLY
        self.started_at = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(days=30)
        self.renewal_count += 1
    
    def activate_yearly(self) -> None:
        """Activate yearly subscription"""
        self.plan = SubscriptionPlan.YEARLY
        self.started_at = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(days=365)
        self.renewal_count += 1
    
    def activate_lifetime(self) -> None:
        """Activate lifetime subscription"""
        self.plan = SubscriptionPlan.LIFETIME
        self.started_at = datetime.utcnow()
        self.expires_at = None
    
    def cancel(self) -> None:
        """Cancel subscription (disable auto-renew)"""
        self.auto_renew = False
    
    def expire(self) -> None:
        """Expire subscription"""
        self.plan = SubscriptionPlan.FREE
        self.expires_at = None


class Payment(Base, TimestampMixin):
    """Payment record model"""
    
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    # Payment details
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # In stars or smallest unit
    currency: Mapped[str] = mapped_column(String(10), default="XTR")  # XTR = Telegram Stars
    
    # Status
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.PENDING
    )
    
    # Method
    method: Mapped[PaymentMethod] = mapped_column(
        SQLEnum(PaymentMethod),
        default=PaymentMethod.TELEGRAM_STARS
    )
    
    # Telegram payment info
    telegram_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    provider_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Plan purchased
    plan_purchased: Mapped[str] = mapped_column(String(50), nullable=False)
    days_added: Mapped[int] = mapped_column(Integer, default=0)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="payments"
    )
    
    def complete(self, charge_id: str = None, provider_charge_id: str = None) -> None:
        """Mark payment as completed"""
        self.status = PaymentStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if charge_id:
            self.telegram_payment_charge_id = charge_id
        if provider_charge_id:
            self.provider_payment_charge_id = provider_charge_id
    
    def fail(self, reason: str = None) -> None:
        """Mark payment as failed"""
        self.status = PaymentStatus.FAILED
        if reason:
            self.notes = reason
    
    def refund(self, reason: str = None) -> None:
        """Mark payment as refunded"""
        self.status = PaymentStatus.REFUNDED
        if reason:
            self.notes = f"Refunded: {reason}"


class PromoCode(Base, TimestampMixin):
    """Promo code model"""
    
    __tablename__ = "promo_codes"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    
    # Reward
    premium_days: Mapped[int] = mapped_column(Integer, default=0)
    bonus_stars: Mapped[int] = mapped_column(Integer, default=0)
    
    # Limits
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_uses: Mapped[int] = mapped_column(Integer, default=0)
    
    # Validity
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Restrictions
    first_time_only: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Creator
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    @property
    def is_valid(self) -> bool:
        """Check if promo code is valid"""
        if not self.is_active:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
    
    def use(self) -> bool:
        """Use promo code"""
        if not self.is_valid:
            return False
        self.current_uses += 1
        return True


class PromoCodeUsage(Base, TimestampMixin):
    """Track promo code usage by users"""
    
    __tablename__ = "promo_code_usages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================
# USER INVENTORY MODEL
# ============================================================

class UserInventory(Base, TimestampMixin):
    """User inventory for shop items"""
    
    __tablename__ = "user_inventory"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    # Item info
    item_id: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "xp_boost_2x"
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "item" or "bundle"
    quantity: Mapped[int] = mapped_column(default=1)
    
    # Usage tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Purchase info
    stars_paid: Mapped[int] = mapped_column(default=0)
    telegram_payment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
