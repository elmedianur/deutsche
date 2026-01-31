"""
Achievement service - handles achievements/badges
"""
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Achievement, UserAchievement, AchievementCategory,
    ACHIEVEMENT_DEFINITIONS
)
from src.repositories.base import BaseRepository
from src.core.logging import get_logger, LoggerMixin

logger = get_logger(__name__)


class AchievementRepository(BaseRepository[Achievement]):
    """Achievement repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Achievement, session)
    
    async def get_all_achievements(self) -> List[Achievement]:
        """Get all active achievements"""
        query = (
            select(Achievement)
            .where(Achievement.is_active == True)
            .order_by(Achievement.display_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_code(self, code: str) -> Optional[Achievement]:
        """Get achievement by code"""
        return await self.get_one(code=code)
    
    async def get_user_achievements(self, user_id: int) -> List[UserAchievement]:
        """Get user's earned achievements"""
        query = (
            select(UserAchievement)
            .where(
                and_(
                    UserAchievement.user_id == user_id,
                    UserAchievement.is_completed == True
                )
            )
            .order_by(UserAchievement.earned_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def has_achievement(self, user_id: int, achievement_code: str) -> bool:
        """Check if user has specific achievement"""
        achievement = await self.get_by_code(achievement_code)
        if not achievement:
            return False
        
        query = select(UserAchievement).where(
            and_(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_id == achievement.id,
                UserAchievement.is_completed == True
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def award_achievement(
        self,
        user_id: int,
        achievement: Achievement
    ) -> UserAchievement:
        """Award achievement to user"""
        user_achievement = UserAchievement(
            user_id=user_id,
            achievement_id=achievement.id,
            earned_at=datetime.utcnow(),
            is_completed=True
        )
        self.session.add(user_achievement)
        await self.session.flush()
        return user_achievement


class AchievementService(LoggerMixin):
    """Achievement service - handles achievement logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AchievementRepository(session)
    
    async def initialize_achievements(self) -> int:
        """Initialize achievements from definitions"""
        count = 0
        
        for definition in ACHIEVEMENT_DEFINITIONS:
            existing = await self.repo.get_by_code(definition["code"])
            if not existing:
                achievement = Achievement(**definition)
                self.session.add(achievement)
                count += 1
        
        if count > 0:
            await self.session.flush()
            self.logger.info("Achievements initialized", count=count)
        
        return count
    
    async def get_all_achievements(self) -> List[Achievement]:
        """Get all achievements"""
        return await self.repo.get_all_achievements()
    
    async def get_user_achievements(self, user_id: int) -> List[UserAchievement]:
        """Get user's achievements"""
        return await self.repo.get_user_achievements(user_id)
    
    async def get_achievements_progress(self, user_id: int) -> Dict:
        """Get user's achievement progress"""
        all_achievements = await self.get_all_achievements()
        user_achievements = await self.get_user_achievements(user_id)
        
        earned_ids = {ua.achievement_id for ua in user_achievements}
        
        earned = []
        not_earned = []
        
        for achievement in all_achievements:
            if achievement.id in earned_ids:
                earned.append(achievement)
            elif not achievement.is_secret:
                not_earned.append(achievement)
        
        return {
            "earned": earned,
            "not_earned": not_earned,
            "total": len(all_achievements),
            "earned_count": len(earned),
            "progress_percent": (len(earned) / len(all_achievements) * 100) if all_achievements else 0
        }
    
    async def check_and_award(
        self,
        user_id: int,
        event_type: str,
        event_value: int = 1
    ) -> List[Achievement]:
        """
        Check and award achievements based on event.
        
        Args:
            user_id: User ID
            event_type: Type of event (quizzes_completed, streak_days, etc.)
            event_value: Value to check against
        
        Returns:
            List of newly awarded achievements
        """
        all_achievements = await self.get_all_achievements()
        awarded = []
        
        for achievement in all_achievements:
            if achievement.requirement_type != event_type:
                continue
            
            if event_value < achievement.requirement_value:
                continue
            
            # Check if already has
            if await self.repo.has_achievement(user_id, achievement.code):
                continue
            
            # Award!
            await self.repo.award_achievement(user_id, achievement)
            awarded.append(achievement)
            
            self.logger.info(
                "Achievement awarded",
                user_id=user_id,
                achievement=achievement.code
            )
        
        return awarded
    
    async def check_quiz_achievements(
        self,
        user_id: int,
        total_quizzes: int,
        is_perfect: bool = False,
        perfect_count: int = 0
    ) -> List[Achievement]:
        """Check quiz-related achievements"""
        awarded = []
        
        # Quizzes completed
        awarded.extend(await self.check_and_award(
            user_id, "quizzes_completed", total_quizzes
        ))
        
        # Perfect quiz
        if is_perfect:
            awarded.extend(await self.check_and_award(
                user_id, "perfect_quiz", 1
            ))
        
        # Perfect quizzes count
        if perfect_count > 0:
            awarded.extend(await self.check_and_award(
                user_id, "perfect_quizzes", perfect_count
            ))
        
        return awarded
    
    async def check_streak_achievements(
        self,
        user_id: int,
        streak_days: int
    ) -> List[Achievement]:
        """Check streak-related achievements"""
        return await self.check_and_award(
            user_id, "streak_days", streak_days
        )
    
    async def check_referral_achievements(
        self,
        user_id: int,
        referral_count: int
    ) -> List[Achievement]:
        """Check referral-related achievements"""
        return await self.check_and_award(
            user_id, "referrals", referral_count
        )
    
    async def check_questions_achievements(
        self,
        user_id: int,
        total_questions: int
    ) -> List[Achievement]:
        """Check questions answered achievements"""
        return await self.check_and_award(
            user_id, "questions_answered", total_questions
        )
    
    async def check_special_achievements(
        self,
        user_id: int,
        event_type: str
    ) -> List[Achievement]:
        """
        Check special achievements.
        
        Event types:
        - early_quiz: Quiz completed before 6 AM
        - night_quiz: Quiz completed after midnight
        - speed_quiz: All answers under 5 seconds
        """
        return await self.check_and_award(user_id, event_type, 1)
    
    async def check_duel_achievements(
        self,
        user_id: int,
        wins: int
    ) -> List[Achievement]:
        """Check duel-related achievements"""
        return await self.check_and_award(user_id, "duel_wins", wins)
    
    async def check_tournament_achievements(
        self,
        user_id: int,
        wins: int
    ) -> List[Achievement]:
        """Check tournament-related achievements"""
        return await self.check_and_award(user_id, "tournament_wins", wins)
    
    async def get_rewards_for_achievement(
        self,
        achievement: Achievement
    ) -> Dict:
        """Get rewards info for achievement"""
        return {
            "stars": achievement.reward_stars,
            "premium_days": achievement.reward_premium_days,
            "has_rewards": achievement.reward_stars > 0 or achievement.reward_premium_days > 0
        }
    
    async def apply_achievement_rewards(
        self,
        user_id: int,
        achievement: Achievement
    ) -> Dict:
        """Apply rewards from achievement"""
        rewards = await self.get_rewards_for_achievement(achievement)
        
        if rewards["premium_days"] > 0:
            from src.repositories.payment import SubscriptionRepository
            sub_repo = SubscriptionRepository(self.session)
            await sub_repo.extend_subscription(user_id, rewards["premium_days"])
        
        return rewards
