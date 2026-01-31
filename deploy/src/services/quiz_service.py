"""
Quiz service - Quiz business logic
"""
import random
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from src.database import get_session
from src.database.models import Question, User
from src.repositories import (
    QuestionRepository, UserRepository, ProgressRepository,
    StreakRepository, LanguageRepository, LevelRepository, DayRepository
)
from src.core.logging import get_logger, LoggerMixin
from src.core.exceptions import NoQuestionsError, QuizAlreadyActiveError
from src.core.redis import QuizSessionManager, PollDataManager

logger = get_logger(__name__)


@dataclass
class QuizQuestion:
    """Processed quiz question ready for display"""
    id: int
    text: str
    options: List[str]
    correct_index: int
    original_correct: str
    explanation: Optional[str] = None
    audio_url: Optional[str] = None
    
    @classmethod
    def from_question(cls, q: Question, shuffle: bool = True) -> "QuizQuestion":
        """Create from Question model"""
        if shuffle:
            options, correct_idx = q.get_shuffled_options()
        else:
            options = q.options_list
            correct_idx = q.correct_index
        
        return cls(
            id=q.id,
            text=q.question_text,
            options=options,
            correct_index=correct_idx,
            original_correct=q.correct_option,
            explanation=q.explanation,
            audio_url=q.audio_url
        )


@dataclass
class QuizResult:
    """Quiz result data"""
    user_id: int
    correct: int
    wrong: int
    total: int
    score: float
    answers: List[Dict[str, Any]] = field(default_factory=list)
    time_taken: float = 0.0
    avg_time: float = 0.0
    
    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.correct / self.total) * 100
    
    @property
    def is_perfect(self) -> bool:
        return self.correct == self.total and self.total > 0


@dataclass 
class QuizSession:
    """Active quiz session"""
    user_id: int
    chat_id: int
    questions: List[QuizQuestion]
    current_index: int = 0
    results: List[Dict] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    question_start_time: Optional[datetime] = None
    
    # Context
    language_id: Optional[int] = None
    level_id: Optional[int] = None
    day_id: Optional[int] = None
    
    @property
    def current_question(self) -> Optional[QuizQuestion]:
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None
    
    @property
    def is_finished(self) -> bool:
        return self.current_index >= len(self.questions)
    
    @property
    def progress_text(self) -> str:
        return f"{self.current_index + 1}/{len(self.questions)}"
    
    def record_answer(
        self,
        selected_index: int,
        time_taken: float = 0.0
    ) -> bool:
        """Record answer and return if correct"""
        q = self.current_question
        if not q:
            return False
        
        is_correct = selected_index == q.correct_index
        
        self.results.append({
            "question_id": q.id,
            "selected": selected_index,
            "correct": q.correct_index,
            "is_correct": is_correct,
            "time": time_taken
        })
        
        return is_correct
    
    def next_question(self) -> Optional[QuizQuestion]:
        """Move to next question"""
        self.current_index += 1
        self.question_start_time = datetime.utcnow()
        return self.current_question
    
    def get_result(self) -> QuizResult:
        """Calculate final result"""
        correct = sum(1 for r in self.results if r["is_correct"])
        total = len(self.results)
        times = [r["time"] for r in self.results if r["time"] > 0]
        
        return QuizResult(
            user_id=self.user_id,
            correct=correct,
            wrong=total - correct,
            total=total,
            score=(correct / total * 100) if total > 0 else 0,
            answers=self.results,
            time_taken=sum(times),
            avg_time=sum(times) / len(times) if times else 0
        )


