"""
Quiz repository - database operations for questions, languages, progress
"""
from datetime import datetime, date
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    Language, Level, Day, Question, QuestionVote,
    UserProgress, SpacedRepetition
)
from src.repositories.base import BaseRepository
from src.core.logging import get_logger
from src.core.utils import secure_shuffle

logger = get_logger(__name__)


class LanguageRepository(BaseRepository[Language]):
    model = Language
    """Language repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_active_languages(self) -> List[Language]:
        """Get all active languages with levels"""
        query = (
            select(Language)
            .where(Language.is_active == True)
            .options(selectinload(Language.levels))
            .order_by(Language.display_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())
    
    async def get_by_code(self, code: str) -> Optional[Language]:
        """Get language by code"""
        query = (
            select(Language)
            .where(Language.code == code.lower())
            .options(selectinload(Language.levels))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class LevelRepository(BaseRepository[Level]):
    model = Level
    """Level repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_by_language(self, language_id: int) -> List[Level]:
        """Get all levels for a language"""
        query = (
            select(Level)
            .where(and_(
                Level.language_id == language_id,
                Level.is_active == True
            ))
            .options(selectinload(Level.days))
            .order_by(Level.display_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())
    
    async def get_with_stats(self, level_id: int) -> Optional[Level]:
        """Get level with question counts"""
        query = (
            select(Level)
            .where(Level.id == level_id)
            .options(
                selectinload(Level.language),
                selectinload(Level.days).selectinload(Day.questions)
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class DayRepository(BaseRepository[Day]):
    model = Day
    """Day repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_by_level(self, level_id: int) -> List[Day]:
        """Get all days for a level"""
        query = (
            select(Day)
            .where(and_(
                Day.level_id == level_id,
                Day.is_active == True
            ))
            .options(selectinload(Day.questions))
            .order_by(Day.day_number)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())
    
    async def get_with_questions(self, day_id: int) -> Optional[Day]:
        """Get day with all questions"""
        query = (
            select(Day)
            .where(Day.id == day_id)
            .options(
                selectinload(Day.level).selectinload(Level.language),
                selectinload(Day.questions)
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class QuestionRepository(BaseRepository[Question]):
    model = Question
    """Question repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_questions_by_day(
        self,
        day_id: int,
        limit: Optional[int] = None,
        shuffle: bool = True,
        include_premium: bool = True
    ) -> List[Question]:
        """Get questions for a day"""
        query = select(Question).where(
            and_(
                Question.day_id == day_id,
                Question.is_active == True
            )
        )
        
        if not include_premium:
            query = query.where(Question.is_premium == False)
        
        result = await self.session.execute(query)
        questions = list(result.scalars().all())
        
        if shuffle:
            questions = secure_shuffle(questions)
        
        if limit:
            questions = questions[:limit]
        
        return questions
    
    async def get_questions_by_level(
        self,
        level_id: int,
        limit: Optional[int] = None,
        shuffle: bool = True,
        include_premium: bool = True
    ) -> List[Question]:
        """Get questions for entire level"""
        query = (
            select(Question)
            .join(Day)
            .where(
                and_(
                    Day.level_id == level_id,
                    Question.is_active == True,
                    Day.is_active == True
                )
            )
        )
        
        if not include_premium:
            query = query.where(Question.is_premium == False)
        
        result = await self.session.execute(query)
        questions = list(result.scalars().all())
        
        if shuffle:
            questions = secure_shuffle(questions)
        
        if limit:
            questions = questions[:limit]
        
        return questions
    
    async def get_random_questions(
        self,
        language_id: int,
        count: int = 10,
        level_id: Optional[int] = None,
        exclude_ids: Optional[List[int]] = None,
        include_premium: bool = True
    ) -> List[Question]:
        """Get random questions"""
        query = (
            select(Question)
            .join(Day)
            .join(Level)
            .where(
                and_(
                    Level.language_id == language_id,
                    Question.is_active == True
                )
            )
        )
        
        if level_id:
            query = query.where(Day.level_id == level_id)
        
        if not include_premium:
            query = query.where(Question.is_premium == False)
        
        if exclude_ids:
            query = query.where(Question.id.notin_(exclude_ids))
        
        result = await self.session.execute(query)
        questions = list(result.scalars().all())
        
        questions = secure_shuffle(questions)
        return questions[:count]
    
    async def record_answer(
        self,
        question_id: int,
        is_correct: bool
    ) -> None:
        """Record answer statistics"""
        question = await self.get_by_id(question_id)
        if question:
            question.times_shown += 1
            if is_correct:
                question.times_correct += 1
            await self.session.flush()
    
    async def add_vote(
        self,
        question_id: int,
        user_id: int,
        vote_type: str  # 'up' or 'down'
    ) -> bool:
        """Add vote to question"""
        # Check if already voted
        query = select(QuestionVote).where(
            and_(
                QuestionVote.question_id == question_id,
                QuestionVote.user_id == user_id
            )
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            if existing.vote_type == vote_type:
                return False  # Already voted same
            
            # Change vote
            old_type = existing.vote_type
            existing.vote_type = vote_type
            
            # Update question counts
            question = await self.get_by_id(question_id)
            if question:
                if old_type == 'up':
                    question.upvotes -= 1
                else:
                    question.downvotes -= 1
                
                if vote_type == 'up':
                    question.upvotes += 1
                else:
                    question.downvotes += 1
        else:
            # New vote
            vote = QuestionVote(
                question_id=question_id,
                user_id=user_id,
                vote_type=vote_type
            )
            self.session.add(vote)
            
            question = await self.get_by_id(question_id)
            if question:
                if vote_type == 'up':
                    question.upvotes += 1
                else:
                    question.downvotes += 1
        
        await self.session.flush()
        return True
    
    async def count_by_day(self, day_id: int) -> int:
        """Count questions in a day"""
        return await self.count(day_id=day_id, is_active=True)
    
    async def count_by_level(self, level_id: int) -> int:
        """Count questions in a level"""
        query = (
            select(func.count())
            .select_from(Question)
            .join(Day)
            .where(
                and_(
                    Day.level_id == level_id,
                    Question.is_active == True
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0


class UserProgressRepository(BaseRepository[UserProgress]):
    model = UserProgress
    """User progress repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def save_progress(
        self,
        user_id: int,
        correct: int,
        wrong: int,
        total: int,
        score: float,
        avg_time: float,
        total_time: float,
        language_id: Optional[int] = None,
        level_id: Optional[int] = None,
        day_id: Optional[int] = None,
        quiz_type: str = "personal",
        chat_id: Optional[int] = None
    ) -> UserProgress:
        """Save quiz progress"""
        progress = UserProgress(
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
        self.session.add(progress)
        await self.session.flush()
        return progress
    
    async def get_user_progress(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[UserProgress]:
        """Get user's recent progress"""
        query = (
            select(UserProgress)
            .where(UserProgress.user_id == user_id)
            .order_by(UserProgress.completed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_day_progress(
        self,
        user_id: int,
        day_id: int
    ) -> Optional[UserProgress]:
        """Get user's best progress for a day"""
        query = (
            select(UserProgress)
            .where(
                and_(
                    UserProgress.user_id == user_id,
                    UserProgress.day_id == day_id
                )
            )
            .order_by(UserProgress.score.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_stats(self, user_id: int) -> dict:
        """Get aggregated user statistics"""
        query = (
            select(
                func.count().label("total_quizzes"),
                func.sum(UserProgress.correct_answers).label("total_correct"),
                func.sum(UserProgress.total_questions).label("total_questions"),
                func.avg(UserProgress.score).label("avg_score"),
                func.avg(UserProgress.avg_time).label("avg_time")
            )
            .where(UserProgress.user_id == user_id)
        )
        result = await self.session.execute(query)
        row = result.one()
        
        return {
            "total_quizzes": row.total_quizzes or 0,
            "total_correct": row.total_correct or 0,
            "total_questions": row.total_questions or 0,
            "avg_score": float(row.avg_score or 0),
            "avg_time": float(row.avg_time or 0)
        }


class SpacedRepetitionRepository(BaseRepository[SpacedRepetition]):
    model = SpacedRepetition
    """Spaced repetition repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_due_questions(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[SpacedRepetition]:
        """Get questions due for review"""
        query = (
            select(SpacedRepetition)
            .where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.next_review_date <= date.today()
                )
            )
            .order_by(SpacedRepetition.next_review_date)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_or_create_sr(
        self,
        user_id: int,
        question_id: int
    ) -> Tuple[SpacedRepetition, bool]:
        """Get or create spaced repetition record"""
        sr = await self.get_one(user_id=user_id, question_id=question_id)
        if sr:
            return sr, False
        
        sr = SpacedRepetition(
            user_id=user_id,
            question_id=question_id,
            next_review_date=date.today()
        )
        self.session.add(sr)
        await self.session.flush()
        return sr, True
    
    async def update_after_review(
        self,
        user_id: int,
        question_id: int,
        quality: int
    ) -> SpacedRepetition:
        """Update SR after review"""
        sr, _ = await self.get_or_create_sr(user_id, question_id)
        sr.update_after_review(quality)
        await self.session.flush()
        return sr
    
    async def count_due(self, user_id: int) -> int:
        """Count due questions"""
        query = (
            select(func.count())
            .select_from(SpacedRepetition)
            .where(
                and_(
                    SpacedRepetition.user_id == user_id,
                    SpacedRepetition.next_review_date <= date.today()
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def get_stats(self, user_id: int) -> dict:
        """Get SR statistics for user"""
        # Total questions
        total = await self.count(user_id=user_id)
        
        # Due today
        due = await self.count_due(user_id)
        
        # By mastery level
        query = (
            select(
                func.count().filter(SpacedRepetition.interval <= 1).label("new"),
                func.count().filter(
                    and_(SpacedRepetition.interval > 1, SpacedRepetition.interval <= 7)
                ).label("learning"),
                func.count().filter(
                    and_(SpacedRepetition.interval > 7, SpacedRepetition.interval <= 30)
                ).label("reviewing"),
                func.count().filter(SpacedRepetition.interval > 30).label("mastered")
            )
            .where(SpacedRepetition.user_id == user_id)
        )
        result = await self.session.execute(query)
        row = result.one()
        
        return {
            "total": total,
            "due": due,
            "new": row.new or 0,
            "learning": row.learning or 0,
            "reviewing": row.reviewing or 0,
            "mastered": row.mastered or 0
        }
