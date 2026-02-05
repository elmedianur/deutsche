"""
Payment service - Compatibility redirect.

MUHIM: Haqiqiy implementatsiya payment_service.py da.
Bu fayl faqat eski importlar uchun mavjud.
Yangi kod uchun payment_service.py dan import qiling:
    from src.services.payment_service import PaymentService, payment_service, PAYMENT_PLANS
"""
# Re-export from canonical location
from src.services.payment_service import (
    PaymentService,
    PAYMENT_PLANS,
    payment_service,
)

__all__ = [
    "PaymentService",
    "PAYMENT_PLANS",
    "payment_service",
]