class QuizService(LoggerMixin):
    """Quiz business logic service"""
    
    async def get_languages(self) -> List[Dict]:
        """Get available languages"""
        async with get_session() as session:
            repo = LanguageRepository(session)
            languages = await repo.get_active_languages()
            
            return [
                {
                    "id": lang.id,
                    "name": lang.name,
                    "code": lang.code,
                    "flag": lang.flag,
                    "levels_count": lang.levels_count
                }
                for lang in languages
            ]
    
    async def get_levels(self, language_id: int = None) -> List[Dict]:
        """Get levels for language or all levels if language_id is None"""
        async with get_session() as session:
            repo = LevelRepository(session)
            if language_id:
                levels = await repo.get_by_language(language_id)
            else:
                levels = await repo.get_all_active()

            return [
                {
                    "id": level.id,
                    "name": level.name,
                    "description": level.description,
                    "days_count": level.days_count,
                    "questions_count": level.questions_count,
                    "is_premium": level.is_premium
                }
                for level in levels
            ]
    
    async def get_days(self, level_id: int) -> List[Dict]:
        """Get days for level"""
        async with get_session() as session:
            repo = DayRepository(session)
            days = await repo.get_by_level(level_id)
            
            return [
                {
                    "id": day.id,
                    "number": day.day_number,
                    "name": day.display_name,
                    "topic": day.topic,
                    "questions_count": day.questions_count,
                    "is_premium": day.is_premium
                }
                for day in days
            ]
    
    async def create_quiz_session(
        self,
        user_id: int,
        chat_id: int = 0,
        day_id: Optional[int] = None,
        level_id: Optional[int] = None,
        language_id: Optional[int] = None,
        questions_count: int = 10,
        shuffle: bool = True,
        exclude_premium: bool = False
    ) -> QuizSession:
        """Create new quiz session"""
        
        # Check for existing session
        if await QuizSessionManager.has_active_session(user_id, chat_id):
            raise QuizAlreadyActiveError(chat_id)
        
        async with get_session() as session:
            repo = QuestionRepository(session)
            
            # Get questions
            questions = await repo.get_random_questions(
                day_id=day_id,
                level_id=level_id,
                language_id=language_id,
                count=questions_count,
                exclude_premium=exclude_premium
            )
            
            if not questions:
                raise NoQuestionsError("No questions available for selected filters")
            
            # Convert to quiz questions
            quiz_questions = [
                QuizQuestion.from_question(q, shuffle=shuffle)
                for q in questions
            ]
            
            # Create session
            quiz_session = QuizSession(
                user_id=user_id,
                chat_id=chat_id,
                questions=quiz_questions,
                language_id=language_id,
                level_id=level_id,
                day_id=day_id,
                question_start_time=datetime.utcnow()
            )
            
            # Save to Redis
            await QuizSessionManager.create_session(
                user_id=user_id,
                chat_id=chat_id,
                data={
                    "language_id": language_id,
                    "level_id": level_id,
                    "day_id": day_id,
                    "total_questions": len(quiz_questions),
                    "current_index": 0,
                    "results": []
                }
            )
            
            return quiz_session
    
    async def process_answer(
        self,
        user_id: int,
        chat_id: int,
        question_id: int,
        selected_index: int,
        is_correct: bool,
        time_taken: float = 0.0
    ) -> Dict:
        """Process quiz answer"""
        
        # Update session in Redis
        session_data = await QuizSessionManager.get_session(user_id, chat_id)
        if not session_data:
            return {"error": "No active session"}
        
        results = session_data.get("results", [])
        results.append({
            "question_id": question_id,
            "selected": selected_index,
            "is_correct": is_correct,
            "time": time_taken
        })
        
        await QuizSessionManager.update_session(
            user_id, chat_id,
            {
                "results": results,
                "current_index": session_data.get("current_index", 0) + 1
            }
        )
        
        # Record answer in DB
        async with get_session() as session:
            repo = QuestionRepository(session)
            await repo.record_answer(question_id, is_correct)
        
        return {"recorded": True}
    
    async def finish_quiz(
        self,
        user_id: int,
        chat_id: int = 0
    ) -> Optional[QuizResult]:
        """Finish quiz and save results"""
        
        # Get session data
        session_data = await QuizSessionManager.get_session(user_id, chat_id)
        if not session_data:
            return None
        
        results = session_data.get("results", [])
        correct = sum(1 for r in results if r.get("is_correct"))
        total = len(results)
        times = [r.get("time", 0) for r in results]
        
        result = QuizResult(
            user_id=user_id,
            correct=correct,
            wrong=total - correct,
            total=total,
            score=(correct / total * 100) if total > 0 else 0,
            answers=results,
            time_taken=sum(times),
            avg_time=sum(times) / len(times) if times else 0
        )
        
        # Save to database
        async with get_session() as session:
            # Save progress
            progress_repo = ProgressRepository(session)
            await progress_repo.save_quiz_result(
                user_id=user_id,
                correct=result.correct,
                wrong=result.wrong,
                total=result.total,
                score=result.score,
                avg_time=result.avg_time,
                total_time=result.time_taken,
                language_id=session_data.get("language_id"),
                level_id=session_data.get("level_id"),
                day_id=session_data.get("day_id"),
                quiz_type="personal" if chat_id == 0 else "group",
                chat_id=chat_id if chat_id else None
            )
            
            # Update user stats
            user_repo = UserRepository(session)
            await user_repo.update_stats(user_id, result.correct, result.total)
            
            # Update streak
            streak_repo = StreakRepository(session)
            streak_result = await streak_repo.update_streak(user_id)
            result.streak_info = streak_result
        
        # Clean up session
        await QuizSessionManager.delete_session(user_id, chat_id)
        
        return result
    
    async def cancel_quiz(self, user_id: int, chat_id: int = 0) -> bool:
        """Cancel active quiz"""
        return await QuizSessionManager.delete_session(user_id, chat_id)
    
    async def has_active_quiz(self, user_id: int, chat_id: int = 0) -> bool:
        """Check if user has active quiz"""
        return await QuizSessionManager.has_active_session(user_id, chat_id)


# Global service instance
quiz_service = QuizService()
