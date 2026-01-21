"""
Question repository - Question data access
"""
import random
from typing import List, Optional
from sqlalchemy import select, func, and_

from src.database.models import Question, QuestionVote, Day, Level, Language
from src.repositories.base import BaseRepository


class QuestionRepository(BaseRepository[Question]):
    """Repository for Question model"""
    
    model = Question
    
    async def get_by_day(
        self,
        day_id: int,
        active_only: bool = True,
        limit: Optional[int] = None
    ) -> List[Question]:
        """Get questions for a specific day"""
        query = select(Question).where(Question.day_id == day_id)
        
        if active_only:
            query = query.where(Question.is_active == True)
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_level(
        self,
        level_id: int,
        active_only: bool = True,
        limit: Optional[int] = None
    ) -> List[Question]:
        """Get all questions for a level"""
        query = (
            select(Question)
            .join(Day)
            .where(Day.level_id == level_id)
        )
        
        if active_only:
            query = query.where(
                and_(Question.is_active == True, Day.is_active == True)
            )
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_language(
        self,
        language_id: int,
        active_only: bool = True,
        limit: Optional[int] = None
    ) -> List[Question]:
        """Get all questions for a language"""
        query = (
            select(Question)
            .join(Day)
            .join(Level)
            .where(Level.language_id == language_id)
        )
        
        if active_only:
            query = query.where(
                and_(
                    Question.is_active == True,
                    Day.is_active == True,
                    Level.is_active == True
                )
            )
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_random_questions(
        self,
        day_id: Optional[int] = None,
        level_id: Optional[int] = None,
        language_id: Optional[int] = None,
        count: int = 10,
        exclude_premium: bool = False
    ) -> List[Question]:
        """Get random questions with filters"""
        
        # Get filtered questions
        if day_id:
            questions = await self.get_by_day(day_id)
        elif level_id:
            questions = await self.get_by_level(level_id)
        elif language_id:
            questions = await self.get_by_language(language_id)
        else:
            questions = await self.get_all(limit=1000)
        
        # Filter premium if needed
        if exclude_premium:
            questions = [q for q in questions if not q.is_premium]
        
        # Shuffle and limit
        random.shuffle(questions)
        return questions[:count]
    
    async def record_answer(
        self,
        question_id: int,
        is_correct: bool
    ) -> None:
        """Record answer attempt on question"""
        question = await self.get_by_id(question_id)
        if question:
            question.record_answer(is_correct)
            await self.save(question)
    
    async def add_vote(
        self,
        question_id: int,
        user_id: int,
        vote_type: str  # 'up' or 'down'
    ) -> bool:
        """Add or update vote on question"""
        # Check existing vote
        existing = await self.session.execute(
            select(QuestionVote).where(
                and_(
                    QuestionVote.question_id == question_id,
                    QuestionVote.user_id == user_id
                )
            )
        )
        existing_vote = existing.scalar_one_or_none()
        
        question = await self.get_by_id(question_id)
        if not question:
            return False
        
        if existing_vote:
            # Update vote
            old_type = existing_vote.vote_type
            if old_type == vote_type:
                return True  # Same vote
            
            existing_vote.vote_type = vote_type
            
            # Update question counts
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
            
            if vote_type == 'up':
                question.upvotes += 1
            else:
                question.downvotes += 1
        
        await self.session.flush()
        return True
    
    async def get_vote(
        self,
        question_id: int,
        user_id: int
    ) -> Optional[str]:
        """Get user's vote on question"""
        result = await self.session.execute(
            select(QuestionVote).where(
                and_(
                    QuestionVote.question_id == question_id,
                    QuestionVote.user_id == user_id
                )
            )
        )
        vote = result.scalar_one_or_none()
        return vote.vote_type if vote else None
    
    async def count_by_day(self, day_id: int) -> int:
        """Count questions in day"""
        result = await self.session.execute(
            select(func.count())
            .select_from(Question)
            .where(
                and_(
                    Question.day_id == day_id,
                    Question.is_active == True
                )
            )
        )
        return result.scalar()
    
    async def count_by_level(self, level_id: int) -> int:
        """Count questions in level"""
        result = await self.session.execute(
            select(func.count())
            .select_from(Question)
            .join(Day)
            .where(
                and_(
                    Day.level_id == level_id,
                    Question.is_active == True,
                    Day.is_active == True
                )
            )
        )
        return result.scalar()
    
    async def bulk_create(self, questions_data: List[dict]) -> int:
        """Bulk create questions"""
        count = 0
        for data in questions_data:
            question = Question(**data)
            self.session.add(question)
            count += 1

        await self.session.flush()
        return count

    async def get_duel_questions(
        self,
        user1_id: int,
        user2_id: int,
        count: int = 5
    ) -> List[Question]:
        """
        Duel uchun savollar - ikkala o'yinchining xatolik tarixi asosida.

        Algoritm:
        1. Ikkala o'yinchi xato qilgan savollar (eng yuqori prioritet)
        2. Bitta o'yinchi xato qilgan savollar
        3. Kam takrorlangan (repetitions) savollar
        4. Tasodifiy savollar (yetmasa)
        """
        from src.database.models import SpacedRepetition

        # 1. Ikkala o'yinchining xato qilgan savollarini topish
        # (repetitions past yoki easiness_factor past bo'lganlar)

        # User 1 ning qiyin savollari
        result1 = await self.session.execute(
            select(SpacedRepetition.question_id).where(
                and_(
                    SpacedRepetition.user_id == user1_id,
                    SpacedRepetition.total_reviews > SpacedRepetition.correct_reviews  # Xato qilgan
                )
            ).order_by(SpacedRepetition.easiness_factor)  # Qiyinroqlari oldin
        )
        user1_hard_ids = set(r[0] for r in result1.all())

        # User 2 ning qiyin savollari
        result2 = await self.session.execute(
            select(SpacedRepetition.question_id).where(
                and_(
                    SpacedRepetition.user_id == user2_id,
                    SpacedRepetition.total_reviews > SpacedRepetition.correct_reviews  # Xato qilgan
                )
            ).order_by(SpacedRepetition.easiness_factor)
        )
        user2_hard_ids = set(r[0] for r in result2.all())

        # Prioritet bo'yicha savollarni yig'ish
        selected_questions = []

        # 1-prioritet: Ikkala o'yinchi xato qilgan savollar
        common_hard_ids = user1_hard_ids.intersection(user2_hard_ids)
        if common_hard_ids:
            result = await self.session.execute(
                select(Question).where(
                    and_(
                        Question.id.in_(list(common_hard_ids)),
                        Question.is_active == True
                    )
                )
            )
            selected_questions.extend(result.scalars().all())

        # 2-prioritet: Kamida bitta o'yinchi xato qilgan savollar
        if len(selected_questions) < count:
            single_hard_ids = user1_hard_ids.union(user2_hard_ids) - common_hard_ids
            if single_hard_ids:
                result = await self.session.execute(
                    select(Question).where(
                        and_(
                            Question.id.in_(list(single_hard_ids)),
                            Question.is_active == True
                        )
                    )
                )
                for q in result.scalars().all():
                    if q not in selected_questions:
                        selected_questions.append(q)

        # 3-prioritet: Global qiyin savollar (ko'p xato qilinganlar)
        if len(selected_questions) < count:
            existing_ids = [q.id for q in selected_questions]
            result = await self.session.execute(
                select(Question).where(
                    and_(
                        Question.is_active == True,
                        ~Question.id.in_(existing_ids) if existing_ids else True,
                        Question.times_shown > 0,
                        (Question.times_correct * 1.0 / Question.times_shown) < 0.7  # 70% dan past
                    )
                ).order_by((Question.times_correct * 1.0 / Question.times_shown))
                .limit(count * 2)
            )
            for q in result.scalars().all():
                if q not in selected_questions:
                    selected_questions.append(q)

        # 4-prioritet: Tasodifiy savollar (agar yetmasa)
        if len(selected_questions) < count:
            existing_ids = [q.id for q in selected_questions]
            result = await self.session.execute(
                select(Question).where(
                    and_(
                        Question.is_active == True,
                        ~Question.id.in_(existing_ids) if existing_ids else True
                    )
                )
            )
            all_questions = list(result.scalars().all())
            random.shuffle(all_questions)

            for q in all_questions:
                if q not in selected_questions:
                    selected_questions.append(q)
                if len(selected_questions) >= count:
                    break

        # Shuffle va limit
        random.shuffle(selected_questions)
        return selected_questions[:count]
