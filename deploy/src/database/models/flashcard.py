"""
Flashcard system models
"""
from datetime import datetime, date, timedelta
from typing import Optional, TYPE_CHECKING
from enum import Enum
from sqlalchemy import String, Text, ForeignKey, Integer, BigInteger, DateTime, Boolean, Date, Float, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin, ActiveMixin

if TYPE_CHECKING:
    from .vocabulary import Vocabulary


class FlashcardDeck(Base, TimestampMixin, ActiveMixin):
    """Flashcard deck - collection of cards"""
    
    __tablename__ = "flashcard_decks"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Basic info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Language association
    language_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("languages.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    level_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("levels.id", ondelete="SET NULL"),
        nullable=True
    )
    # Link to Day/Topic - birlashtirilgan xarid uchun
    day_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("days.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Owner (None = system deck)
    owner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    
    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    price: Mapped[int] = mapped_column(Integer, default=0)  # Stars/Coins narxi
    
    # Stats
    cards_count: Mapped[int] = mapped_column(Integer, default=0)
    users_studying: Mapped[int] = mapped_column(Integer, default=0)
    
    # Display
    icon: Mapped[str] = mapped_column(String(10), default="📚")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    cards: Mapped[list["Flashcard"]] = relationship(
        "Flashcard",
        back_populates="deck",
        lazy="selectin"
    )


class Flashcard(Base, TimestampMixin, ActiveMixin):
    """Individual flashcard"""
    
    __tablename__ = "flashcards"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("flashcard_decks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Reference to unified vocabulary (optional - for migration)
    vocabulary_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Front side (question/word)
    front_text: Mapped[str] = mapped_column(Text, nullable=False)
    front_audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    front_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Back side (answer/translation)
    back_text: Mapped[str] = mapped_column(Text, nullable=False)
    back_audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    back_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Extra info
    example_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Tagging
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Comma separated
    
    # Stats
    times_shown: Mapped[int] = mapped_column(Integer, default=0)
    times_known: Mapped[int] = mapped_column(Integer, default=0)
    
    # Display order within deck
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    deck: Mapped["FlashcardDeck"] = relationship(
        "FlashcardDeck",
        back_populates="cards"
    )
    user_cards: Mapped[list["UserFlashcard"]] = relationship(
        "UserFlashcard",
        back_populates="card",
        lazy="selectin"
    )
    vocabulary: Mapped[Optional["Vocabulary"]] = relationship(
        "Vocabulary",
        foreign_keys=[vocabulary_id],
        lazy="selectin"
    )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.times_shown == 0:
            return 0.0
        return (self.times_known / self.times_shown) * 100
    
    @property
    def tags_list(self) -> list[str]:
        """Get tags as list"""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class UserFlashcard(Base, TimestampMixin):
    """
    User's progress on individual flashcard.
    Implements SM-2 spaced repetition.
    """

    __tablename__ = "user_flashcards"
    __table_args__ = (
        # Har bir user har bir kartani faqat 1 marta o'rganadi
        UniqueConstraint('user_id', 'card_id', name='uq_user_flashcard'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("flashcards.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # SM-2 parameters
    easiness_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval: Mapped[int] = mapped_column(Integer, default=0)  # Days
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    
    # Scheduling
    next_review_date: Mapped[date] = mapped_column(Date, default=date.today)
    last_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Stats
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    correct_reviews: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    is_learning: Mapped[bool] = mapped_column(Boolean, default=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    card: Mapped["Flashcard"] = relationship(
        "Flashcard",
        back_populates="user_cards"
    )
    
    def review(self, knew_it: bool) -> dict:
        """
        Process a review.
        
        Args:
            knew_it: True if user knew the answer, False otherwise
        
        Returns:
            Dict with review result info
        """
        quality = 4 if knew_it else 1  # Simplified quality rating
        
        self.total_reviews += 1
        self.last_review_date = date.today()
        
        result = {
            "knew_it": knew_it,
            "old_interval": self.interval,
            "new_interval": 0,
            "next_review": None
        }
        
        if knew_it:
            self.correct_reviews += 1
            
            if self.repetitions == 0:
                self.interval = 1
            elif self.repetitions == 1:
                self.interval = 6
            else:
                self.interval = int(self.interval * self.easiness_factor)
            
            self.repetitions += 1
        else:
            # Reset on failure
            self.repetitions = 0
            self.interval = 1
        
        # Update easiness factor
        self.easiness_factor = max(
            1.3,
            self.easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        )
        
        # Set next review date
        self.next_review_date = date.today() + timedelta(days=self.interval)
        
        result["new_interval"] = self.interval
        result["next_review"] = self.next_review_date
        
        return result
    
    @property
    def is_due(self) -> bool:
        """Check if card is due for review"""
        return date.today() >= self.next_review_date and not self.is_suspended
    
    @property
    def days_until_due(self) -> int:
        """Days until next review"""
        return max(0, (self.next_review_date - date.today()).days)
    
    @property
    def mastery_level(self) -> str:
        """Get mastery level"""
        if self.repetitions == 0:
            return "Yangi"
        elif self.interval <= 3:
            return "O'rganilmoqda"
        elif self.interval <= 14:
            return "O'zlashtirilmoqda"
        elif self.interval <= 60:
            return "Yaxshi biladi"
        else:
            return "Puxta"
    
    @property
    def mastery_color(self) -> str:
        """Get mastery color for UI"""
        colors = {
            "Yangi": "🔴",
            "O'rganilmoqda": "🟠",
            "O'zlashtirilmoqda": "🟡",
            "Yaxshi biladi": "🟢",
            "Puxta": "🔵"
        }
        return colors.get(self.mastery_level, "⚪")


class UserDeckProgress(Base, TimestampMixin):
    """User's overall progress on a deck"""

    __tablename__ = "user_deck_progress"
    __table_args__ = (
        # Har bir user har bir deck uchun faqat 1 ta progress yozuvi
        UniqueConstraint('user_id', 'deck_id', name='uq_user_deck_progress'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("flashcard_decks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Progress stats
    cards_seen: Mapped[int] = mapped_column(Integer, default=0)
    cards_learning: Mapped[int] = mapped_column(Integer, default=0)
    cards_mastered: Mapped[int] = mapped_column(Integer, default=0)
    
    # Review stats
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    reviews_today: Mapped[int] = mapped_column(Integer, default=0)
    new_cards_today: Mapped[int] = mapped_column(Integer, default=0)
    last_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Settings
    daily_new_cards: Mapped[int] = mapped_column(Integer, default=10)
    daily_review_limit: Mapped[int] = mapped_column(Integer, default=50)

    # SR Tuning settings
    sr_initial_ef: Mapped[float] = mapped_column(Float, default=2.5)
    sr_min_ef: Mapped[float] = mapped_column(Float, default=1.3)
    sr_first_interval: Mapped[int] = mapped_column(Integer, default=1)
    sr_second_interval: Mapped[int] = mapped_column(Integer, default=6)
    sr_easy_bonus: Mapped[float] = mapped_column(Float, default=1.3)
    
    @property
    def completion_percent(self) -> float:
        """Calculate deck completion percentage"""
        total = self.cards_seen + self.cards_learning + self.cards_mastered
        if total == 0:
            return 0.0
        return (self.cards_mastered / total) * 100


class UserDeckPurchase(Base, TimestampMixin):
    """
    Foydalanuvchi sotib olgan decklar
    """
    __tablename__ = "user_deck_purchases"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("flashcard_decks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # To'lov ma'lumotlari
    price_paid: Mapped[int] = mapped_column(Integer, default=0)  # Stars
    payment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Holat
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    deck: Mapped["FlashcardDeck"] = relationship("FlashcardDeck")
    
    __table_args__ = (
        # Har bir user har bir deckni faqat 1 marta sotib oladi
        UniqueConstraint('user_id', 'deck_id', name='uq_user_deck_purchase'),
        {"sqlite_autoincrement": True},
    )
