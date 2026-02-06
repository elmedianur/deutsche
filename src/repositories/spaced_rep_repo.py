"""
Spaced Repetition Repository - SM-2 algoritmi
"""
from datetime import date, timedelta
from typing import List, Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import SpacedRepetition, Question
from src.repositories.base import BaseRepository


class SpacedRepetitionRepository(BaseRepository[SpacedRepetition]):
    """Repository for SpacedRepetition (SM-2)"""
    model = SpacedRepetition
    
    async def get_or_create(self, user_id: int, question_id: int) -> SpacedRepetition:
        """Foydalanuvchi-savol uchun SM-2 record olish yoki yaratish"""
        result = await self.session.execute(
            select(SpacedRepetition).where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.question_id == question_id
                )
            )
        )
        sr = result.scalar_one_or_none()
        
        if not sr:
            sr = SpacedRepetition(
                user_id=user_id,
                question_id=question_id
            )
            self.session.add(sr)
            await self.session.flush()
        
        return sr
    
    async def record_answer(self, user_id: int, question_id: int, is_correct: bool) -> SpacedRepetition:
        """
        Javobni qayd qilish va SM-2 ni yangilash
        
        is_correct=True -> quality=4 (yaxshi biladi)
        is_correct=False -> quality=1 (xato)
        """
        sr = await self.get_or_create(user_id, question_id)
        
        quality = 4 if is_correct else 1
        sr.update_after_review(quality)
        
        await self.session.flush()
        return sr
    
    async def get_due_questions(self, user_id: int, day_id: int, limit: int = 10) -> List[int]:
        """
        Takrorlash kerak bo'lgan savollar ID lari
        (next_review_date <= bugun)
        """
        today = date.today()
        
        result = await self.session.execute(
            select(SpacedRepetition.question_id).where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.next_review_date <= today
                )
            ).limit(limit)
        )
        
        return [r[0] for r in result.fetchall()]
    
    async def get_new_questions(
        self, 
        user_id: int, 
        day_id: int, 
        limit: int = 10
    ) -> List[int]:
        """
        Hali ko'rilmagan yangi savollar
        (SpacedRepetition da yo'q)
        """
        # Foydalanuvchi ko'rgan savollar
        seen_result = await self.session.execute(
            select(SpacedRepetition.question_id).where(
                SpacedRepetition.user_id == user_id
            )
        )
        seen_ids = set(r[0] for r in seen_result.fetchall())
        
        # Day dagi barcha savollar
        questions_result = await self.session.execute(
            select(Question.id).where(
                and_(
                    Question.day_id == day_id,
                    Question.is_active == True
                )
            )
        )
        all_ids = [r[0] for r in questions_result.fetchall()]
        
        # Ko'rilmagan savollar
        new_ids = [qid for qid in all_ids if qid not in seen_ids]
        
        return new_ids[:limit]
    
    async def get_mastered_count(self, user_id: int) -> int:
        """
        O'zlashtirilgan savollar soni
        (interval >= 21 kun = yaxshi biladi)
        """
        result = await self.session.execute(
            select(SpacedRepetition).where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.interval >= 21
                )
            )
        )
        return len(result.scalars().all())
    
    async def get_learning_count(self, user_id: int) -> int:
        """O'rganilayotgan savollar soni (interval < 21)"""
        result = await self.session.execute(
            select(SpacedRepetition).where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.interval < 21
                )
            )
        )
        return len(result.scalars().all())
    
    async def get_user_stats(self, user_id: int) -> dict:
        """Foydalanuvchi SM-2 statistikasi"""
        result = await self.session.execute(
            select(SpacedRepetition).where(
                SpacedRepetition.user_id == user_id
            )
        )
        records = result.scalars().all()
        
        if not records:
            return {
                "total": 0,
                "mastered": 0,
                "learning": 0,
                "due_today": 0,
                "accuracy": 0
            }
        
        today = date.today()
        total_reviews = sum(r.total_reviews for r in records)
        correct_reviews = sum(r.correct_reviews for r in records)
        
        return {
            "total": len(records),
            "mastered": len([r for r in records if r.interval >= 21]),
            "learning": len([r for r in records if r.interval < 21]),
            "due_today": len([r for r in records if r.next_review_date <= today]),
            "accuracy": round(correct_reviews / total_reviews * 100, 1) if total_reviews > 0 else 0
        }
