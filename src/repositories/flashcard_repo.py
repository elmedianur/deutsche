"""
Flashcard Repository - Flashcard operations
TO'G'RILANGAN: BaseRepository pattern ga moslashtirildi
"""
from datetime import datetime, date, timedelta
from typing import Optional, List
from sqlalchemy import select, update, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.utils import utc_today

from src.database.models.flashcard import (
    FlashcardDeck,
    Flashcard,
    UserFlashcard,
    UserDeckProgress
)
from src.repositories.base import BaseRepository


class FlashcardDeckRepository(BaseRepository[FlashcardDeck]):
    """Flashcard deck repository"""
    model = FlashcardDeck

    async def get_by_id(self, deck_id: int) -> Optional[FlashcardDeck]:
        """ID bo'yicha deck olish"""
        result = await self.session.execute(
            select(FlashcardDeck).where(FlashcardDeck.id == deck_id)
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> List[FlashcardDeck]:
        """Barcha faol decklar"""
        result = await self.session.execute(
            select(FlashcardDeck).where(
                FlashcardDeck.is_active == True
            ).order_by(FlashcardDeck.display_order.asc())
        )
        return list(result.scalars().all())

    async def get_by_language(self, language_id: int) -> List[FlashcardDeck]:
        """Til bo'yicha decklar"""
        result = await self.session.execute(
            select(FlashcardDeck).where(
                and_(
                    FlashcardDeck.language_id == language_id,
                    FlashcardDeck.is_active == True
                )
            ).order_by(FlashcardDeck.display_order.asc())
        )
        return list(result.scalars().all())

    async def get_by_level(self, level_id: int) -> List[FlashcardDeck]:
        """Daraja bo'yicha decklar"""
        result = await self.session.execute(
            select(FlashcardDeck).where(
                and_(
                    FlashcardDeck.level_id == level_id,
                    FlashcardDeck.is_active == True
                )
            ).order_by(FlashcardDeck.display_order.asc())
        )
        return list(result.scalars().all())


class FlashcardRepository(BaseRepository[Flashcard]):
    """Flashcard repository"""
    model = Flashcard

    async def get_by_id(self, card_id: int) -> Optional[Flashcard]:
        """ID bo'yicha kartochka olish"""
        result = await self.session.execute(
            select(Flashcard).where(Flashcard.id == card_id)
        )
        return result.scalar_one_or_none()

    async def get_deck_cards(
        self,
        deck_id: int,
        limit: Optional[int] = None
    ) -> List[Flashcard]:
        """Deckdagi kartochkalar"""
        query = select(Flashcard).where(
            and_(
                Flashcard.deck_id == deck_id,
                Flashcard.is_active == True
            )
        ).order_by(Flashcard.display_order.asc())

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_deck_cards(self, deck_id: int) -> int:
        """Deckdagi kartochkalar soni"""
        result = await self.session.execute(
            select(func.count(Flashcard.id)).where(
                and_(
                    Flashcard.deck_id == deck_id,
                    Flashcard.is_active == True
                )
            )
        )
        return result.scalar() or 0


class UserFlashcardRepository(BaseRepository[UserFlashcard]):
    """User flashcard progress repository"""
    model = UserFlashcard

    async def get_or_create(
        self,
        user_id: int,
        card_id: int
    ) -> UserFlashcard:
        """Progress olish yoki yaratish"""
        result = await self.session.execute(
            select(UserFlashcard).where(
                and_(
                    UserFlashcard.user_id == user_id,
                    UserFlashcard.card_id == card_id
                )
            )
        )
        user_card = result.scalar_one_or_none()

        if not user_card:
            user_card = UserFlashcard(
                user_id=user_id,
                card_id=card_id,
                easiness_factor=2.5,
                interval=0,
                repetitions=0,
                next_review_date=utc_today()
            )
            self.session.add(user_card)
            await self.session.flush()
            await self.session.refresh(user_card)

        return user_card

    async def update_after_review(
        self,
        user_id: int,
        flashcard_id: int,
        quality: int  # 0-5 (0=bilmadim, 5=juda oson)
    ) -> UserFlashcard:
        """Spaced repetition algoritmi bilan yangilash (SM-2)"""
        user_card = await self.get_or_create(user_id, flashcard_id)

        # SM-2 Algorithm
        if quality < 3:
            # Noto'g'ri javob - qaytadan boshlash
            user_card.repetitions = 0
            user_card.interval = 0
            user_card.next_review_date = utc_today()
        else:
            # To'g'ri javob
            if user_card.repetitions == 0:
                user_card.interval = 1
            elif user_card.repetitions == 1:
                user_card.interval = 6
            else:
                user_card.interval = int(user_card.interval * user_card.easiness_factor)

            user_card.repetitions += 1
            user_card.next_review_date = utc_today() + timedelta(days=user_card.interval)

        # Ease factor yangilash
        user_card.easiness_factor = max(
            1.3,
            user_card.easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        )

        user_card.last_review_date = utc_today()
        user_card.total_reviews += 1

        if quality >= 3:
            user_card.correct_reviews += 1

        await self.session.flush()
        await self.session.refresh(user_card)
        return user_card

    async def get_due_cards(
        self,
        user_id: int,
        deck_id: Optional[int] = None,
        limit: int = 20
    ) -> List[UserFlashcard]:
        """Takrorlash kerak bo'lgan kartochkalar"""
        query = select(UserFlashcard).where(
            and_(
                UserFlashcard.user_id == user_id,
                UserFlashcard.next_review_date <= utc_today(),
                UserFlashcard.is_suspended == False
            )
        ).options(
            # N+1 query oldini olish - card va deck ni eager load qilish
            selectinload(UserFlashcard.card).selectinload(Flashcard.deck)
        )

        if deck_id:
            query = query.join(Flashcard).where(Flashcard.deck_id == deck_id)

        query = query.order_by(UserFlashcard.next_review_date.asc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_user_card_stats(
        self,
        user_id: int,
        deck_id: Optional[int] = None
    ) -> dict:
        """Foydalanuvchi statistikasi"""
        query = select(UserFlashcard).where(UserFlashcard.user_id == user_id)

        if deck_id:
            query = query.join(Flashcard).where(Flashcard.deck_id == deck_id)

        result = await self.session.execute(query)
        cards = list(result.scalars().all())

        total = len(cards)
        learned = sum(1 for c in cards if c.repetitions >= 3)
        learning = sum(1 for c in cards if 0 < c.repetitions < 3)
        due = sum(1 for c in cards if c.next_review_date <= utc_today())

        total_reviews = sum(c.total_reviews for c in cards)
        correct_reviews = sum(c.correct_reviews for c in cards)

        return {
            "total_cards": total,
            "learned": learned,
            "learning": learning,
            "new": total - learned - learning,
            "due_today": due,
            "total_reviews": total_reviews,
            "accuracy": (correct_reviews / total_reviews * 100) if total_reviews > 0 else 0
        }



    async def auto_suspend_mastered(
        self,
        user_id: int,
        threshold_days: int = 180
    ) -> int:
        """
        Interval >= threshold_days bo'lgan kartochkalarni suspend qilish.
        Returns: suspend qilingan kartochkalar soni
        """
        result = await self.session.execute(
            select(UserFlashcard).where(
                and_(
                    UserFlashcard.user_id == user_id,
                    UserFlashcard.interval >= threshold_days,
                    UserFlashcard.is_suspended == False
                )
            )
        )
        cards = list(result.scalars().all())
        
        for card in cards:
            card.is_suspended = True
        
        if cards:
            await self.session.flush()
        
        return len(cards)

    async def auto_suspend_all_users(
        self,
        threshold_days: int = 180
    ) -> dict:
        """
        Barcha foydalanuvchilar uchun mastered kartochkalarni suspend qilish.
        Returns: {"total_suspended": int, "users_affected": int}
        """
        result = await self.session.execute(
            update(UserFlashcard)
            .where(
                and_(
                    UserFlashcard.interval >= threshold_days,
                    UserFlashcard.is_suspended == False
                )
            )
            .values(is_suspended=True)
        )
        
        await self.session.flush()
        
        return {
            "total_suspended": result.rowcount,
            "threshold_days": threshold_days
        }

    async def unsuspend_card(
        self,
        user_id: int,
        card_id: int
    ) -> Optional[UserFlashcard]:
        """Kartochkani qayta faollashtirish"""
        result = await self.session.execute(
            select(UserFlashcard).where(
                and_(
                    UserFlashcard.user_id == user_id,
                    UserFlashcard.card_id == card_id
                )
            )
        )
        card = result.scalar_one_or_none()
        
        if card:
            card.is_suspended = False
            await self.session.flush()
            await self.session.refresh(card)
        
        return card

    async def get_suspended_cards(
        self,
        user_id: int,
        deck_id: Optional[int] = None
    ) -> List[UserFlashcard]:
        """Suspend qilingan kartochkalar ro'yxati"""
        query = select(UserFlashcard).where(
            and_(
                UserFlashcard.user_id == user_id,
                UserFlashcard.is_suspended == True
            )
        )
        
        if deck_id:
            query = query.join(Flashcard).where(Flashcard.deck_id == deck_id)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())


class UserDeckProgressRepository(BaseRepository[UserDeckProgress]):
    """User deck progress repository"""
    model = UserDeckProgress

    async def get_or_create(
        self,
        user_id: int,
        deck_id: int
    ) -> UserDeckProgress:
        """Progress olish yoki yaratish"""
        result = await self.session.execute(
            select(UserDeckProgress).where(
                and_(
                    UserDeckProgress.user_id == user_id,
                    UserDeckProgress.deck_id == deck_id
                )
            )
        )
        progress = result.scalar_one_or_none()

        if not progress:
            progress = UserDeckProgress(
                user_id=user_id,
                deck_id=deck_id
            )
            self.session.add(progress)
            await self.session.flush()
            await self.session.refresh(progress)

        return progress

    async def update_progress(
        self,
        user_id: int,
        deck_id: int,
        cards_studied: int,
        correct: int
    ) -> UserDeckProgress:
        """Progressni yangilash"""
        progress = await self.get_or_create(user_id, deck_id)

        progress.cards_seen += cards_studied
        progress.total_reviews += cards_studied
        progress.last_review_date = utc_today()

        await self.session.flush()
        await self.session.refresh(progress)
        return progress

    async def get_user_all_progress(self, user_id: int) -> List[UserDeckProgress]:
        """Foydalanuvchining barcha deck progresslari"""
        result = await self.session.execute(
            select(UserDeckProgress).where(
                UserDeckProgress.user_id == user_id
            ).order_by(desc(UserDeckProgress.last_review_date))
        )
        return list(result.scalars().all())


async def get_or_create_quiz_errors_deck(session) -> FlashcardDeck:
    """Quiz xatolar uchun maxsus deck olish yoki yaratish"""
    from sqlalchemy import select
    
    result = await session.execute(
        select(FlashcardDeck).where(FlashcardDeck.name == "Quiz xatolar")
    )
    deck = result.scalar_one_or_none()
    
    if not deck:
        deck = FlashcardDeck(
            name="Quiz xatolar",
            description="Quizda xato qilingan savollar",
            language_id=1,  # Default language
            level_id=1,
            icon="❌",
            is_premium=False,
            is_active=True,
            cards_count=0
        )
        session.add(deck)
        await session.flush()
        await session.refresh(deck)
    
    return deck


async def add_question_to_flashcard(
    session,
    user_id: int,
    question_id: int,
    question_text: str,
    correct_answer: str,
    explanation: str = None
) -> bool:
    """Quiz savolini flashcardga qo'shish"""
    from sqlalchemy import select
    
    # Maxsus deck
    deck = await get_or_create_quiz_errors_deck(session)
    
    # Bu savol allaqachon flashcardda bormi?
    result = await session.execute(
        select(Flashcard).where(
            Flashcard.deck_id == deck.id,
            Flashcard.front_text == question_text[:500]
        )
    )
    card = result.scalar_one_or_none()
    
    if not card:
        # Yangi flashcard yaratish
        card = Flashcard(
            deck_id=deck.id,
            front_text=question_text[:500],
            back_text=correct_answer[:500],
            example_sentence=explanation[:1000] if explanation else None,
            is_active=True
        )
        session.add(card)
        await session.flush()
        await session.refresh(card)
        
        # Deck cards_count yangilash
        deck.cards_count += 1
        await session.flush()
    
    # User uchun flashcard progress
    result = await session.execute(
        select(UserFlashcard).where(
            UserFlashcard.user_id == user_id,
            UserFlashcard.card_id == card.id
        )
    )
    user_card = result.scalar_one_or_none()
    
    if not user_card:
        from datetime import date
        user_card = UserFlashcard(
            user_id=user_id,
            card_id=card.id,
            easiness_factor=2.5,
            interval=0,
            repetitions=0,
            next_review_date=utc_today(),
            is_suspended=False
        )
        session.add(user_card)
        await session.flush()
        return True  # Yangi qo'shildi
    
    return False  # Allaqachon bor


class DailyLimitManager:
    """Kunlik limitlarni boshqarish"""
    
    def __init__(self, session):
        self.session = session
    
    async def get_user_limits(self, user_id: int, deck_id: int) -> dict:
        """Foydalanuvchi limitlarini olish"""
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(UserDeckProgress).where(
                and_(
                    UserDeckProgress.user_id == user_id,
                    UserDeckProgress.deck_id == deck_id
                )
            )
        )
        progress = result.scalar_one_or_none()
        
        if not progress:
            return {
                "new_cards_limit": 10,
                "new_cards_today": 0,
                "new_cards_remaining": 10,
                "review_limit": 50,
                "reviews_today": 0,
                "reviews_remaining": 50,
                "last_review_date": None
            }
        
        # Kun o'zgargan bo'lsa reset qilish
        today = utc_today()
        if progress.last_review_date and progress.last_review_date < today:
            progress.new_cards_today = 0
            progress.reviews_today = 0
            await self.session.flush()
        
        return {
            "new_cards_limit": progress.daily_new_cards,
            "new_cards_today": progress.new_cards_today,
            "new_cards_remaining": max(0, progress.daily_new_cards - progress.new_cards_today),
            "review_limit": progress.daily_review_limit,
            "reviews_today": progress.reviews_today,
            "reviews_remaining": max(0, progress.daily_review_limit - progress.reviews_today),
            "last_review_date": progress.last_review_date
        }
    
    async def increment_review(self, user_id: int, deck_id: int, is_new_card: bool = False) -> dict:
        """Takrorlash counterni oshirish"""
        progress_repo = UserDeckProgressRepository(self.session)
        progress = await progress_repo.get_or_create(user_id, deck_id)
        
        # Kun o'zgargan bo'lsa reset
        today = utc_today()
        if progress.last_review_date and progress.last_review_date < today:
            progress.new_cards_today = 0
            progress.reviews_today = 0
        
        progress.reviews_today += 1
        if is_new_card:
            progress.new_cards_today += 1
        progress.last_review_date = today
        
        await self.session.flush()
        
        return {
            "new_cards_remaining": max(0, progress.daily_new_cards - progress.new_cards_today),
            "reviews_remaining": max(0, progress.daily_review_limit - progress.reviews_today)
        }
    
    async def can_study(self, user_id: int, deck_id: int) -> dict:
        """O'rganish mumkinmi tekshirish"""
        limits = await self.get_user_limits(user_id, deck_id)
        
        can_review = limits["reviews_remaining"] > 0
        can_learn_new = limits["new_cards_remaining"] > 0
        
        return {
            "can_review": can_review,
            "can_learn_new": can_learn_new,
            "can_study": can_review or can_learn_new,
            "message": self._get_limit_message(limits),
            **limits
        }
    
    def _get_limit_message(self, limits: dict) -> str:
        """Limit xabari"""
        if limits["reviews_remaining"] <= 0 and limits["new_cards_remaining"] <= 0:
            return "🎉 Bugungi limit tugadi! Ertaga davom eting."
        
        msgs = []
        if limits["new_cards_remaining"] > 0:
            msgs.append(f"🆕 Yangi: {limits['new_cards_remaining']}/{limits['new_cards_limit']}")
        else:
            msgs.append("🆕 Yangi: limit tugadi")
            
        if limits["reviews_remaining"] > 0:
            msgs.append(f"🔄 Takrorlash: {limits['reviews_remaining']}/{limits['review_limit']}")
        else:
            msgs.append("🔄 Takrorlash: limit tugadi")
        
        return " | ".join(msgs)
    
    async def update_limits(
        self,
        user_id: int,
        deck_id: int,
        new_cards_limit: int = None,
        review_limit: int = None
    ) -> dict:
        """Limitlarni o'zgartirish"""
        progress_repo = UserDeckProgressRepository(self.session)
        progress = await progress_repo.get_or_create(user_id, deck_id)
        
        if new_cards_limit is not None:
            progress.daily_new_cards = max(1, min(50, new_cards_limit))
        
        if review_limit is not None:
            progress.daily_review_limit = max(10, min(200, review_limit))
        
        await self.session.flush()
        
        return {
            "new_cards_limit": progress.daily_new_cards,
            "review_limit": progress.daily_review_limit
        }


