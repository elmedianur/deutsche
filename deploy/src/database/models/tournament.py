"""
Tournament and Duel models
Competitive quiz features
"""
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
from enum import Enum
from sqlalchemy import String, Text, ForeignKey, Integer, BigInteger, DateTime, Boolean, Float, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin


class TournamentStatus(str, Enum):
    """Tournament status"""
    UPCOMING = "upcoming"       # Not started yet
    REGISTRATION = "registration"  # Registration open
    ACTIVE = "active"           # In progress
    COMPLETED = "completed"     # Finished
    CANCELLED = "cancelled"     # Cancelled


class DuelStatus(str, Enum):
    """Duel status"""
    PENDING = "pending"         # Waiting for opponent
    ACTIVE = "active"           # In progress
    COMPLETED = "completed"     # Finished
    EXPIRED = "expired"         # Timed out
    DECLINED = "declined"       # Opponent declined


class Tournament(Base, TimestampMixin):
    """Tournament model"""
    
    __tablename__ = "tournaments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Basic info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type
    tournament_type: Mapped[str] = mapped_column(String(50), default="weekly")  # weekly, monthly, special
    
    # Language/Level restriction
    language_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("languages.id", ondelete="SET NULL"),
        nullable=True
    )
    level_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("levels.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Timing
    registration_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    registration_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Status
    status: Mapped[TournamentStatus] = mapped_column(
        SQLEnum(TournamentStatus),
        default=TournamentStatus.UPCOMING
    )
    
    # Settings
    questions_count: Mapped[int] = mapped_column(Integer, default=20)
    time_per_question: Mapped[int] = mapped_column(Integer, default=15)
    max_participants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Entry requirements
    is_premium_only: Mapped[bool] = mapped_column(Boolean, default=False)
    min_level_required: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entry_fee_stars: Mapped[int] = mapped_column(Integer, default=0)
    
    # Prizes
    prize_1st_stars: Mapped[int] = mapped_column(Integer, default=500)
    prize_1st_premium_days: Mapped[int] = mapped_column(Integer, default=30)
    prize_2nd_stars: Mapped[int] = mapped_column(Integer, default=250)
    prize_2nd_premium_days: Mapped[int] = mapped_column(Integer, default=14)
    prize_3rd_stars: Mapped[int] = mapped_column(Integer, default=100)
    prize_3rd_premium_days: Mapped[int] = mapped_column(Integer, default=7)
    
    # Stats
    participants_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Winner
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Relationships
    participants: Mapped[list["TournamentParticipant"]] = relationship(
        "TournamentParticipant",
        back_populates="tournament",
        lazy="selectin"
    )
    
    @property
    def is_registration_open(self) -> bool:
        """Check if registration is open"""
        now = datetime.utcnow()
        return (
            self.status == TournamentStatus.REGISTRATION and
            self.registration_start <= now <= self.registration_end
        )
    
    @property
    def is_active(self) -> bool:
        """Check if tournament is active"""
        return self.status == TournamentStatus.ACTIVE
    
    @property
    def is_full(self) -> bool:
        """Check if tournament is full"""
        if self.max_participants is None:
            return False
        return self.participants_count >= self.max_participants
    
    def get_prize_info(self, place: int) -> dict:
        """Get prize info for a place"""
        prizes = {
            1: {"stars": self.prize_1st_stars, "premium_days": self.prize_1st_premium_days},
            2: {"stars": self.prize_2nd_stars, "premium_days": self.prize_2nd_premium_days},
            3: {"stars": self.prize_3rd_stars, "premium_days": self.prize_3rd_premium_days}
        }
        return prizes.get(place, {"stars": 0, "premium_days": 0})


class TournamentParticipant(Base, TimestampMixin):
    """Tournament participant model"""
    
    __tablename__ = "tournament_participants"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    # Registration
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    entry_fee_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Results
    score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    avg_time: Mapped[float] = mapped_column(Float, default=0.0)
    total_time: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Ranking
    final_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Completion
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_played_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Prize
    prize_received: Mapped[bool] = mapped_column(Boolean, default=False)
    prize_stars: Mapped[int] = mapped_column(Integer, default=0)
    prize_premium_days: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    tournament: Mapped["Tournament"] = relationship(
        "Tournament",
        back_populates="participants"
    )
    
    @property
    def accuracy(self) -> float:
        """Calculate accuracy percentage"""
        if self.total_questions == 0:
            return 0.0
        return (self.correct_answers / self.total_questions) * 100


class Duel(Base, TimestampMixin):
    """1v1 Duel model"""
    
    __tablename__ = "duels"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Participants
    challenger_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    opponent_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    
    # Status
    status: Mapped[DuelStatus] = mapped_column(
        SQLEnum(DuelStatus),
        default=DuelStatus.PENDING
    )
    
    # Language/Level
    language_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("languages.id", ondelete="SET NULL"),
        nullable=True
    )
    level_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("levels.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Settings
    questions_count: Mapped[int] = mapped_column(Integer, default=10)
    time_per_question: Mapped[int] = mapped_column(Integer, default=15)
    
    # Stake
    stake_stars: Mapped[int] = mapped_column(Integer, default=0)
    
    # Results - Challenger
    challenger_score: Mapped[float] = mapped_column(Float, default=0.0)
    challenger_correct: Mapped[int] = mapped_column(Integer, default=0)
    challenger_time: Mapped[float] = mapped_column(Float, default=0.0)
    challenger_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Results - Opponent
    opponent_score: Mapped[float] = mapped_column(Float, default=0.0)
    opponent_correct: Mapped[int] = mapped_column(Integer, default=0)
    opponent_time: Mapped[float] = mapped_column(Float, default=0.0)
    opponent_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Winner
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timing
    challenge_expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(hours=24)
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Questions (stored as JSON string of question IDs)
    question_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    @property
    def is_pending(self) -> bool:
        """Check if duel is waiting for opponent"""
        return self.status == DuelStatus.PENDING
    
    @property
    def is_active(self) -> bool:
        """Check if duel is active"""
        return self.status == DuelStatus.ACTIVE
    
    @property
    def is_expired(self) -> bool:
        """Check if duel challenge has expired"""
        if self.status != DuelStatus.PENDING:
            return False
        return datetime.utcnow() > self.challenge_expires_at
    
    def accept(self, opponent_id: int) -> None:
        """Accept duel challenge"""
        self.opponent_id = opponent_id
        self.status = DuelStatus.ACTIVE
        self.started_at = datetime.utcnow()
    
    def decline(self) -> None:
        """Decline duel challenge"""
        self.status = DuelStatus.DECLINED
    
    def expire(self) -> None:
        """Expire duel challenge"""
        self.status = DuelStatus.EXPIRED
    
    def complete(self) -> None:
        """Complete duel and determine winner"""
        self.status = DuelStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        
        # Determine winner
        if self.challenger_score > self.opponent_score:
            self.winner_id = self.challenger_id
        elif self.opponent_score > self.challenger_score:
            self.winner_id = self.opponent_id
        elif self.challenger_score == self.opponent_score:
            # Tie-breaker: faster time wins
            if self.challenger_time < self.opponent_time:
                self.winner_id = self.challenger_id
            elif self.opponent_time < self.challenger_time:
                self.winner_id = self.opponent_id
            else:
                self.is_draw = True
    
    def get_result_text(self, for_user_id: int) -> str:
        """Get result text for a specific user"""
        if self.is_draw:
            return "🤝 Durrang!"
        elif self.winner_id == for_user_id:
            return "🏆 Siz g'alaba qozondiniz!"
        else:
            return "😔 Siz yutqazdingiz"


class DuelStats(Base, TimestampMixin):
    """User's duel statistics"""
    
    __tablename__ = "duel_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    
    # Stats
    total_duels: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    
    # Win streaks
    current_win_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_win_streak: Mapped[int] = mapped_column(Integer, default=0)
    
    # Stars
    total_stars_won: Mapped[int] = mapped_column(Integer, default=0)
    total_stars_lost: Mapped[int] = mapped_column(Integer, default=0)
    
    # Rating (ELO-like)
    rating: Mapped[int] = mapped_column(Integer, default=1000)
    peak_rating: Mapped[int] = mapped_column(Integer, default=1000)
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate"""
        if self.total_duels == 0:
            return 0.0
        return (self.wins / self.total_duels) * 100
    
    @property
    def net_stars(self) -> int:
        """Net stars from duels"""
        return self.total_stars_won - self.total_stars_lost
    
    def record_win(self, stars_won: int = 0) -> None:
        """Record a win"""
        self.total_duels += 1
        self.wins += 1
        self.current_win_streak += 1
        self.total_stars_won += stars_won
        
        if self.current_win_streak > self.longest_win_streak:
            self.longest_win_streak = self.current_win_streak
        
        # Update rating
        self.rating = min(3000, self.rating + 25)
        if self.rating > self.peak_rating:
            self.peak_rating = self.rating
    
    def record_loss(self, stars_lost: int = 0) -> None:
        """Record a loss"""
        self.total_duels += 1
        self.losses += 1
        self.current_win_streak = 0
        self.total_stars_lost += stars_lost
        
        # Update rating
        self.rating = max(100, self.rating - 20)
    
    def record_draw(self) -> None:
        """Record a draw"""
        self.total_duels += 1
        self.draws += 1
        # Streak continues on draw
