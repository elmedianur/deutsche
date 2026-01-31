"""
Payment and Subscription repositories
Telegram Stars integration
"""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Subscription, Payment, PromoCode, PromoCodeUsage,
    SubscriptionPlan, PaymentStatus, PaymentMethod
)
from src.repositories.base import BaseRepository
from src.core.logging import get_logger, audit_logger

logger = get_logger(__name__)


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription
    """Subscription repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_by_user_id(self, user_id: int) -> Optional[Subscription]:
        """Get subscription by user_id"""
        return await self.get_one(user_id=user_id)
    
    async def get_or_create(self, user_id: int) -> tuple[Subscription, bool]:
        """Get or create subscription for user"""
        sub = await self.get_by_user_id(user_id)
        if sub:
            return sub, False
        
        sub = Subscription(
            user_id=user_id,
            plan=SubscriptionPlan.FREE
        )
        self.session.add(sub)
        await self.session.flush()
        return sub, True
    
    async def activate_premium(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        days: Optional[int] = None
    ) -> Subscription:
        """Activate premium subscription"""
        sub, _ = await self.get_or_create(user_id)
        
        old_plan = sub.plan
        
        if plan == SubscriptionPlan.MONTHLY:
            sub.activate_monthly()
        elif plan == SubscriptionPlan.YEARLY:
            sub.activate_yearly()
        elif plan == SubscriptionPlan.LIFETIME:
            sub.activate_lifetime()
        elif days:
            sub.extend(days)
        
        await self.session.flush()
        
        # Log subscription change
        audit_logger.log_subscription_change(
            user_id=user_id,
            old_status=old_plan.value,
            new_status=sub.plan.value,
            reason="premium_activated"
        )
        
        return sub
    
    async def extend_subscription(
        self,
        user_id: int,
        days: int
    ) -> Subscription:
        """Extend subscription by days"""
        sub, _ = await self.get_or_create(user_id)
        sub.extend(days)
        await self.session.flush()
        return sub
    
    async def check_expired_subscriptions(self) -> List[Subscription]:
        """Find and expire subscriptions that have passed their expiry date"""
        query = (
            select(Subscription)
            .where(
                and_(
                    Subscription.plan != SubscriptionPlan.FREE,
                    Subscription.plan != SubscriptionPlan.LIFETIME,
                    Subscription.expires_at < datetime.utcnow()
                )
            )
        )
        result = await self.session.execute(query)
        expired = list(result.scalars().all())
        
        for sub in expired:
            old_plan = sub.plan
            sub.expire()
            audit_logger.log_subscription_change(
                user_id=sub.user_id,
                old_status=old_plan.value,
                new_status=SubscriptionPlan.FREE.value,
                reason="expired"
            )
        
        if expired:
            await self.session.flush()
        
        return expired
    
    async def is_premium(self, user_id: int) -> bool:
        """Check if user has active premium"""
        from src.config import settings
        # Super adminlar doim premium
        if settings.is_super_admin(user_id):
            return True
        sub = await self.get_by_user_id(user_id)
        return sub.is_active if sub else False


class PaymentRepository(BaseRepository[Payment]):
    model = Payment
    """Payment repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def create_payment(
        self,
        subscription_id: int,
        user_id: int,
        amount: int,
        plan: str,
        days: int,
        method: PaymentMethod = PaymentMethod.TELEGRAM_STARS
    ) -> Payment:
        """Create new payment record"""
        payment = Payment(
            subscription_id=subscription_id,
            user_id=user_id,
            amount=amount,
            currency="XTR" if method == PaymentMethod.TELEGRAM_STARS else "USD",
            method=method,
            plan_purchased=plan,
            days_added=days,
            status=PaymentStatus.PENDING
        )
        self.session.add(payment)
        await self.session.flush()
        
        audit_logger.log_payment(
            user_id=user_id,
            amount=amount,
            currency=payment.currency,
            status="pending"
        )
        
        return payment
    
    async def complete_payment(
        self,
        payment_id: int,
        charge_id: str = None,
        provider_charge_id: str = None
    ) -> Optional[Payment]:
        """Mark payment as completed"""
        payment = await self.get_by_id(payment_id)
        if payment:
            payment.complete(charge_id, provider_charge_id)
            await self.session.flush()
            
            audit_logger.log_payment(
                user_id=payment.user_id,
                amount=payment.amount,
                currency=payment.currency,
                status="completed",
                payment_id=str(payment_id)
            )
        
        return payment
    
    async def fail_payment(
        self,
        payment_id: int,
        reason: str = None
    ) -> Optional[Payment]:
        """Mark payment as failed"""
        payment = await self.get_by_id(payment_id)
        if payment:
            payment.fail(reason)
            await self.session.flush()
            
            audit_logger.log_payment(
                user_id=payment.user_id,
                amount=payment.amount,
                currency=payment.currency,
                status="failed"
            )
        
        return payment
    
    async def get_user_payments(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[Payment]:
        """Get user's payment history"""
        query = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_total_revenue(
        self,
        since: Optional[datetime] = None
    ) -> dict:
        """Get total revenue stats"""
        from sqlalchemy import func
        
        query = (
            select(
                func.sum(Payment.amount).label("total"),
                func.count().label("count")
            )
            .where(Payment.status == PaymentStatus.COMPLETED)
        )
        
        if since:
            query = query.where(Payment.completed_at >= since)
        
        result = await self.session.execute(query)
        row = result.one()
        
        return {
            "total_stars": row.total or 0,
            "total_payments": row.count or 0
        }


class PromoCodeRepository(BaseRepository[PromoCode]):
    model = PromoCode
    """Promo code repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_by_code(self, code: str) -> Optional[PromoCode]:
        """Get promo code by code string"""
        return await self.get_one(code=code.upper())
    
    async def create_promo(
        self,
        code: str,
        premium_days: int = 0,
        bonus_stars: int = 0,
        max_uses: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        first_time_only: bool = False,
        created_by: int = 0
    ) -> PromoCode:
        """Create new promo code"""
        promo = PromoCode(
            code=code.upper(),
            premium_days=premium_days,
            bonus_stars=bonus_stars,
            max_uses=max_uses,
            expires_at=expires_at,
            first_time_only=first_time_only,
            created_by=created_by
        )
        self.session.add(promo)
        await self.session.flush()
        return promo
    
    async def use_promo(
        self,
        code: str,
        user_id: int
    ) -> tuple[bool, str, Optional[PromoCode]]:
        """
        Use promo code.
        Returns (success, message, promo)
        """
        promo = await self.get_by_code(code)
        
        if not promo:
            return False, "Promo kod topilmadi", None
        
        if not promo.is_valid:
            if promo.max_uses and promo.current_uses >= promo.max_uses:
                return False, "Promo kod limiti tugadi", None
            if promo.expires_at and datetime.utcnow() > promo.expires_at:
                return False, "Promo kod muddati tugagan", None
            return False, "Promo kod yaroqsiz", None
        
        # Check if already used
        query = select(PromoCodeUsage).where(
            and_(
                PromoCodeUsage.promo_code_id == promo.id,
                PromoCodeUsage.user_id == user_id
            )
        )
        result = await self.session.execute(query)
        if result.scalar_one_or_none():
            return False, "Siz bu promo kodni allaqachon ishlatgansiz", None
        
        # Use promo
        if not promo.use():
            return False, "Promo kodni ishlatishda xatolik", None
        
        # Record usage
        usage = PromoCodeUsage(
            promo_code_id=promo.id,
            user_id=user_id
        )
        self.session.add(usage)
        await self.session.flush()
        
        return True, "Promo kod muvaffaqiyatli ishlatildi!", promo
    
    async def get_active_promos(self) -> List[PromoCode]:
        """Get all active promo codes"""
        query = (
            select(PromoCode)
            .where(PromoCode.is_active == True)
            .order_by(PromoCode.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
