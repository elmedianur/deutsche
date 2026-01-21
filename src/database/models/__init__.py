"""
Database models package
All models exported here for easy importing
"""

# User
from .user import User

# Language hierarchy
from .language import Language, Level, Day

# Questions
from .question import Question, QuestionVote

# Progress and Streaks
from .progress import UserProgress, UserStreak, SpacedRepetition

# Subscription and Payments
from .subscription import (
    Subscription,
    Payment,
    PromoCode,
    PromoCodeUsage,
    SubscriptionPlan,
    PaymentStatus,
    PaymentMethod,
)

# Achievements
from .achievement import (
    Achievement,
    UserAchievement,
    AchievementCategory,
    AchievementRarity,
    ACHIEVEMENT_DEFINITIONS,
)

# Referrals
from .referral import (
    Referral,
    ReferralStats,
    ReferralStatus,
)

# Flashcards
from .flashcard import (
    FlashcardDeck,
    Flashcard,
    UserFlashcard,
    UserDeckPurchase,
    UserDeckProgress,
)

# Tournaments and Duels
from .tournament import (
    Tournament,
    TournamentParticipant,
    TournamentStatus,
    Duel,
    DuelStats,
    DuelStatus,
)

# System
from .system import (
    RequiredChannel,
    BotSettings,
    GroupQuizSettings,
    BroadcastMessage,
)

__all__ = [
    # User
    "User",
    
    # Language hierarchy
    "Language",
    "Level",
    "Day",
    
    # Questions
    "Question",
    "QuestionVote",
    
    # Progress
    "UserProgress",
    "UserStreak",
    "SpacedRepetition",
    
    # Subscription
    "Subscription",
    "Payment",
    "PromoCode",
    "PromoCodeUsage",
    "SubscriptionPlan",
    "PaymentStatus",
    "PaymentMethod",
    
    # Achievements
    "Achievement",
    "UserAchievement",
    "AchievementCategory",
    "AchievementRarity",
    "ACHIEVEMENT_DEFINITIONS",
    
    # Referrals
    "Referral",
    "ReferralStats",
    "ReferralStatus",
    
    # Flashcards
    "FlashcardDeck",
    "Flashcard",
    "UserFlashcard",
    "UserDeckPurchase",
    "UserDeckProgress",
    
    # Tournaments
    "Tournament",
    "TournamentParticipant",
    "TournamentStatus",
    "Duel",
    "DuelStats",
    "DuelStatus",
    
    # System
    "RequiredChannel",
    "BotSettings",
    "GroupQuizSettings",
    "BroadcastMessage",
]

from .subscription import UserInventory