class DifficultCardsManager:
    """Qiyin so'zlarni boshqarish"""
    
    def __init__(self, session):
        self.session = session
    
    async def get_difficult_cards(
        self,
        user_id: int,
        accuracy_threshold: float = 50.0,
        min_reviews: int = 3
    ) -> List[UserFlashcard]:
        """
        Qiyin so'zlarni olish (accuracy < threshold)
        min_reviews: kamida shuncha takrorlangan bo'lishi kerak
        """
        from sqlalchemy import select, and_
        
        result = await self.session.execute(
            select(UserFlashcard).where(
                and_(
                    UserFlashcard.user_id == user_id,
                    UserFlashcard.total_reviews >= min_reviews,
                    UserFlashcard.is_suspended == False
                )
            )
        )
        all_cards = list(result.scalars().all())
        
        # Filter by accuracy
        difficult = []
        for card in all_cards:
            if card.total_reviews > 0:
                accuracy = (card.correct_reviews / card.total_reviews) * 100
                if accuracy < accuracy_threshold:
                    card._accuracy = accuracy  # Temp attribute
                    difficult.append(card)
        
        # Sort by accuracy (worst first)
        difficult.sort(key=lambda c: c._accuracy)
        
        return difficult
    
    async def get_difficult_stats(self, user_id: int) -> dict:
        """Qiyin so'zlar statistikasi"""
        difficult = await self.get_difficult_cards(user_id)
        
        return {
            "count": len(difficult),
            "cards": difficult[:20]  # Top 20 worst
        }


