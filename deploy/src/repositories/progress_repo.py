"""
Progress and Streak repository
"""
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import select, func, desc, and_

from src.database.models import UserProgress, UserStreak, SpacedRepetition
from src.repositories.base import BaseRepository


class ProgressRepository(BaseRepository[UserProgress]):
    """Repository for UserProgress model"""
    
    model = UserProgress
    
    async def save_quiz_result(
        self,
        user_id: int,
        correct: int,
        wrong: int,
        total: int,
        score: float = 0.0,
        avg_time: float = 0.0,
        total_time: float = 0.0,
        language_id: int = None,
        level_id: int = None,
        day_id: int = None,
        quiz_type: str = "personal",
        chat_id: int = None
    ) -> UserProgress:
        """Save quiz result"""
        return await self.create(
            user_id=user_id,
            language_id=language_id,
            level_id=level_id,
            day_id=day_id,
            correct_answers=correct,
            wrong_answers=wrong,
            total_questions=total,
            score=score,
            avg_time=avg_time,
            total_time=total_time,
            quiz_type=quiz_type,
            chat_id=chat_id,
            completed_at=datetime.utcnow()
        )
    
    async def get_user_history(
        self,
        user_id: int,
        limit: int = 20,
        quiz_type: str = None
    ) -> List[UserProgress]:
        """Get user's quiz history"""
        query = select(UserProgress).where(UserProgress.user_id == user_id)
        
        if quiz_type:
            query = query.where(UserProgress.quiz_type == quiz_type)
        
        query = query.order_by(desc(UserProgress.completed_at)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_user_stats(self, user_id: int) -> dict:
        """Get aggregated user statistics"""
        result = await self.session.execute(
            select(
                func.count().label("total_quizzes"),
                func.sum(UserProgress.correct_answers).label("total_correct"),
                func.sum(UserProgress.total_questions).label("total_questions"),
                func.avg(UserProgress.score).label("avg_score"),
                func.avg(UserProgress.avg_time).label("avg_time")
            ).where(UserProgress.user_id == user_id)
        )
        row = result.one()
        
        return {
            "total_quizzes": row.total_quizzes or 0,
            "total_correct": int(row.total_correct or 0),
            "total_questions": int(row.total_questions or 0),
            "avg_score": float(row.avg_score or 0),
            "avg_time": float(row.avg_time or 0),
            "accuracy": (
                (int(row.total_correct or 0) / int(row.total_questions or 1)) * 100
                if row.total_questions else 0
            )
        }
    
    async def get_day_stats(
        self,
        user_id: int,
        day_id: int
    ) -> Optional[dict]:
        """Get user stats for specific day"""
        result = await self.session.execute(
            select(
                func.count().label("attempts"),
                func.max(UserProgress.score).label("best_score"),
                func.sum(UserProgress.correct_answers).label("total_correct"),
                func.sum(UserProgress.total_questions).label("total_questions")
            ).where(
                and_(
                    UserProgress.user_id == user_id,
                    UserProgress.day_id == day_id
                )
            )
        )
        row = result.one()
        
        if not row.attempts:
            return None
        
        return {
            "attempts": row.attempts,
            "best_score": float(row.best_score or 0),
            "total_correct": int(row.total_correct or 0),
            "total_questions": int(row.total_questions or 0)
        }
    
    async def get_leaderboard(
        self,
        day_id: int = None,
        level_id: int = None,
        language_id: int = None,
        limit: int = 10
    ) -> List[dict]:
        """Get leaderboard"""
        query = select(
            UserProgress.user_id,
            func.sum(UserProgress.correct_answers).label("total_correct"),
            func.count().label("quiz_count"),
            func.max(UserProgress.score).label("best_score")
        )
        
        if day_id:
            query = query.where(UserProgress.day_id == day_id)
        elif level_id:
            query = query.where(UserProgress.level_id == level_id)
        elif language_id:
            query = query.where(UserProgress.language_id == language_id)
        
        query = (
            query
            .group_by(UserProgress.user_id)
            .order_by(desc("total_correct"))
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return [
            {
                "user_id": row.user_id,
                "total_correct": int(row.total_correct or 0),
                "quiz_count": row.quiz_count,
                "best_score": float(row.best_score or 0)
            }
            for row in result.all()
        ]


class StreakRepository(BaseRepository[UserStreak]):
    """Repository for UserStreak model"""
    
    model = UserStreak
    
    async def get_by_user_id(self, user_id: int) -> Optional[UserStreak]:
        """Get streak by user_id"""
        result = await self.session.execute(
            select(UserStreak).where(UserStreak.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, user_id: int) -> UserStreak:
        """Get or create streak"""
        streak = await self.get_by_user_id(user_id)
        if streak:
            return streak
        
        return await self.create(user_id=user_id)
    
    async def update_streak(self, user_id: int) -> dict:
        """Update user's streak and return status"""
        streak = await self.get_or_create(user_id)
        result = streak.check_and_update()
        await self.save(streak)
        return result
    
    async def add_freeze(self, user_id: int, count: int = 1) -> bool:
        """Add streak freeze to user"""
        streak = await self.get_by_user_id(user_id)
        if not streak:
            return False
        
        streak.freeze_count += count
        await self.save(streak)
        return True
    
    async def get_top_streaks(self, limit: int = 10) -> List[UserStreak]:
        """Get top current streaks"""
        result = await self.session.execute(
            select(UserStreak)
            .where(UserStreak.current_streak > 0)
            .order_by(desc(UserStreak.current_streak))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_longest_streaks(self, limit: int = 10) -> List[UserStreak]:
        """Get longest ever streaks"""
        result = await self.session.execute(
            select(UserStreak)
            .where(UserStreak.longest_streak > 0)
            .order_by(desc(UserStreak.longest_streak))
            .limit(limit)
        )
        return list(result.scalars().all())


class SpacedRepetitionRepository(BaseRepository[SpacedRepetition]):
    """Repository for SpacedRepetition model"""
    
    model = SpacedRepetition
    
    async def get_due_questions(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[SpacedRepetition]:
        """Get questions due for review"""
        result = await self.session.execute(
            select(SpacedRepetition).where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.next_review_date <= date.today()
                )
            ).order_by(SpacedRepetition.next_review_date).limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_or_create(
        self,
        user_id: int,
        question_id: int
    ) -> SpacedRepetition:
        """Get or create spaced repetition record"""
        result = await self.session.execute(
            select(SpacedRepetition).where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.question_id == question_id
                )
            )
        )
        sr = result.scalar_one_or_none()
        
        if sr:
            return sr
        
        return await self.create(
            user_id=user_id,
            question_id=question_id
        )
    
    async def record_review(
        self,
        user_id: int,
        question_id: int,
        quality: int  # 0-5
    ) -> SpacedRepetition:
        """Record review and update SM-2 parameters"""
        sr = await self.get_or_create(user_id, question_id)
        sr.update_after_review(quality)
        await self.save(sr)
        return sr
    
    async def get_user_stats(self, user_id: int) -> dict:
        """Get spaced repetition stats for user"""
        result = await self.session.execute(
            select(
                func.count().label("total"),
                func.sum(
                    func.cast(SpacedRepetition.next_review_date <= date.today(), int)
                ).label("due"),
                func.avg(SpacedRepetition.easiness_factor).label("avg_ef")
            ).where(SpacedRepetition.user_id == user_id)
        )
        row = result.one()
        
        return {
            "total_cards": row.total or 0,
            "due_today": int(row.due or 0),
            "avg_easiness": float(row.avg_ef or 2.5)
        }
