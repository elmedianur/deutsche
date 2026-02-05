"""
Subscription repository - Payment and subscription data access
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, and_, update

from src.database.models import (
    Subscription, Payment, PromoCode, PromoCodeUsage,
    SubscriptionPlan, PaymentStatus, PaymentMethod
)
from src.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    """Repository for Subscription model"""
    
    model = Subscription
    
    async def get_by_user_id(self, user_id: int) -> Optional[Subscription]:
        """Get subscription by user_id"""
        result = await self.session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, user_id: int) -> Subscription:
        """Get existing or create new subscription"""
        sub = await self.get_by_user_id(user_id)
        if sub:
            return sub
        
        return await self.create(
            user_id=user_id,
            plan=SubscriptionPlan.FREE
        )
    
    async def is_premium(self, user_id: int) -> bool:
        """Check if user has active premium"""
        from src.config import settings
        # Super adminlar doim premium
        if settings.is_super_admin(user_id):
            return True
        sub = await self.get_by_user_id(user_id)
        return sub.is_active if sub else False
    
    async def activate_plan(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        days: int = 30
    ) -> Subscription:
        """Activate subscription plan"""
        sub = await self.get_or_create(user_id)
        
        if plan == SubscriptionPlan.MONTHLY:
            sub.activate_monthly()
        elif plan == SubscriptionPlan.YEARLY:
            sub.activate_yearly()
        elif plan == SubscriptionPlan.LIFETIME:
            sub.activate_lifetime()
        else:
            sub.extend(days)
        
        await self.save(sub)
        return sub
    
    async def extend_subscription(
        self,
        user_id: int,
        days: int
    ) -> Subscription:
        """Extend subscription by days"""
        sub = await self.get_or_create(user_id)
        sub.extend(days)
        await self.save(sub)
        return sub
    
    async def cancel_subscription(self, user_id: int) -> bool:
        """Cancel auto-renewal"""
        sub = await self.get_by_user_id(user_id)
        if not sub:
            return False
        
        sub.cancel()
        await self.save(sub)
        return True
    
    async def get_expiring_soon(self, days: int = 3) -> List[Subscription]:
        """Get subscriptions expiring within days"""
        from datetime import timedelta

        threshold = datetime.utcnow() + timedelta(days=days)
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.expires_at != None,
                    Subscription.expires_at <= threshold,
                    Subscription.plan != SubscriptionPlan.FREE
                )
            )
        )
        return list(result.scalars().all())

    async def expire_old_subscriptions(self) -> int:
        """Muddati tugagan obunalarni FREE ga o'zgartirish

        Bu metod muddati o'tgan barcha premium obunalarni
        (LIFETIME dan tashqari) FREE statusga o'tkazadi.

        Returns:
            int: O'zgartirilgan obunalar soni
        """
        now = datetime.utcnow()

        result = await self.session.execute(
            update(Subscription)
            .where(
                and_(
                    Subscription.expires_at != None,
                    Subscription.expires_at < now,
                    Subscription.plan != SubscriptionPlan.FREE,
                    Subscription.plan != SubscriptionPlan.LIFETIME
                )
            )
            .values(plan=SubscriptionPlan.FREE)
        )
        await self.session.flush()
        return result.rowcount


class PaymentRepository(BaseRepository[Payment]):
    """Repository for Payment model"""
    
    model = Payment
    
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
        return await self.create(
            subscription_id=subscription_id,
            user_id=user_id,
            amount=amount,
            currency="XTR",  # Telegram Stars
            status=PaymentStatus.PENDING,
            method=method,
            plan_purchased=plan,
            days_added=days
        )
    
    async def complete_payment(
        self,
        payment_id: int,
        charge_id: str = None,
        provider_charge_id: str = None
    ) -> Optional[Payment]:
        """Mark payment as completed"""
        payment = await self.get_by_id(payment_id)
        if not payment:
            return None
        
        payment.complete(charge_id, provider_charge_id)
        await self.save(payment)
        return payment
    
    async def fail_payment(
        self,
        payment_id: int,
        reason: str = None
    ) -> Optional[Payment]:
        """Mark payment as failed"""
        payment = await self.get_by_id(payment_id)
        if not payment:
            return None
        
        payment.fail(reason)
        await self.save(payment)
        return payment
    
    async def get_user_payments(
        self,
        user_id: int,
        status: PaymentStatus = None
    ) -> List[Payment]:
        """Get user's payment history"""
        query = select(Payment).where(Payment.user_id == user_id)
        
        if status:
            query = query.where(Payment.status == status)
        
        query = query.order_by(Payment.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_charge_id(self, charge_id: str) -> Optional[Payment]:
        """Get payment by Telegram charge ID"""
        result = await self.session.execute(
            select(Payment).where(
                Payment.telegram_payment_charge_id == charge_id
            )
        )
        return result.scalar_one_or_none()

    async def create_shop_payment(
        self,
        user_id: int,
        amount: int,
        item_type: str,
        item_id: str,
        charge_id: str = None,
        provider_charge_id: str = None,
    ) -> Payment:
        """Shop/Topic to'lovi uchun Payment record yaratish va completed qilish.

        Bu Premium subscription bilan bog'liq emas, shuning uchun
        subscription_id = None bo'lishi mumkin emas.
        Subscription topilmasa, get_or_create qilamiz.
        """
        from src.database.models import PaymentStatus

        # Subscription kerak (foreign key constraint)
        sub_repo = SubscriptionRepository(self.session)
        sub = await sub_repo.get_or_create(user_id)

        payment = Payment(
            subscription_id=sub.id,
            user_id=user_id,
            amount=amount,
            currency="XTR",
            status=PaymentStatus.COMPLETED,
            method=PaymentMethod.TELEGRAM_STARS,
            plan_purchased=f"{item_type}:{item_id}",
            days_added=0,
            telegram_payment_charge_id=charge_id,
            provider_payment_charge_id=provider_charge_id,
        )
        payment.complete(charge_id, provider_charge_id)
        self.session.add(payment)
        await self.session.flush()
        return payment

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
    """Repository for PromoCode model"""
    
    model = PromoCode
    
    async def get_by_code(self, code: str) -> Optional[PromoCode]:
        """Get promo code by code string"""
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code.upper())
        )
        return result.scalar_one_or_none()
    
    async def use_promo_code(
        self,
        code: str,
        user_id: int
    ) -> tuple[bool, str, Optional[PromoCode]]:
        """
        Try to use promo code.
        Returns (success, message, promo_code)
        """
        promo = await self.get_by_code(code)
        
        if not promo:
            return False, "Promo kod topilmadi", None
        
        if not promo.is_valid:
            return False, "Promo kod eskirgan yoki limitga yetgan", None
        
        # Check if user already used
        used = await self.session.execute(
            select(PromoCodeUsage).where(
                and_(
                    PromoCodeUsage.promo_code_id == promo.id,
                    PromoCodeUsage.user_id == user_id
                )
            )
        )
        if used.scalar_one_or_none():
            return False, "Siz bu promo kodni allaqachon ishlatgansiz", None
        
        # Use the code
        promo.use()
        
        # Record usage
        usage = PromoCodeUsage(
            promo_code_id=promo.id,
            user_id=user_id
        )
        self.session.add(usage)
        
        await self.session.flush()
        return True, "Promo kod muvaffaqiyatli qo'llanildi!", promo
    
    async def create_promo_code(
        self,
        code: str,
        premium_days: int = 0,
        bonus_stars: int = 0,
        max_uses: int = None,
        created_by: int = 0
    ) -> PromoCode:
        """Create new promo code"""
        return await self.create(
            code=code.upper(),
            premium_days=premium_days,
            bonus_stars=bonus_stars,
            max_uses=max_uses,
            created_by=created_by
        )