class ExtendedStatsManager:
    """Kengaytirilgan statistika"""
    
    def __init__(self, session):
        self.session = session
    
    async def get_extended_stats(self, user_id: int) -> dict:
        """Kengaytirilgan statistika"""
        from sqlalchemy import select, func, and_
        from datetime import timedelta
        
        # Barcha user flashcardlarni olish
        result = await self.session.execute(
            select(UserFlashcard).where(UserFlashcard.user_id == user_id)
        )
        all_cards = list(result.scalars().all())
        
        if not all_cards:
            return self._empty_stats()
        
        # Asosiy statistikalar
        total = len(all_cards)
        total_reviews = sum(c.total_reviews for c in all_cards)
        correct_reviews = sum(c.correct_reviews for c in all_cards)
        
        # Mastery darajalari
        mastery = self._calculate_mastery(all_cards)
        
        # Streak va davomiylik
        streak_info = self._calculate_streak(all_cards)
        
        # Qiyinlik tahlili
        difficulty = self._analyze_difficulty(all_cards)
        
        # Progress grafik uchun ma'lumot
        progress_bars = self._generate_progress_bars(mastery, total)
        
        return {
            "total_cards": total,
            "total_reviews": total_reviews,
            "correct_reviews": correct_reviews,
            "accuracy": (correct_reviews / total_reviews * 100) if total_reviews > 0 else 0,
            "mastery": mastery,
            "streak_info": streak_info,
            "difficulty": difficulty,
            "progress_bars": progress_bars,
            "avg_ease_factor": sum(c.easiness_factor for c in all_cards) / total if total > 0 else 2.5,
            "suspended_count": sum(1 for c in all_cards if c.is_suspended),
        }
    
    def _empty_stats(self) -> dict:
        return {
            "total_cards": 0,
            "total_reviews": 0,
            "correct_reviews": 0,
            "accuracy": 0,
            "mastery": {"new": 0, "learning": 0, "reviewing": 0, "mastered": 0, "suspended": 0},
            "streak_info": {"current": 0, "best": 0},
            "difficulty": {"easy": 0, "medium": 0, "hard": 0},
            "progress_bars": {"mastered": "", "learning": ""},
            "avg_ease_factor": 2.5,
            "suspended_count": 0,
        }
    
    def _calculate_mastery(self, cards: list) -> dict:
        """Mastery darajalarini hisoblash"""
        mastery = {
            "new": 0,       # repetitions = 0
            "learning": 0,  # interval <= 3
            "reviewing": 0, # interval <= 21
            "mastered": 0,  # interval > 21
            "suspended": 0
        }
        
        for c in cards:
            if c.is_suspended:
                mastery["suspended"] += 1
            elif c.repetitions == 0:
                mastery["new"] += 1
            elif c.interval <= 3:
                mastery["learning"] += 1
            elif c.interval <= 21:
                mastery["reviewing"] += 1
            else:
                mastery["mastered"] += 1
        
        return mastery
    
    def _calculate_streak(self, cards: list) -> dict:
        """Streak ma'lumotlari"""
        # Eng oxirgi takrorlash sanasi
        review_dates = [c.last_review_date for c in cards if c.last_review_date]
        
        if not review_dates:
            return {"current": 0, "best": 0, "last_review": None}
        
        last_review = max(review_dates)
        today = utc_today()
        
        # Joriy streak
        current_streak = 0
        if last_review == today or last_review == today - timedelta(days=1):
            current_streak = 1
            # TODO: To'liq streak hisoblash uchun user_progress jadvalidan foydalanish kerak
        
        return {
            "current": current_streak,
            "best": current_streak,  # Placeholder
            "last_review": last_review
        }
    
    def _analyze_difficulty(self, cards: list) -> dict:
        """Qiyinlik tahlili"""
        difficulty = {"easy": 0, "medium": 0, "hard": 0}
        
        for c in cards:
            if c.total_reviews < 2:
                continue
            
            accuracy = (c.correct_reviews / c.total_reviews) * 100
            
            if accuracy >= 80:
                difficulty["easy"] += 1
            elif accuracy >= 50:
                difficulty["medium"] += 1
            else:
                difficulty["hard"] += 1
        
        return difficulty
    
    def _generate_progress_bars(self, mastery: dict, total: int) -> dict:
        """Mini progress barlar"""
        if total == 0:
            return {"mastered": "░░░░░░░░░░", "learning": "░░░░░░░░░░"}
        
        # Mastered progress
        mastered_pct = (mastery["mastered"] / total) * 10
        mastered_bar = "█" * int(mastered_pct) + "░" * (10 - int(mastered_pct))
        
        # Learning progress (learning + reviewing)
        learning_pct = ((mastery["learning"] + mastery["reviewing"]) / total) * 10
        learning_bar = "▓" * int(learning_pct) + "░" * (10 - int(learning_pct))
        
        return {
            "mastered": mastered_bar,
            "learning": learning_bar,
            "mastered_pct": (mastery["mastered"] / total) * 100,
            "learning_pct": ((mastery["learning"] + mastery["reviewing"]) / total) * 100
        }


