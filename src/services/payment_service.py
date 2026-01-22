"""
Payment service - Telegram Stars payment handling
"""
from typing import Optional, Dict, Any
from datetime import datetime

from aiogram import Bot
from aiogram.types import (
    LabeledPrice,
    PreCheckoutQuery,
    Message,
    SuccessfulPayment
)

from src.database import get_session
from src.database.models import SubscriptionPlan, PaymentMethod, PaymentStatus
from src.repositories import (
    SubscriptionRepository, PaymentRepository,
    UserRepository, PromoCodeRepository
)
from src.core.logging import get_logger, audit_logger, LoggerMixin
from src.core.exceptions import PaymentFailedError, InsufficientStarsError
from src.config import settings

logger = get_logger(__name__)


# Payment plans configuration - settings dan olinadi
def get_payment_plans():
    """Payment plans - har safar settings dan yangilanadi"""
    return {
        "monthly": {
            "title": "Premium 1 oy",
            "description": "Premium obuna 30 kun uchun",
            "stars": settings.PREMIUM_MONTHLY_STARS,
            "days": 30,
            "plan": SubscriptionPlan.MONTHLY
        },
        "yearly": {
            "title": "Premium 1 yil",
            "description": "Premium obuna 365 kun uchun (40% chegirma!)",
            "stars": settings.PREMIUM_YEARLY_STARS,
            "days": 365,
            "plan": SubscriptionPlan.YEARLY
        },
        "lifetime": {
            "title": "Lifetime Premium",
            "description": "Umrbod premium obuna",
            "stars": settings.PREMIUM_LIFETIME_STARS,
            "days": 0,
            "plan": SubscriptionPlan.LIFETIME
        }
    }


# Backwards compatibility
PAYMENT_PLANS = get_payment_plans()


