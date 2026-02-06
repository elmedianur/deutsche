"""XP va Level boshqaruv tizimi"""
from typing import Tuple
from src.database.session import get_session
from src.repositories import UserRepository
from src.core.logging import get_logger

logger = get_logger(__name__)


# Level thresholds - har bir level uchun kerak XP
LEVEL_THRESHOLDS = [
    0,      # Level 1: 0 XP
    100,    # Level 2: 100 XP
    250,    # Level 3: 250 XP
    500,    # Level 4: 500 XP
    1000,   # Level 5: 1000 XP
    1750,   # Level 6: 1750 XP
    2750,   # Level 7: 2750 XP
    4000,   # Level 8: 4000 XP
    5500,   # Level 9: 5500 XP
    7500,   # Level 10: 7500 XP
    10000,  # Level 11: 10000 XP
    13000,  # Level 12: 13000 XP
    17000,  # Level 13: 17000 XP
    22000,  # Level 14: 22000 XP
    28000,  # Level 15: 28000 XP
    35000,  # Level 16: 35000 XP
    45000,  # Level 17: 45000 XP
    60000,  # Level 18: 60000 XP
    80000,  # Level 19: 80000 XP
    100000, # Level 20: 100000 XP
]

# XP rewards
XP_REWARDS = {
    "flashcard_correct": 5,      # To'g'ri javob
    "flashcard_easy": 3,         # Oson javob (quality 5)
    "flashcard_hard": 8,         # Qiyin javob (quality 3+)
    "flashcard_again": 1,        # Takror (quality 0-2)
    "quiz_correct": 10,          # Quiz to'g'ri javob
    "quiz_wrong": 2,             # Quiz noto'g'ri javob
    "daily_streak": 25,          # Kunlik streak bonus
    "first_review": 15,          # Birinchi review
    "deck_complete": 50,         # Deck tugallash
    "level_up_bonus": 100,       # Level up bonus
}

# Level nomlari
LEVEL_NAMES = {
    1: "Boshlang'ich",
    2: "Shogird",
    3: "O'quvchi",
    4: "Talaba",
    5: "Ilg'or",
    6: "Ustoz",
    7: "Ekspert",
    8: "Master",
    9: "Grandmaster",
    10: "Legenda",
    11: "Afsonaviy",
    12: "Epik",
    13: "Etalon",
    14: "Virtuoz",
    15: "Dahiy",
    16: "Fenomen",
    17: "Titan",
    18: "Imperator",
    19: "Xudo",
    20: "Absolut",
}


def calculate_level(xp: int) -> int:
    """XP ga qarab levelni hisoblash"""
    for i in range(len(LEVEL_THRESHOLDS) - 1, -1, -1):
        if xp >= LEVEL_THRESHOLDS[i]:
            return i + 1
    return 1


def get_level_progress(xp: int, level: int) -> Tuple[int, int, float]:
    """
    Level progress hisoblash
    Returns: (current_xp_in_level, xp_needed_for_next, progress_percent)
    """
    if level >= len(LEVEL_THRESHOLDS):
        return xp, 0, 100.0
    
    current_threshold = LEVEL_THRESHOLDS[level - 1]
    next_threshold = LEVEL_THRESHOLDS[level] if level < len(LEVEL_THRESHOLDS) else LEVEL_THRESHOLDS[-1]
    
    xp_in_level = xp - current_threshold
    xp_needed = next_threshold - current_threshold
    progress = (xp_in_level / xp_needed * 100) if xp_needed > 0 else 100.0
    
    return xp_in_level, xp_needed, min(progress, 100.0)


def get_level_name(level: int) -> str:
    """Level nomini olish"""
    return LEVEL_NAMES.get(level, f"Level {level}")


def get_progress_bar(percent: float, length: int = 10) -> str:
    """Progress bar yasash"""
    filled = int(percent / 100 * length)
    empty = length - filled
    return "█" * filled + "░" * empty


class XPService:
    """XP va Level boshqarish"""
    
    @staticmethod
    async def add_xp(user_id: int, amount: int, reason: str = "") -> Tuple[int, int, bool]:
        """
        XP qo'shish
        Returns: (new_xp, new_level, level_up)
        """
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_user_id(user_id)
            
            if not user:
                logger.warning(f"User {user_id} not found for XP")
                return 0, 1, False
            
            old_level = user.level
            user.xp += amount
            new_level = calculate_level(user.xp)
            
            level_up = new_level > old_level
            if level_up:
                user.level = new_level
                # Level up bonus
                user.xp += XP_REWARDS["level_up_bonus"]
                logger.info(f"User {user_id} leveled up: {old_level} -> {new_level}")
            
            await session.flush()

            return user.xp, user.level, level_up
    
    @staticmethod
    async def get_user_stats(user_id: int) -> dict:
        """User XP statistikasi"""
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_user_id(user_id)
            
            if not user:
                return {
                    "xp": 0, "level": 1, "level_name": "Boshlang'ich",
                    "progress": 0, "xp_in_level": 0, "xp_needed": 100
                }
            
            xp_in_level, xp_needed, progress = get_level_progress(user.xp, user.level)
            
            return {
                "xp": user.xp,
                "level": user.level,
                "level_name": get_level_name(user.level),
                "progress": progress,
                "xp_in_level": xp_in_level,
                "xp_needed": xp_needed,
                "progress_bar": get_progress_bar(progress),
            }
    
    @staticmethod
    async def reward_flashcard_answer(user_id: int, quality: int) -> Tuple[int, bool]:
        """
        Flashcard javobiga XP berish
        Returns: (xp_earned, level_up)
        """
        if quality >= 4:  # Easy
            xp = XP_REWARDS["flashcard_easy"]
        elif quality >= 3:  # Hard but correct
            xp = XP_REWARDS["flashcard_hard"]
        else:  # Again
            xp = XP_REWARDS["flashcard_again"]
        
        new_xp, new_level, level_up = await XPService.add_xp(user_id, xp, f"flashcard_q{quality}")
        return xp, level_up
    
    @staticmethod
    async def reward_quiz_answer(user_id: int, is_correct: bool) -> Tuple[int, bool]:
        """Quiz javobiga XP berish"""
        xp = XP_REWARDS["quiz_correct"] if is_correct else XP_REWARDS["quiz_wrong"]
        new_xp, new_level, level_up = await XPService.add_xp(user_id, xp, "quiz")
        return xp, level_up
