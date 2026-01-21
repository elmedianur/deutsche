"""
Payment service - Telegram Stars payment integration
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Subscription, SubscriptionPlan, PaymentMethod
)
from src.repositories.payment import (
    SubscriptionRepository, PaymentRepository, PromoCodeRepository
)
from src.config import settings
from src.core.logging import get_logger, LoggerMixin, audit_logger
from src.core.exceptions import PaymentFailedError, SubscriptionExpiredError

logger = get_logger(__name__)


# Payment plans configuration
PAYMENT_PLANS = {
    "monthly": {
        "name": "Premium 1 oy",
        "description": "1 oylik premium obuna",
        "stars": settings.PREMIUM_MONTHLY_STARS,
        "days": 30,
        "plan": SubscriptionPlan.MONTHLY
    },
    "yearly": {
        "name": "Premium 1 yil",
        "description": "1 yillik premium obuna (2 oy bepul!)",
        "stars": settings.PREMIUM_YEARLY_STARS,
        "days": 365,
        "plan": SubscriptionPlan.YEARLY
    },
    "lifetime": {
        "name": "Lifetime Premium",
        "description": "Umrbod premium obuna",
        "stars": settings.PREMIUM_YEARLY_STARS * 3,  # 3 years price
        "days": 0,  # Lifetime
        "plan": SubscriptionPlan.LIFETIME
    }
}


class PaymentService(LoggerMixin):
    """Payment service - handles payment business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.sub_repo = SubscriptionRepository(session)
        self.payment_repo = PaymentRepository(session)
        self.promo_repo = PromoCodeRepository(session)
    
    # ==================== PLANS ====================
    
    def get_available_plans(self) -> list:
        """Get list of available plans"""
        return [
            {
                "id": plan_id,
                **plan_data
            }
            for plan_id, plan_data in PAYMENT_PLANS.items()
        ]
    
    def get_plan(self, plan_id: str) -> Optional[dict]:
        """Get specific plan by ID"""
        plan = PAYMENT_PLANS.get(plan_id)
        if plan:
            return {"id": plan_id, **plan}
        return None
    
    # ==================== SUBSCRIPTION ====================
    
    async def get_subscription(self, user_id: int) -> Subscription:
        """Get user's subscription"""
        sub, _ = await self.sub_repo.get_or_create(user_id)
        return sub
    
    async def is_premium(self, user_id: int) -> bool:
        """Check if user has active premium"""
        from src.config import settings
        # Super adminlar doim premium
        if settings.is_super_admin(user_id):
            return True
        return await self.sub_repo.is_premium(user_id)
    
    async def get_subscription_info(self, user_id: int) -> dict:
        """Get detailed subscription info"""
        sub = await self.get_subscription(user_id)
        
        return {
            "plan": sub.plan.value,
            "is_active": sub.is_active,
            "status_text": sub.status_text,
            "expires_at": sub.expires_at,
            "days_remaining": sub.days_remaining,
            "auto_renew": sub.auto_renew,
            "total_paid": sub.total_paid_stars
        }
    
    # ==================== TELEGRAM STARS PAYMENT ====================
    
    def create_invoice(self, plan_id: str) -> dict:
        """
        Create invoice for Telegram Stars payment.
        Returns data for Bot.send_invoice()
        """
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Unknown plan: {plan_id}")
        
        return {
            "title": plan["name"],
            "description": plan["description"],
            "payload": f"premium_{plan_id}",
            "currency": "XTR",  # Telegram Stars
            "prices": [{"label": plan["name"], "amount": plan["stars"]}],
            "provider_token": "",  # Empty for Telegram Stars
            "start_parameter": f"premium_{plan_id}",
            "photo_url": None,  # Optional: add premium badge image
            "photo_size": 0,
            "photo_width": 0,
            "photo_height": 0,
            "need_name": False,
            "need_phone_number": False,
            "need_email": False,
            "send_phone_number_to_provider": False,
            "send_email_to_provider": False,
            "is_flexible": False,
        }
    
    async def process_pre_checkout(
        self,
        user_id: int,
        payload: str,
        total_amount: int
    ) -> tuple[bool, str]:
        """
        Process pre-checkout query.
        Returns (success, error_message)
        """
        # Parse payload
        if not payload.startswith("premium_"):
            return False, "Invalid payload"
        
        plan_id = payload.replace("premium_", "")
        plan = self.get_plan(plan_id)
        
        if not plan:
            return False, "Plan not found"
        
        # Verify amount
        if total_amount != plan["stars"]:
            return False, "Invalid amount"
        
        self.logger.info(
            "Pre-checkout approved",
            user_id=user_id,
            plan=plan_id,
            amount=total_amount
        )
        
        return True, ""
    
    async def process_successful_payment(
        self,
        user_id: int,
        payload: str,
        total_amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str
    ) -> dict:
        """
        Process successful payment.
        Returns subscription info.
        """
        # Parse payload
        plan_id = payload.replace("premium_", "")
        plan = self.get_plan(plan_id)
        
        if not plan:
            raise PaymentFailedError("Plan not found")
        
        # Get subscription
        sub, _ = await self.sub_repo.get_or_create(user_id)
        
        # Create payment record
        payment = await self.payment_repo.create_payment(
            subscription_id=sub.id,
            user_id=user_id,
            amount=total_amount,
            plan=plan_id,
            days=plan["days"],
            method=PaymentMethod.TELEGRAM_STARS
        )
        
        # Complete payment
        await self.payment_repo.complete_payment(
            payment.id,
            telegram_payment_charge_id,
            provider_payment_charge_id
        )
        
        # Activate subscription
        sub = await self.sub_repo.activate_premium(
            user_id,
            plan["plan"],
            plan["days"]
        )
        
        # Update total paid
        sub.total_paid_stars += total_amount
        await self.session.flush()
        
        self.logger.info(
            "Payment successful",
            user_id=user_id,
            plan=plan_id,
            amount=total_amount
        )
        
        return {
            "success": True,
            "plan": plan_id,
            "plan_name": plan["name"],
            "days_added": plan["days"],
            "subscription": await self.get_subscription_info(user_id)
        }
    
    # ==================== PROMO CODES ====================
    
    async def apply_promo_code(
        self,
        user_id: int,
        code: str
    ) -> tuple[bool, str, dict]:
        """
        Apply promo code.
        Returns (success, message, details)
        """
        success, message, promo = await self.promo_repo.use_promo(code, user_id)
        
        if not success:
            return False, message, {}
        
        # Apply rewards
        details = {
            "premium_days": promo.premium_days,
            "bonus_stars": promo.bonus_stars
        }
        
        if promo.premium_days > 0:
            await self.sub_repo.extend_subscription(user_id, promo.premium_days)
            details["subscription"] = await self.get_subscription_info(user_id)
        
        self.logger.info(
            "Promo code applied",
            user_id=user_id,
            code=code,
            days=promo.premium_days
        )
        
        return True, message, details
    
    # ==================== REFERRAL REWARDS ====================
    
    async def grant_referral_reward(
        self,
        referrer_id: int,
        referred_id: int,
        days: int
    ) -> bool:
        """Grant referral reward to referrer"""
        try:
            await self.sub_repo.extend_subscription(referrer_id, days)
            
            audit_logger.log_subscription_change(
                user_id=referrer_id,
                old_status="",
                new_status=f"+{days} days",
                reason=f"referral_reward_from_{referred_id}"
            )
            
            return True
        except Exception as e:
            self.logger.error("Referral reward failed", error=str(e))
            return False
    
    # ==================== ADMIN ====================
    
    async def admin_grant_premium(
        self,
        user_id: int,
        days: int,
        admin_id: int,
        reason: str = ""
    ) -> bool:
        """Admin grants premium to user"""
        try:
            sub, _ = await self.sub_repo.get_or_create(user_id)
            
            # Create payment record
            payment = await self.payment_repo.create_payment(
                subscription_id=sub.id,
                user_id=user_id,
                amount=0,
                plan=f"admin_grant_{days}d",
                days=days,
                method=PaymentMethod.ADMIN_GRANT
            )
            payment.notes = f"Granted by {admin_id}: {reason}"
            
            await self.payment_repo.complete_payment(payment.id)
            
            # Extend subscription
            await self.sub_repo.extend_subscription(user_id, days)
            
            audit_logger.log_admin_action(
                admin_id=admin_id,
                action="grant_premium",
                target=str(user_id),
                details={"days": days, "reason": reason}
            )
            
            return True
        except Exception as e:
            self.logger.error("Admin grant failed", error=str(e))
            return False
    
    # ==================== STATS ====================
    
    async def get_revenue_stats(self, days: int = 30) -> dict:
        """Get revenue statistics"""
        from datetime import timedelta
        
        since = datetime.utcnow() - timedelta(days=days)
        return await self.payment_repo.get_total_revenue(since)
    
    async def check_and_expire_subscriptions(self) -> int:
        """Check and expire old subscriptions"""
        expired = await self.sub_repo.check_expired_subscriptions()
        return len(expired)
