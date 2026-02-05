"""
Payment and Subscription repositories - Compatibility redirect.

MUHIM: Haqiqiy implementatsiya subscription_repo.py da.
Bu fayl faqat eski importlar uchun mavjud.
Yangi kod uchun subscription_repo.py dan import qiling:
    from src.repositories.subscription_repo import SubscriptionRepository, PaymentRepository, PromoCodeRepository
"""
# Re-export from canonical location
from src.repositories.subscription_repo import (
    SubscriptionRepository,
    PaymentRepository,
    PromoCodeRepository,
)

__all__ = [
    "SubscriptionRepository",
    "PaymentRepository",
    "PromoCodeRepository",
]
