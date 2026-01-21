"""
Quiz service - business logic for quiz operations
"""
import random
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Language, Level, Day, Question, UserProgress
)
from src.repositories.quiz import (
    LanguageRepository, LevelRepository, DayRepository,
    QuestionRepository, UserProgressRepository, SpacedRepetitionRepository
)
from src.core.logging import get_logger, LoggerMixin
from src.core.exceptions import NoQuestionsError, QuizAlreadyActiveError

logger = get_logger(__name__)


@dataclass
class QuizQuestion:
    """Prepared quiz question"""
    id: int
    question_id: int
    text: str
    options: List[str]
    correct_index: int
    explanation: Optional[str] = None
    audio_url: Optional[str] = None
    
    @classmethod
    def from_model(cls, question: Question, index: int = 0) -> "QuizQuestion":
        """Create from Question model with shuffled options"""
        options, correct_idx = question.get_shuffled_options()
        return cls(
            id=index,
            question_id=question.id,
            text=question.question_text,
            options=options,
            correct_index=correct_idx,
            explanation=question.explanation,
            audio_url=question.audio_url
        )


@dataclass
class QuizSession:
    """Quiz session state"""
    user_id: int
    chat_id: int
    language_id: int
    level_id: Optional[int] = None
    day_id: Optional[int] = None
    
    questions: List[QuizQuestion] = field(default_factory=list)
    current_index: int = 0
    
    answers: Dict[int, bool] = field(default_factory=dict)  # question_id -> is_correct
    answer_times: Dict[int, float] = field(default_factory=dict)  # question_id -> time_seconds
    
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    quiz_type: str = "personal"  # personal, group, duel
    time_per_question: int = 30
    
    @property
    def total_questions(self) -> int:
        return len(self.questions)
    
    @property
    def current_question(self) -> Optional[QuizQuestion]:
        if 0 <= self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None
    
    @property
    def is_finished(self) -> bool:
        return self.current_index >= len(self.questions)
    
    @property
    def correct_count(self) -> int:
        return sum(1 for v in self.answers.values() if v)
    
    @property
    def wrong_count(self) -> int:
        return sum(1 for v in self.answers.values() if not v)
    
    @property
    def score(self) -> float:
        if not self.answers:
            return 0.0
        return (self.correct_count / len(self.answers)) * 100
    
    @property
    def avg_time(self) -> float:
        if not self.answer_times:
            return 0.0
        return sum(self.answer_times.values()) / len(self.answer_times)
    
    @property
    def total_time(self) -> float:
        return sum(self.answer_times.values())
    
    def record_answer(
        self,
        question_id: int,
        is_correct: bool,
        time_seconds: float
    ) -> None:
        """Record answer for question"""
        self.answers[question_id] = is_correct
        self.answer_times[question_id] = time_seconds
    
    def next_question(self) -> Optional[QuizQuestion]:
        """Move to next question"""
        self.current_index += 1
        return self.current_question
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage"""
        return {
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "language_id": self.language_id,
            "level_id": self.level_id,
            "day_id": self.day_id,
            "questions": [
                {
                    "id": q.id,
                    "question_id": q.question_id,
                    "text": q.text,
                    "options": q.options,
                    "correct_index": q.correct_index,
                    "explanation": q.explanation,
                    "audio_url": q.audio_url
                }
                for q in self.questions
            ],
            "current_index": self.current_index,
            "answers": self.answers,
            "answer_times": self.answer_times,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "quiz_type": self.quiz_type,
            "time_per_question": self.time_per_question
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "QuizSession":
        """Create from dictionary"""
        session = cls(
            user_id=data["user_id"],
            chat_id=data["chat_id"],
            language_id=data["language_id"],
            level_id=data.get("level_id"),
            day_id=data.get("day_id"),
            current_index=data.get("current_index", 0),
            answers={int(k): v for k, v in data.get("answers", {}).items()},
            answer_times={int(k): v for k, v in data.get("answer_times", {}).items()},
            quiz_type=data.get("quiz_type", "personal"),
            time_per_question=data.get("time_per_question", 30)
        )
        
        if data.get("started_at"):
            session.started_at = datetime.fromisoformat(data["started_at"])
        
        # Rebuild questions
        for q_data in data.get("questions", []):
            session.questions.append(QuizQuestion(
                id=q_data["id"],
                question_id=q_data["question_id"],
                text=q_data["text"],
                options=q_data["options"],
                correct_index=q_data["correct_index"],
                explanation=q_data.get("explanation"),
                audio_url=q_data.get("audio_url")
            ))
        
        return session


class QuizService(LoggerMixin):
    """Quiz service - handles quiz business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.lang_repo = LanguageRepository(session)
        self.level_repo = LevelRepository(session)
        self.day_repo = DayRepository(session)
        self.question_repo = QuestionRepository(session)
        self.progress_repo = UserProgressRepository(session)
        self.sr_repo = SpacedRepetitionRepository(session)
    
    # ==================== LANGUAGE/LEVEL/DAY ====================
    
    async def get_languages(self) -> List[Language]:
        """Get all active languages"""
        return await self.lang_repo.get_active_languages()
    
    async def get_language_by_code(self, code: str) -> Optional[Language]:
        """Get language by code"""
        return await self.lang_repo.get_by_code(code)
    
    async def get_levels(self, language_id: int) -> List[Level]:
        """Get levels for language"""
        return await self.level_repo.get_by_language(language_id)
    
    async def get_days(self, level_id: int) -> List[Day]:
        """Get days for level"""
        return await self.day_repo.get_by_level(level_id)
    
    async def get_level_with_stats(self, level_id: int) -> Optional[Level]:
        """Get level with question counts"""
        return await self.level_repo.get_with_stats(level_id)
    
    # ==================== QUIZ SESSION ====================
    
    async def create_quiz_session(
        self,
        user_id: int,
        chat_id: int,
        language_id: int,
        level_id: Optional[int] = None,
        day_id: Optional[int] = None,
        question_count: Optional[int] = None,
        quiz_type: str = "personal",
        time_per_question: int = 30,
        is_premium: bool = False
    ) -> QuizSession:
        """Create new quiz session"""
        
        # Get questions
        if day_id:
            questions = await self.question_repo.get_questions_by_day(
                day_id,
                limit=question_count,
                include_premium=is_premium
            )
        elif level_id:
            questions = await self.question_repo.get_questions_by_level(
                level_id,
                limit=question_count,
                include_premium=is_premium
            )
        else:
            questions = await self.question_repo.get_random_questions(
                language_id,
                count=question_count or 10,
                include_premium=is_premium
            )
        
        if not questions:
            raise NoQuestionsError("Bu bo'limda savollar mavjud emas")
        
        # Create session
        session = QuizSession(
            user_id=user_id,
            chat_id=chat_id,
            language_id=language_id,
            level_id=level_id,
            day_id=day_id,
            quiz_type=quiz_type,
            time_per_question=time_per_question,
            started_at=datetime.utcnow()
        )
        
        # Prepare questions
        for i, q in enumerate(questions):
            session.questions.append(QuizQuestion.from_model(q, i))
        
        self.logger.info(
            "Quiz session created",
            user_id=user_id,
            questions_count=len(session.questions)
        )
        
        return session
    
    async def process_answer(
        self,
        session: QuizSession,
        selected_option: int,
        time_taken: float
    ) -> dict:
        """Process user's answer"""
        question = session.current_question
        if not question:
            return {"error": "No current question"}
        
        is_correct = selected_option == question.correct_index
        
        # Record answer
        session.record_answer(question.question_id, is_correct, time_taken)
        
        # Update question statistics
        await self.question_repo.record_answer(question.question_id, is_correct)
        
        # Update spaced repetition
        quality = 4 if is_correct else 1
        await self.sr_repo.update_after_review(
            session.user_id,
            question.question_id,
            quality
        )
        
        return {
            "is_correct": is_correct,
            "correct_index": question.correct_index,
            "correct_text": question.options[question.correct_index],
            "explanation": question.explanation,
            "time_taken": time_taken
        }
    
    async def complete_quiz(self, session: QuizSession) -> dict:
        """Complete quiz and save results"""
        session.completed_at = datetime.utcnow()
        
        # Save progress
        progress = await self.progress_repo.save_progress(
            user_id=session.user_id,
            correct=session.correct_count,
            wrong=session.wrong_count,
            total=session.total_questions,
            score=session.score,
            avg_time=session.avg_time,
            total_time=session.total_time,
            language_id=session.language_id,
            level_id=session.level_id,
            day_id=session.day_id,
            quiz_type=session.quiz_type,
            chat_id=session.chat_id
        )
        
        self.logger.info(
            "Quiz completed",
            user_id=session.user_id,
            score=session.score,
            correct=session.correct_count,
            total=session.total_questions
        )
        
        return {
            "correct": session.correct_count,
            "wrong": session.wrong_count,
            "total": session.total_questions,
            "score": session.score,
            "avg_time": session.avg_time,
            "total_time": session.total_time,
            "progress_id": progress.id
        }
    
    # ==================== STATISTICS ====================
    
    async def get_user_progress(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[UserProgress]:
        """Get user's recent progress"""
        return await self.progress_repo.get_user_progress(user_id, limit)
    
    async def get_user_stats(self, user_id: int) -> dict:
        """Get user's overall stats"""
        return await self.progress_repo.get_user_stats(user_id)
    
    async def get_spaced_repetition_stats(self, user_id: int) -> dict:
        """Get SR stats for user"""
        return await self.sr_repo.get_stats(user_id)
    
    async def get_due_questions_count(self, user_id: int) -> int:
        """Get count of questions due for review"""
        return await self.sr_repo.count_due(user_id)
    
    # ==================== VOTING ====================
    
    async def vote_question(
        self,
        question_id: int,
        user_id: int,
        vote_type: str
    ) -> bool:
        """Vote on a question"""
        return await self.question_repo.add_vote(question_id, user_id, vote_type)