class PaymentService(LoggerMixin):
    """Payment processing service"""
    
    def __init__(self, bot: Bot = None):
        self.bot = bot
    
    def set_bot(self, bot: Bot):
        """Set bot instance"""
        self.bot = bot
    
    def get_plans(self) -> Dict[str, Dict]:
        """Get available payment plans"""
        return get_payment_plans()

    def get_plan(self, plan_id: str) -> Optional[Dict]:
        """Get single plan by ID"""
        return get_payment_plans().get(plan_id)
    
    async def create_invoice(
        self,
        chat_id: int,
        user_id: int,
        plan_id: str
    ) -> Optional[Message]:
        """
        Create and send Telegram Stars invoice.
        
        Returns the sent invoice message or None on failure.
        """
        if not self.bot:
            raise ValueError("Bot not initialized")
        
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Invalid plan: {plan_id}")
        
        # Create payment record
        async with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            payment_repo = PaymentRepository(session)
            
            subscription = await sub_repo.get_or_create(user_id)
            
            payment = await payment_repo.create_payment(
                subscription_id=subscription.id,
                user_id=user_id,
                amount=plan["stars"],
                plan=plan_id,
                days=plan["days"],
                method=PaymentMethod.TELEGRAM_STARS
            )
            
            payload = f"{payment.id}:{user_id}:{plan_id}"
        
        try:
            # Send invoice with Telegram Stars
            message = await self.bot.send_invoice(
                chat_id=chat_id,
                title=plan["title"],
                description=plan["description"],
                payload=payload,
                provider_token="",  # Empty for Telegram Stars
                currency="XTR",  # Telegram Stars currency
                prices=[
                    LabeledPrice(label=plan["title"], amount=plan["stars"])
                ],
                start_parameter=f"premium_{plan_id}",
                protect_content=False
            )
            
            self.logger.info(
                "Invoice created",
                user_id=user_id,
                plan=plan_id,
                stars=plan["stars"]
            )
            
            return message
            
        except Exception as e:
            self.logger.error(
                "Failed to create invoice",
                user_id=user_id,
                error=str(e)
            )
            
            # Mark payment as failed
            async with get_session() as session:
                payment_repo = PaymentRepository(session)
                await payment_repo.fail_payment(payment.id, str(e))
            
            raise PaymentFailedError(str(e))
    
    async def process_pre_checkout(
        self,
        pre_checkout: PreCheckoutQuery
    ) -> bool:
        """
        Process pre-checkout query.

        Returns True if payment should proceed, False otherwise.
        """
        try:
            payload_parts = pre_checkout.invoice_payload.split(":")
            if len(payload_parts) != 3:
                await pre_checkout.answer(
                    ok=False,
                    error_message="Invalid payment data"
                )
                return False

            payment_id, user_id, plan_id = payload_parts

            # XAVFSIZLIK: Payload'dagi user_id haqiqiy foydalanuvchi bilan mos kelishini tekshirish
            # Bu IDOR (Insecure Direct Object Reference) hujumini oldini oladi
            if int(user_id) != pre_checkout.from_user.id:
                self.logger.warning(
                    "Payment user mismatch - potential IDOR attack",
                    payload_user_id=user_id,
                    actual_user_id=pre_checkout.from_user.id
                )
                await pre_checkout.answer(
                    ok=False,
                    error_message="Unauthorized payment attempt"
                )
                return False

            # Verify payment exists and is pending
            async with get_session() as session:
                payment_repo = PaymentRepository(session)
                payment = await payment_repo.get_by_id(int(payment_id))

                if not payment:
                    await pre_checkout.answer(
                        ok=False,
                        error_message="Payment not found"
                    )
                    return False

                if payment.status != PaymentStatus.PENDING:
                    await pre_checkout.answer(
                        ok=False,
                        error_message="Payment already processed"
                    )
                    return False

                # Qo'shimcha tekshirish: payment user_id ham to'g'ri kelishini tekshirish
                if payment.user_id != pre_checkout.from_user.id:
                    self.logger.warning(
                        "Payment record user mismatch",
                        payment_user_id=payment.user_id,
                        actual_user_id=pre_checkout.from_user.id
                    )
                    await pre_checkout.answer(
                        ok=False,
                        error_message="Payment user mismatch"
                    )
                    return False

            # All good, approve
            await pre_checkout.answer(ok=True)
            return True
            
        except Exception as e:
            self.logger.error(
                "Pre-checkout error",
                error=str(e)
            )
            await pre_checkout.answer(
                ok=False,
                error_message="Processing error"
            )
            return False
    
    async def process_successful_payment(
        self,
        message: Message,
        payment: SuccessfulPayment
    ) -> Dict[str, Any]:
        """
        Process successful payment.

        Returns result dict with subscription info.
        """
        try:
            payload_parts = payment.invoice_payload.split(":")
            if len(payload_parts) != 3:
                raise PaymentFailedError("Invalid payment payload format")

            payment_id, user_id, plan_id = payload_parts

            # XAVFSIZLIK: User ID validatsiyasi
            if int(user_id) != message.from_user.id:
                self.logger.error(
                    "Payment user mismatch in successful payment",
                    payload_user_id=user_id,
                    actual_user_id=message.from_user.id
                )
                raise PaymentFailedError("Payment user mismatch")

            plan = self.get_plan(plan_id)
            if not plan:
                raise PaymentFailedError(f"Invalid plan: {plan_id}")
            
            async with get_session() as session:
                payment_repo = PaymentRepository(session)
                sub_repo = SubscriptionRepository(session)
                user_repo = UserRepository(session)
                
                # Complete payment record
                db_payment = await payment_repo.complete_payment(
                    payment_id=int(payment_id),
                    charge_id=payment.telegram_payment_charge_id,
                    provider_charge_id=payment.provider_payment_charge_id
                )
                
                # Activate subscription
                subscription = await sub_repo.activate_plan(
                    user_id=int(user_id),
                    plan=plan["plan"],
                    days=plan["days"]
                )
                
                # Update user premium status
                user = await user_repo.get_by_user_id(int(user_id))
                if user:
                    user.is_premium = True
                    await user_repo.save(user)
                
                # Update payment with total stars
                subscription.total_paid_stars += plan["stars"]
                await sub_repo.save(subscription)
            
            # Audit log
            audit_logger.log_payment(
                user_id=int(user_id),
                amount=plan["stars"],
                currency="XTR",
                status="completed",
                payment_id=payment.telegram_payment_charge_id
            )
            
            audit_logger.log_subscription_change(
                user_id=int(user_id),
                old_status="unknown",
                new_status=plan_id,
                reason="payment"
            )
            
            self.logger.info(
                "Payment successful",
                user_id=user_id,
                plan=plan_id,
                stars=plan["stars"]
            )
            
            return {
                "success": True,
                "plan": plan_id,
                "days": plan["days"],
                "expires_at": subscription.expires_at,
                "total_paid": subscription.total_paid_stars
            }
            
        except Exception as e:
            self.logger.error(
                "Payment processing error",
                error=str(e)
            )
            raise PaymentFailedError(str(e))
    
    async def apply_promo_code(
        self,
        user_id: int,
        code: str
    ) -> Dict[str, Any]:
        """Apply promo code to user"""
        async with get_session() as session:
            promo_repo = PromoCodeRepository(session)
            sub_repo = SubscriptionRepository(session)
            
            success, message, promo = await promo_repo.use_promo_code(code, user_id)
            
            if not success:
                return {"success": False, "message": message}
            
            # Apply rewards
            result = {"success": True, "message": message, "rewards": []}
            
            if promo.premium_days > 0:
                await sub_repo.extend_subscription(user_id, promo.premium_days)
                result["rewards"].append(f"{promo.premium_days} kun premium")
            
            if promo.bonus_stars > 0:
                result["rewards"].append(f"{promo.bonus_stars} yulduzcha")
            
            # Audit
            audit_logger.log_subscription_change(
                user_id=user_id,
                old_status="unknown",
                new_status="promo_applied",
                reason=f"promo_code:{code}"
            )
            
            return result
    
    async def check_subscription(self, user_id: int) -> Dict[str, Any]:
        """Check user's subscription status"""
        async with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            subscription = await sub_repo.get_or_create(user_id)
            
            return {
                "is_premium": subscription.is_active,
                "plan": subscription.plan.value,
                "days_remaining": subscription.days_remaining,
                "expires_at": subscription.expires_at,
                "auto_renew": subscription.auto_renew,
                "total_paid": subscription.total_paid_stars,
                "status_text": subscription.status_text
            }
    
    async def grant_premium(
        self,
        user_id: int,
        days: int,
        admin_id: int,
        reason: str = "admin_grant"
    ) -> bool:
        """Grant premium by admin"""
        async with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            user_repo = UserRepository(session)
            payment_repo = PaymentRepository(session)
            
            subscription = await sub_repo.extend_subscription(user_id, days)
            
            user = await user_repo.get_by_user_id(user_id)
            if user:
                user.is_premium = True
                await user_repo.save(user)
            
            # Create payment record for tracking
            await payment_repo.create_payment(
                subscription_id=subscription.id,
                user_id=user_id,
                amount=0,
                plan=f"admin_grant_{days}d",
                days=days,
                method=PaymentMethod.ADMIN_GRANT
            )
        
        # Audit
        audit_logger.log_admin_action(
            admin_id=admin_id,
            action="grant_premium",
            target=str(user_id),
            details={"days": days, "reason": reason}
        )
        
        audit_logger.log_subscription_change(
            user_id=user_id,
            old_status="unknown",
            new_status=f"+{days}d",
            reason=reason
        )
        
        return True


# Global service instance
payment_service = PaymentService()