class FlashcardExportImport:
    """Kartochkalarni export/import qilish"""
    
    def __init__(self, session):
        self.session = session
    
    async def export_deck_csv(self, user_id: int, deck_id: int) -> str:
        """Deckni CSV formatda eksport qilish"""
        import csv
        import io
        from sqlalchemy import select, and_
        
        # Get deck info
        deck_repo = FlashcardDeckRepository(self.session)
        deck = await deck_repo.get_by_id(deck_id)
        if not deck:
            return None
        
        # Get user's cards from this deck
        result = await self.session.execute(
            select(UserFlashcard).where(
                and_(
                    UserFlashcard.user_id == user_id,
                    UserFlashcard.card_id.in_(
                        select(Flashcard.id).where(Flashcard.deck_id == deck_id)
                    )
                )
            )
        )
        user_cards = list(result.scalars().all())
        
        # Get flashcard details
        card_repo = FlashcardRepository(self.session)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['front', 'back', 'example', 'easiness_factor', 'interval', 'repetitions'])
        
        for uc in user_cards:
            card = await card_repo.get_by_id(uc.card_id)
            if card:
                writer.writerow([
                    card.front_text,
                    card.back_text,
                    card.example_sentence or '',
                    uc.easiness_factor,
                    uc.interval,
                    uc.repetitions
                ])
        
        return output.getvalue()
    
    async def export_all_csv(self, user_id: int) -> str:
        """Barcha kartochkalarni CSV formatda eksport qilish"""
        import csv
        import io
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(UserFlashcard).where(UserFlashcard.user_id == user_id)
        )
        user_cards = list(result.scalars().all())
        
        if not user_cards:
            return None
        
        card_repo = FlashcardRepository(self.session)
        deck_repo = FlashcardDeckRepository(self.session)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header with deck name
        writer.writerow(['deck', 'front', 'back', 'example', 'easiness_factor', 'interval'])
        
        for uc in user_cards:
            card = await card_repo.get_by_id(uc.card_id)
            if card:
                deck = await deck_repo.get_by_id(card.deck_id)
                writer.writerow([
                    deck.name if deck else 'Unknown',
                    card.front_text,
                    card.back_text,
                    card.example_sentence or '',
                    uc.easiness_factor,
                    uc.interval
                ])
        
        return output.getvalue()
    
    async def import_csv(self, user_id: int, deck_id: int, csv_content: str) -> dict:
        """CSV dan kartochkalarni import qilish"""
        import csv
        import io
        
        reader = csv.DictReader(io.StringIO(csv_content))
        
        imported = 0
        skipped = 0
        errors = []
        
        card_repo = FlashcardRepository(self.session)
        user_fc_repo = UserFlashcardRepository(self.session)
        
        for row in reader:
            try:
                front = row.get('front', '').strip()
                back = row.get('back', '').strip()
                example = row.get('example', '').strip()
                
                if not front or not back:
                    skipped += 1
                    continue
                
                # Check if card already exists in deck
                existing = await card_repo.find_by_front(deck_id, front)
                if existing:
                    skipped += 1
                    continue
                
                # Create flashcard
                card = Flashcard(
                    deck_id=deck_id,
                    front_text=front,
                    back_text=back,
                    example_sentence=example if example else None
                )
                self.session.add(card)
                await self.session.flush()
                
                # Create user flashcard
                user_card = UserFlashcard(
                    user_id=user_id,
                    card_id=card.id,
                    easiness_factor=2.5,
                    interval=0,
                    repetitions=0
                )
                self.session.add(user_card)
                
                imported += 1
                
            except Exception as e:
                errors.append(str(e))
        
        await self.session.flush()
        
        # Update deck cards count
        deck_repo = FlashcardDeckRepository(self.session)
        deck = await deck_repo.get_by_id(deck_id)
        if deck:
            from sqlalchemy import func, select
            count_result = await self.session.execute(
                select(func.count(Flashcard.id)).where(Flashcard.deck_id == deck_id)
            )
            deck.cards_count = count_result.scalar() or 0
            await self.session.flush()
        
        return {
            'imported': imported,
            'skipped': skipped,
            'errors': errors[:5]  # First 5 errors only
        }


