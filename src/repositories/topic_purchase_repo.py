"""
Topic Purchase Repository - Mavzu sotib olish
Day-based purchase system (FlashcardDeck o'rniga)
"""
from typing import List, Dict, Optional
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.subscription import UserTopicPurchase
from src.database.models.language import Day, Level
from src.repositories.base import BaseRepository


class TopicPurchaseRepository(BaseRepository[UserTopicPurchase]):
    """Repository for UserTopicPurchase"""
    model = UserTopicPurchase

    async def has_purchased(self, user_id: int, day_id: int) -> bool:
        """Foydalanuvchi mavzuni sotib olganmi?"""
        result = await self.session.execute(
            select(UserTopicPurchase).where(
                and_(
                    UserTopicPurchase.user_id == user_id,
                    UserTopicPurchase.day_id == day_id,
                    UserTopicPurchase.is_active == True
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def has_topic_access(self, user_id: int, day_id: int) -> bool:
        """
        Foydalanuvchi mavzuga kirish huquqi bormi?
        Bepul (price=0, is_premium=False) yoki sotib olingan bo'lsa True
        """
        # Check if day is free
        day_result = await self.session.execute(
            select(Day).where(Day.id == day_id)
        )
        day = day_result.scalar_one_or_none()
        if not day:
            return False

        # Free day
        if not day.is_premium and day.price == 0:
            return True

        # Check purchase
        return await self.has_purchased(user_id, day_id)

    async def purchase_topic(
        self,
        user_id: int,
        day_id: int,
        price_paid: int = 0,
        payment_method: str = "stars",
        telegram_payment_id: str = None
    ) -> UserTopicPurchase:
        """Mavzuni sotib olish"""
        # Check if already purchased
        existing = await self.session.execute(
            select(UserTopicPurchase).where(
                and_(
                    UserTopicPurchase.user_id == user_id,
                    UserTopicPurchase.day_id == day_id
                )
            )
        )
        purchase = existing.scalar_one_or_none()

        if purchase:
            # Reactivate if deactivated
            purchase.is_active = True
            purchase.price_paid = price_paid
            purchase.payment_method = payment_method
            if telegram_payment_id:
                purchase.telegram_payment_id = telegram_payment_id
        else:
            purchase = UserTopicPurchase(
                user_id=user_id,
                day_id=day_id,
                price_paid=price_paid,
                payment_method=payment_method,
                telegram_payment_id=telegram_payment_id
            )
            self.session.add(purchase)

        await self.session.flush()
        return purchase

    async def get_purchased_day_ids(self, user_id: int) -> List[int]:
        """Barcha sotib olingan Day ID lari"""
        result = await self.session.execute(
            select(UserTopicPurchase.day_id).where(
                and_(
                    UserTopicPurchase.user_id == user_id,
                    UserTopicPurchase.is_active == True
                )
            )
        )
        return [r[0] for r in result.all()]

    async def get_purchased_days_by_level(self, user_id: int) -> Dict[int, List[Day]]:
        """
        Sotib olingan mavzularni level bo'yicha guruhlash.
        Returns: {level_id: [Day, Day, ...]}
        """
        result = await self.session.execute(
            select(Day)
            .join(UserTopicPurchase, Day.id == UserTopicPurchase.day_id)
            .where(
                and_(
                    UserTopicPurchase.user_id == user_id,
                    UserTopicPurchase.is_active == True
                )
            )
            .order_by(Day.day_number)
        )
        days = result.scalars().all()

        grouped: Dict[int, List[Day]] = {}
        for day in days:
            if day.level_id not in grouped:
                grouped[day.level_id] = []
            grouped[day.level_id].append(day)

        return grouped

    async def get_user_purchases_count_per_level(self, user_id: int) -> Dict[int, int]:
        """Har bir leveldagi sotib olingan mavzular soni"""
        result = await self.session.execute(
            select(Day.level_id, func.count(UserTopicPurchase.id))
            .join(Day, Day.id == UserTopicPurchase.day_id)
            .where(
                and_(
                    UserTopicPurchase.user_id == user_id,
                    UserTopicPurchase.is_active == True
                )
            )
            .group_by(Day.level_id)
        )
        return {r[0]: r[1] for r in result.all()}

    async def get_free_day_ids(self) -> List[int]:
        """Barcha bepul mavzular ID lari"""
        result = await self.session.execute(
            select(Day.id).where(
                and_(
                    Day.is_active == True,
                    Day.is_premium == False,
                    Day.price == 0
                )
            )
        )
        return [r[0] for r in result.all()]
