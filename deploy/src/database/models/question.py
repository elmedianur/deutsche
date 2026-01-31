"""
Question models - Question and votes
"""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, ForeignKey, Integer, BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin, ActiveMixin

if TYPE_CHECKING:
    from .language import Day


class Question(Base, TimestampMixin, ActiveMixin):
    """Question model"""
    
    __tablename__ = "questions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    day_id: Mapped[int] = mapped_column(
        ForeignKey("days.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Question content
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Options
    option_a: Mapped[str] = mapped_column(String(500), nullable=False)
    option_b: Mapped[str] = mapped_column(String(500), nullable=False)
    option_c: Mapped[str] = mapped_column(String(500), nullable=False)
    option_d: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Correct answer (A, B, C, or D)
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    
    # Explanation shown after answer
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Audio pronunciation file path/URL
    audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Image URL (if question has image)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Difficulty (1-5)
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    
    # Premium only question
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Statistics
    times_shown: Mapped[int] = mapped_column(Integer, default=0)
    times_correct: Mapped[int] = mapped_column(Integer, default=0)
    
    # Votes
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    downvotes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    day: Mapped["Day"] = relationship(
        "Day",
        back_populates="questions",
        lazy="joined"
    )
    votes: Mapped[list["QuestionVote"]] = relationship(
        "QuestionVote",
        back_populates="question",
        lazy="selectin"
    )
    
    @property
    def correct_text(self) -> str:
        """Get correct option text"""
        options = {
            'A': self.option_a,
            'B': self.option_b,
            'C': self.option_c,
            'D': self.option_d
        }
        return options.get(self.correct_option.upper(), "")
    
    @property
    def options_list(self) -> list[str]:
        """Get options as list"""
        return [self.option_a, self.option_b, self.option_c, self.option_d]
    
    @property
    def correct_index(self) -> int:
        """Get correct option index (0-3)"""
        return ord(self.correct_option.upper()) - ord('A')
    
    @property
    def accuracy_rate(self) -> float:
        """Calculate accuracy rate"""
        if self.times_shown == 0:
            return 0.0
        return (self.times_correct / self.times_shown) * 100
    
    @property
    def vote_score(self) -> int:
        """Net vote score"""
        return self.upvotes - self.downvotes
    
    def record_answer(self, is_correct: bool) -> None:
        """Record an answer attempt"""
        self.times_shown += 1
        if is_correct:
            self.times_correct += 1
    
    def get_shuffled_options(self) -> tuple[list[str], int]:
        """
        Get shuffled options and correct index.
        Returns (shuffled_options, new_correct_index)
        """
        import random
        
        options_data = [
            ('A', self.option_a),
            ('B', self.option_b),
            ('C', self.option_c),
            ('D', self.option_d)
        ]
        random.shuffle(options_data)
        
        options = [opt[1] for opt in options_data]
        correct_index = next(
            i for i, opt in enumerate(options_data)
            if opt[0] == self.correct_option.upper()
        )
        
        return options, correct_index


class QuestionVote(Base, TimestampMixin):
    """Question vote model - like/dislike"""
    
    __tablename__ = "question_votes"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    # Vote type: 'up' or 'down'
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # Relationships
    question: Mapped["Question"] = relationship(
        "Question",
        back_populates="votes"
    )
    
    __table_args__ = (
        UniqueConstraint('question_id', 'user_id', name='uq_question_user_vote'),
    )
    
    @property
    def is_upvote(self) -> bool:
        return self.vote_type == 'up'
    
    @property
    def is_downvote(self) -> bool:
        return self.vote_type == 'down'
