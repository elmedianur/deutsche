"""
Achievement/Badge system models
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from enum import Enum
from sqlalchemy import String, Text, ForeignKey, Integer, BigInteger, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class AchievementCategory(str, Enum):
    """Achievement categories"""
    QUIZ = "quiz"           # Quiz related
    STREAK = "streak"       # Streak related
    SOCIAL = "social"       # Referral, sharing
    SPECIAL = "special"     # Special events
    MILESTONE = "milestone" # Milestones


class AchievementRarity(str, Enum):
    """Achievement rarity"""
    COMMON = "common"       # 🥉
    RARE = "rare"           # 🥈
    EPIC = "epic"           # 🥇
    LEGENDARY = "legendary" # 💎


class Achievement(Base, TimestampMixin):
    """Achievement definition model"""
    
    __tablename__ = "achievements"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Basic info
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Visual
    icon: Mapped[str] = mapped_column(String(10), default="🏆")
    
    # Category and rarity
    category: Mapped[AchievementCategory] = mapped_column(
        SQLEnum(AchievementCategory),
        default=AchievementCategory.QUIZ
    )
    rarity: Mapped[AchievementRarity] = mapped_column(
        SQLEnum(AchievementRarity),
        default=AchievementRarity.COMMON
    )
    
    # Requirements
    requirement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    requirement_value: Mapped[int] = mapped_column(Integer, default=1)
    
    # Rewards
    reward_stars: Mapped[int] = mapped_column(Integer, default=0)
    reward_premium_days: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Display order
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    user_achievements: Mapped[list["UserAchievement"]] = relationship(
        "UserAchievement",
        back_populates="achievement",
        lazy="selectin"
    )
    
    @property
    def rarity_icon(self) -> str:
        """Get rarity icon"""
        icons = {
            AchievementRarity.COMMON: "🥉",
            AchievementRarity.RARE: "🥈",
            AchievementRarity.EPIC: "🥇",
            AchievementRarity.LEGENDARY: "💎"
        }
        return icons.get(self.rarity, "🏆")
    
    @property
    def full_display(self) -> str:
        """Full display string"""
        return f"{self.icon} {self.name} {self.rarity_icon}"


class UserAchievement(Base, TimestampMixin):
    """User's earned achievements"""
    
    __tablename__ = "user_achievements"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    achievement_id: Mapped[int] = mapped_column(
        ForeignKey("achievements.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # When earned
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Progress tracking (for progressive achievements)
    current_progress: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Notification
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="achievements",
        foreign_keys=[user_id],
        primaryjoin="User.user_id == UserAchievement.user_id"
    )
    achievement: Mapped["Achievement"] = relationship(
        "Achievement",
        back_populates="user_achievements",
        lazy="joined"
    )


# Predefined achievements
ACHIEVEMENT_DEFINITIONS = [
    # Quiz achievements
    {
        "code": "first_quiz",
        "name": "Birinchi qadam",
        "description": "Birinchi quizni tugatish",
        "icon": "🎯",
        "category": AchievementCategory.QUIZ,
        "rarity": AchievementRarity.COMMON,
        "requirement_type": "quizzes_completed",
        "requirement_value": 1,
    },
    {
        "code": "quiz_10",
        "name": "O'quvchi",
        "description": "10 ta quiz tugatish",
        "icon": "📚",
        "category": AchievementCategory.QUIZ,
        "rarity": AchievementRarity.COMMON,
        "requirement_type": "quizzes_completed",
        "requirement_value": 10,
    },
    {
        "code": "quiz_50",
        "name": "Bilimdon",
        "description": "50 ta quiz tugatish",
        "icon": "🎓",
        "category": AchievementCategory.QUIZ,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "quizzes_completed",
        "requirement_value": 50,
        "reward_stars": 50,
    },
    {
        "code": "quiz_100",
        "name": "Professor",
        "description": "100 ta quiz tugatish",
        "icon": "👨‍🏫",
        "category": AchievementCategory.QUIZ,
        "rarity": AchievementRarity.EPIC,
        "requirement_type": "quizzes_completed",
        "requirement_value": 100,
        "reward_premium_days": 3,
    },
    {
        "code": "perfect_quiz",
        "name": "Mukammal",
        "description": "Quizni 100% to'g'ri tugatish",
        "icon": "💯",
        "category": AchievementCategory.QUIZ,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "perfect_quiz",
        "requirement_value": 1,
    },
    {
        "code": "perfect_10",
        "name": "Aniq nishonchi",
        "description": "10 ta quizni 100% to'g'ri tugatish",
        "icon": "🎯",
        "category": AchievementCategory.QUIZ,
        "rarity": AchievementRarity.EPIC,
        "requirement_type": "perfect_quizzes",
        "requirement_value": 10,
        "reward_stars": 100,
    },
    
    # Streak achievements
    {
        "code": "streak_7",
        "name": "Bir hafta",
        "description": "7 kunlik streak",
        "icon": "🔥",
        "category": AchievementCategory.STREAK,
        "rarity": AchievementRarity.COMMON,
        "requirement_type": "streak_days",
        "requirement_value": 7,
        "reward_stars": 50,
    },
    {
        "code": "streak_30",
        "name": "Bir oy",
        "description": "30 kunlik streak",
        "icon": "🔥",
        "category": AchievementCategory.STREAK,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "streak_days",
        "requirement_value": 30,
        "reward_premium_days": 7,
    },
    {
        "code": "streak_100",
        "name": "Yuz kun!",
        "description": "100 kunlik streak",
        "icon": "💪",
        "category": AchievementCategory.STREAK,
        "rarity": AchievementRarity.EPIC,
        "requirement_type": "streak_days",
        "requirement_value": 100,
        "reward_premium_days": 30,
    },
    {
        "code": "streak_365",
        "name": "Bir yil!",
        "description": "365 kunlik streak",
        "icon": "👑",
        "category": AchievementCategory.STREAK,
        "rarity": AchievementRarity.LEGENDARY,
        "requirement_type": "streak_days",
        "requirement_value": 365,
        "reward_premium_days": 90,
    },
    
    # Social achievements
    {
        "code": "first_referral",
        "name": "Do'st topdi",
        "description": "Birinchi referal",
        "icon": "🤝",
        "category": AchievementCategory.SOCIAL,
        "rarity": AchievementRarity.COMMON,
        "requirement_type": "referrals",
        "requirement_value": 1,
        "reward_premium_days": 3,
    },
    {
        "code": "referral_10",
        "name": "Influencer",
        "description": "10 ta referal",
        "icon": "📢",
        "category": AchievementCategory.SOCIAL,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "referrals",
        "requirement_value": 10,
        "reward_premium_days": 14,
    },
    {
        "code": "referral_50",
        "name": "Ambassador",
        "description": "50 ta referal",
        "icon": "🌟",
        "category": AchievementCategory.SOCIAL,
        "rarity": AchievementRarity.LEGENDARY,
        "requirement_type": "referrals",
        "requirement_value": 50,
        "reward_premium_days": 60,
    },
    
    # Milestone achievements
    {
        "code": "questions_100",
        "name": "100 savol",
        "description": "100 ta savolga javob berish",
        "icon": "📝",
        "category": AchievementCategory.MILESTONE,
        "rarity": AchievementRarity.COMMON,
        "requirement_type": "questions_answered",
        "requirement_value": 100,
    },
    {
        "code": "questions_1000",
        "name": "Ming savol",
        "description": "1000 ta savolga javob berish",
        "icon": "🎖",
        "category": AchievementCategory.MILESTONE,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "questions_answered",
        "requirement_value": 1000,
        "reward_stars": 100,
    },
    {
        "code": "questions_10000",
        "name": "O'n ming savol",
        "description": "10,000 ta savolga javob berish",
        "icon": "🏆",
        "category": AchievementCategory.MILESTONE,
        "rarity": AchievementRarity.LEGENDARY,
        "requirement_type": "questions_answered",
        "requirement_value": 10000,
        "reward_premium_days": 30,
    },
    
    # Special achievements
    {
        "code": "early_bird",
        "name": "Erta qush",
        "description": "Ertalab 6:00 dan oldin quiz yechish",
        "icon": "🐦",
        "category": AchievementCategory.SPECIAL,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "early_quiz",
        "requirement_value": 1,
        "is_secret": True,
    },
    {
        "code": "night_owl",
        "name": "Tunda ishlaydi",
        "description": "Tunda 00:00 dan keyin quiz yechish",
        "icon": "🦉",
        "category": AchievementCategory.SPECIAL,
        "rarity": AchievementRarity.RARE,
        "requirement_type": "night_quiz",
        "requirement_value": 1,
        "is_secret": True,
    },
    {
        "code": "speed_demon",
        "name": "Tez javob",
        "description": "Barcha savollarga 5 soniyadan kam vaqtda javob berish",
        "icon": "⚡",
        "category": AchievementCategory.SPECIAL,
        "rarity": AchievementRarity.EPIC,
        "requirement_type": "speed_quiz",
        "requirement_value": 1,
        "is_secret": True,
    },
    {
        "code": "duel_winner",
        "name": "G'olib",
        "description": "Birinchi duelda g'alaba",
        "icon": "⚔️",
        "category": AchievementCategory.SPECIAL,
        "rarity": AchievementRarity.COMMON,
        "requirement_type": "duel_wins",
        "requirement_value": 1,
    },
    {
        "code": "duel_master",
        "name": "Duel ustasi",
        "description": "10 ta duelda g'alaba",
        "icon": "🗡",
        "category": AchievementCategory.SPECIAL,
        "rarity": AchievementRarity.EPIC,
        "requirement_type": "duel_wins",
        "requirement_value": 10,
        "reward_stars": 100,
    },
    {
        "code": "tournament_winner",
        "name": "Chempion",
        "description": "Turnirda birinchi o'rin",
        "icon": "🏆",
        "category": AchievementCategory.SPECIAL,
        "rarity": AchievementRarity.LEGENDARY,
        "requirement_type": "tournament_wins",
        "requirement_value": 1,
        "reward_premium_days": 7,
    },
]
