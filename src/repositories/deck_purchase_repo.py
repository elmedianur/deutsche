"""
Deck Purchase Repository - Sotib olingan decklar
"""
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import UserDeckPurchase, FlashcardDeck
from src.repositories.base import BaseRepository


class DeckPurchaseRepository(BaseRepository[UserDeckPurchase]):
    """Repository for UserDeckPurchase"""
    model = UserDeckPurchase
    
    async def has_purchased(self, user_id: int, deck_id: int) -> bool:
        """Foydalanuvchi deckni sotib olganmi?"""
        result = await self.session.execute(
            select(UserDeckPurchase).where(
                and_(
                    UserDeckPurchase.user_id == user_id,
                    UserDeckPurchase.deck_id == deck_id,
                    UserDeckPurchase.is_active == True
                )
            )
        )
        return result.scalar_one_or_none() is not None
    
    async def purchase_deck(
        self, 
        user_id: int, 
        deck_id: int, 
        price: int = 0,
        payment_id: str = None
    ) -> UserDeckPurchase:
        """Deck sotib olish"""
        purchase = UserDeckPurchase(
            user_id=user_id,
            deck_id=deck_id,
            price_paid=price,
            payment_id=payment_id
        )
        self.session.add(purchase)
        await self.session.commit()
        await self.session.refresh(purchase)
        return purchase
    
    async def get_user_decks(self, user_id: int) -> List[FlashcardDeck]:
        """Foydalanuvchi sotib olgan decklar"""
        result = await self.session.execute(
            select(FlashcardDeck)
            .join(UserDeckPurchase, FlashcardDeck.id == UserDeckPurchase.deck_id)
            .where(
                and_(
                    UserDeckPurchase.user_id == user_id,
                    UserDeckPurchase.is_active == True
                )
            )
        )
        return list(result.scalars().all())
    
    async def get_available_decks(self, user_id: int) -> List[dict]:
        """
        Foydalanuvchi uchun mavjud decklar
        Returns: [{"deck": FlashcardDeck, "purchased": bool, "price": int}]
        """
        # Barcha faol decklar
        decks_result = await self.session.execute(
            select(FlashcardDeck).where(FlashcardDeck.is_active == True)
        )
        all_decks = decks_result.scalars().all()
        
        # Sotib olinganlar
        purchased_result = await self.session.execute(
            select(UserDeckPurchase.deck_id).where(
                and_(
                    UserDeckPurchase.user_id == user_id,
                    UserDeckPurchase.is_active == True
                )
            )
        )
        purchased_ids = set(r[0] for r in purchased_result.fetchall())
        
        result = []
        for deck in all_decks:
            result.append({
                "deck": deck,
                "purchased": deck.id in purchased_ids,
                "price": 0 if not deck.is_premium else 50  # Default price
            })

        return result

    async def has_day_access(self, user_id: int, day_id: int) -> bool:
        """
        Foydalanuvchi Day/Topic ga kirishga ruxsati bormi?
        Day'ga bog'langan Deck sotib olingan bo'lsa - True
        """
        # Find deck linked to this day
        result = await self.session.execute(
            select(FlashcardDeck).where(FlashcardDeck.day_id == day_id)
        )
        deck = result.scalar_one_or_none()

        if not deck:
            # No deck linked - check if day is premium
            from src.database.models import Day
            day_result = await self.session.execute(
                select(Day).where(Day.id == day_id)
            )
            day = day_result.scalar_one_or_none()
            # If day is not premium or doesn't exist, grant access
            return not (day and day.is_premium)

        # Check if user purchased the linked deck
        return await self.has_purchased(user_id, deck.id)

    async def has_deck_access(self, user_id: int, deck_id: int) -> bool:
        """
        Foydalanuvchi Deck ga kirishga ruxsati bormi?
        Deck sotib olingan yoki bepul bo'lsa - True
        """
        # Check if deck is free
        result = await self.session.execute(
            select(FlashcardDeck).where(FlashcardDeck.id == deck_id)
        )
        deck = result.scalar_one_or_none()

        if not deck:
            return False

        # Free decks are accessible
        if not deck.is_premium or deck.price == 0:
            return True

        # Check if purchased
        return await self.has_purchased(user_id, deck_id)
