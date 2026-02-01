"""
Vocabulary model - unified word storage for Quiz and Flashcards
"""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin, ActiveMixin

if TYPE_CHECKING:
    from .language import Level, Day
    from .question import Question
    from .flashcard import Flashcard


class Vocabulary(Base, TimestampMixin, ActiveMixin):
    """
    Unified vocabulary table - one word, used in both Quiz and Flashcards.

    Bu jadval barcha so'zlarni saqlaydi:
    - Quiz savollar uchun question_text sifatida ishlatiladi
    - Flashcard uchun front_text/back_text sifatida ishlatiladi
    """

    __tablename__ = "vocabulary"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Word content
    word: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    translation: Mapped[str] = mapped_column(String(500), nullable=False)

    # Optional additional translations or meanings
    alt_translations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Part of speech (noun, verb, adjective, etc.)
    part_of_speech: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Gender for nouns (der, die, das for German)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Example sentence
    example_de: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example_uz: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Pronunciation
    pronunciation: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Image
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Level and Day references
    level_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("levels.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    day_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("days.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Difficulty (1-5)
    difficulty: Mapped[int] = mapped_column(Integer, default=3)

    # Frequency/importance (how common is this word)
    frequency: Mapped[int] = mapped_column(Integer, default=5)  # 1=rare, 10=very common

    # Tags for categorization
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Statistics
    times_shown: Mapped[int] = mapped_column(Integer, default=0)
    times_correct: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    level: Mapped[Optional["Level"]] = relationship(
        "Level",
        foreign_keys=[level_id],
        lazy="selectin"
    )
    day: Mapped[Optional["Day"]] = relationship(
        "Day",
        foreign_keys=[day_id],
        lazy="selectin"
    )

    @property
    def full_word(self) -> str:
        """Get word with gender if applicable (e.g., 'der Hund')"""
        if self.gender:
            return f"{self.gender} {self.word}"
        return self.word

    @property
    def accuracy(self) -> float:
        """Calculate accuracy percentage"""
        if self.times_shown == 0:
            return 0.0
        return (self.times_correct / self.times_shown) * 100

    def __repr__(self) -> str:
        return f"<Vocabulary(id={self.id}, word='{self.word}', translation='{self.translation}')>"