class SRTuningManager:
    """Spaced Repetition algoritm sozlamalari"""
    
    def __init__(self, session):
        self.session = session
    
    async def get_user_sr_settings(self, user_id: int, deck_id: int = 0) -> dict:
        """SR sozlamalarini olish"""
        from sqlalchemy import select, and_
        
        result = await self.session.execute(
            select(UserDeckProgress).where(
                and_(
                    UserDeckProgress.user_id == user_id,
                    UserDeckProgress.deck_id == deck_id
                )
            )
        )
        progress = result.scalar_one_or_none()
        
        if not progress:
            # Default sozlamalar
            return {
                "initial_ef": 2.5,
                "min_ef": 1.3,
                "first_interval": 1,
                "second_interval": 6,
                "easy_bonus": 1.3
            }
        
        return {
            "initial_ef": progress.sr_initial_ef or 2.5,
            "min_ef": progress.sr_min_ef or 1.3,
            "first_interval": progress.sr_first_interval or 1,
            "second_interval": progress.sr_second_interval or 6,
            "easy_bonus": progress.sr_easy_bonus or 1.3
        }
    
    async def update_sr_settings(
        self,
        user_id: int,
        deck_id: int = 0,
        initial_ef: float = None,
        min_ef: float = None,
        first_interval: int = None,
        second_interval: int = None,
        easy_bonus: float = None
    ) -> dict:
        """SR sozlamalarini yangilash"""
        from sqlalchemy import select, and_
        
        result = await self.session.execute(
            select(UserDeckProgress).where(
                and_(
                    UserDeckProgress.user_id == user_id,
                    UserDeckProgress.deck_id == deck_id
                )
            )
        )
        progress = result.scalar_one_or_none()
        
        if not progress:
            progress = UserDeckProgress(
                user_id=user_id,
                deck_id=deck_id
            )
            self.session.add(progress)
        
        # Sozlamalarni yangilash (validatsiya bilan)
        if initial_ef is not None:
            progress.sr_initial_ef = max(1.3, min(3.0, initial_ef))
        if min_ef is not None:
            progress.sr_min_ef = max(1.1, min(2.0, min_ef))
        if first_interval is not None:
            progress.sr_first_interval = max(1, min(7, first_interval))
        if second_interval is not None:
            progress.sr_second_interval = max(3, min(14, second_interval))
        if easy_bonus is not None:
            progress.sr_easy_bonus = max(1.0, min(2.0, easy_bonus))
        
        await self.session.flush()
        
        return await self.get_user_sr_settings(user_id, deck_id)
    
    async def reset_to_defaults(self, user_id: int, deck_id: int = 0) -> dict:
        """Default sozlamalarga qaytarish"""
        return await self.update_sr_settings(
            user_id, deck_id,
            initial_ef=2.5,
            min_ef=1.3,
            first_interval=1,
            second_interval=6,
            easy_bonus=1.3
        )
    
    @staticmethod
    def get_preset(preset_name: str) -> dict:
        """Tayyor presetlar"""
        presets = {
            "easy": {
                "initial_ef": 2.7,
                "min_ef": 1.5,
                "first_interval": 2,
                "second_interval": 7,
                "easy_bonus": 1.5,
                "description": "🟢 Oson - intervallar uzoqroq"
            },
            "normal": {
                "initial_ef": 2.5,
                "min_ef": 1.3,
                "first_interval": 1,
                "second_interval": 6,
                "easy_bonus": 1.3,
                "description": "🟡 Normal - standart SM-2"
            },
            "hard": {
                "initial_ef": 2.3,
                "min_ef": 1.2,
                "first_interval": 1,
                "second_interval": 4,
                "easy_bonus": 1.2,
                "description": "🔴 Qiyin - ko'proq takrorlash"
            },
            "aggressive": {
                "initial_ef": 2.1,
                "min_ef": 1.1,
                "first_interval": 1,
                "second_interval": 3,
                "easy_bonus": 1.1,
                "description": "🟣 Intensiv - tez o'rganish"
            }
        }
        return presets.get(preset_name, presets["normal"])
