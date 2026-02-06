"""
Achievement service - Badge and achievement handling
"""
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.database import get_session
from src.database.models import (
    Achievement, UserAchievement, ACHIEVEMENT_DEFINITIONS,
    AchievementCategory, AchievementRarity
)
from src.repositories import UserRepository
from src.core.logging import get_logger, LoggerMixin
from sqlalchemy import select, and_

logger = get_logger(__name__)


class AchievementService(LoggerMixin):
    """Achievement and badge service"""
    
    async def initialize_achievements(self) -> int:
        """Initialize achievements from definitions"""
        from src.database.session import get_session
        
        async with get_session() as session:
            created = 0
            
            for definition in ACHIEVEMENT_DEFINITIONS:
                # Check if exists
                result = await session.execute(
                    select(Achievement).where(
                        Achievement.code == definition["code"]
                    )
                )
                existing = result.scalar_one_or_none()
                
                if not existing:
                    achievement = Achievement(
                        code=definition["code"],
                        name=definition["name"],
                        description=definition["description"],
                        icon=definition.get("icon", "🏆"),
                        category=definition.get("category", AchievementCategory.QUIZ),
                        rarity=definition.get("rarity", AchievementRarity.COMMON),
                        requirement_type=definition["requirement_type"],
                        requirement_value=definition["requirement_value"],
                        reward_stars=definition.get("reward_stars", 0),
                        reward_premium_days=definition.get("reward_premium_days", 0),
                        is_secret=definition.get("is_secret", False)
                    )
                    session.add(achievement)
                    created += 1
            
            await session.flush()
            
            self.logger.info(f"Initialized {created} achievements")
            return created
    
    async def check_and_award(
        self,
        user_id: int,
        event_type: str,
        event_value: int = 1
    ) -> List[Achievement]:
        """
        Check if user earned any achievements for an event.
        
        Args:
            user_id: User's Telegram ID
            event_type: Type of event (matches requirement_type)
            event_value: Current value/count for the event
        
        Returns:
            List of newly awarded achievements
        """
        awarded = []
        
        async with get_session() as session:
            # Get matching achievements
            result = await session.execute(
                select(Achievement).where(
                    and_(
                        Achievement.requirement_type == event_type,
                        Achievement.is_active == True
                    )
                )
            )
            achievements = result.scalars().all()
            
            for achievement in achievements:
                # Skip if value not met
                if event_value < achievement.requirement_value:
                    continue
                
                # Check if already earned
                existing = await session.execute(
                    select(UserAchievement).where(
                        and_(
                            UserAchievement.user_id == user_id,
                            UserAchievement.achievement_id == achievement.id,
                            UserAchievement.is_completed == True
                        )
                    )
                )
                
                if existing.scalar_one_or_none():
                    continue
                
                # Award achievement
                user_achievement = UserAchievement(
                    user_id=user_id,
                    achievement_id=achievement.id,
                    earned_at=datetime.utcnow(),
                    current_progress=event_value,
                    is_completed=True,
                    notified=False
                )
                session.add(user_achievement)
                
                awarded.append(achievement)
                
                self.logger.info(
                    "Achievement awarded",
                    user_id=user_id,
                    achievement=achievement.code
                )
            
            await session.flush()
        
        # Apply rewards for awarded achievements
        if awarded:
            await self._apply_rewards(user_id, awarded)
        
        return awarded
    
    async def _apply_rewards(
        self,
        user_id: int,
        achievements: List[Achievement]
    ) -> None:
        """Apply rewards for earned achievements"""
        from src.services.payment_service import payment_service
        
        total_days = sum(a.reward_premium_days for a in achievements)
        total_stars = sum(a.reward_stars for a in achievements)
        
        if total_days > 0:
            async with get_session() as session:
                from src.repositories import SubscriptionRepository
                sub_repo = SubscriptionRepository(session)
                await sub_repo.extend_subscription(user_id, total_days)
        
        # Stars would need to be added to user's balance if we track that
        # For now, just log it
        if total_stars > 0:
            self.logger.info(
                "Achievement stars reward",
                user_id=user_id,
                stars=total_stars
            )
    
    async def get_user_achievements(
        self,
        user_id: int,
        include_unearned: bool = False
    ) -> List[Dict[str, Any]]:
        """Get user's achievements"""
        async with get_session() as session:
            # Get all achievements
            all_result = await session.execute(
                select(Achievement).where(Achievement.is_active == True)
            )
            all_achievements = {a.id: a for a in all_result.scalars().all()}
            
            # Get user's earned achievements
            earned_result = await session.execute(
                select(UserAchievement).where(
                    and_(
                        UserAchievement.user_id == user_id,
                        UserAchievement.is_completed == True
                    )
                )
            )
            earned = {ua.achievement_id: ua for ua in earned_result.scalars().all()}
            
            result = []
            
            for achievement_id, achievement in all_achievements.items():
                # Skip secret achievements if not earned and not including unearned
                if achievement.is_secret and achievement_id not in earned:
                    if not include_unearned:
                        continue
                
                user_achievement = earned.get(achievement_id)
                
                result.append({
                    "id": achievement.id,
                    "code": achievement.code,
                    "name": achievement.name,
                    "description": achievement.description if not achievement.is_secret or user_achievement else "???",
                    "icon": achievement.icon,
                    "category": achievement.category.value,
                    "rarity": achievement.rarity.value,
                    "rarity_icon": achievement.rarity_icon,
                    "is_secret": achievement.is_secret,
                    "is_earned": user_achievement is not None,
                    "earned_at": user_achievement.earned_at if user_achievement else None,
                    "reward_stars": achievement.reward_stars,
                    "reward_premium_days": achievement.reward_premium_days
                })
            
            # Sort: earned first, then by rarity
            result.sort(
                key=lambda x: (
                    not x["is_earned"],
                    ["legendary", "epic", "rare", "common"].index(x["rarity"])
                )
            )
            
            return result
    
    async def get_unnotified_achievements(
        self,
        user_id: int
    ) -> List[Achievement]:
        """Get achievements that haven't been notified"""
        async with get_session() as session:
            result = await session.execute(
                select(UserAchievement)
                .where(
                    and_(
                        UserAchievement.user_id == user_id,
                        UserAchievement.notified == False,
                        UserAchievement.is_completed == True
                    )
                )
            )
            user_achievements = result.scalars().all()
            
            achievements = []
            for ua in user_achievements:
                ua.notified = True
                achievements.append(ua.achievement)
            
            await session.flush()
            
            return achievements
    
    async def get_achievement_stats(self, user_id: int) -> Dict[str, Any]:
        """Get achievement statistics for user"""
        async with get_session() as session:
            # Total achievements
            total_result = await session.execute(
                select(Achievement).where(Achievement.is_active == True)
            )
            total = len(list(total_result.scalars().all()))
            
            # Earned achievements
            earned_result = await session.execute(
                select(UserAchievement).where(
                    and_(
                        UserAchievement.user_id == user_id,
                        UserAchievement.is_completed == True
                    )
                )
            )
            earned = len(list(earned_result.scalars().all()))
            
            return {
                "total": total,
                "earned": earned,
                "percentage": (earned / total * 100) if total > 0 else 0
            }
    
    # Event handlers for common achievement triggers
    async def on_quiz_completed(
        self,
        user_id: int,
        total_quizzes: int,
        is_perfect: bool = False
    ) -> List[Achievement]:
        """Handle quiz completion event"""
        awarded = []
        
        # Check quiz count achievements
        awarded.extend(
            await self.check_and_award(user_id, "quizzes_completed", total_quizzes)
        )
        
        # Check perfect quiz
        if is_perfect:
            awarded.extend(
                await self.check_and_award(user_id, "perfect_quiz", 1)
            )
        
        return awarded
    
    async def on_streak_updated(
        self,
        user_id: int,
        current_streak: int
    ) -> List[Achievement]:
        """Handle streak update event"""
        return await self.check_and_award(user_id, "streak_days", current_streak)
    
    async def on_referral(
        self,
        user_id: int,
        total_referrals: int
    ) -> List[Achievement]:
        """Handle referral event"""
        return await self.check_and_award(user_id, "referrals", total_referrals)
    
    async def on_questions_answered(
        self,
        user_id: int,
        total_questions: int
    ) -> List[Achievement]:
        """Handle questions answered milestone"""
        return await self.check_and_award(user_id, "questions_answered", total_questions)
    
    async def on_duel_win(
        self,
        user_id: int,
        total_wins: int
    ) -> List[Achievement]:
        """Handle duel win"""
        return await self.check_and_award(user_id, "duel_wins", total_wins)
    
    async def on_tournament_win(
        self,
        user_id: int,
        total_wins: int = 1
    ) -> List[Achievement]:
        """Handle tournament win"""
        return await self.check_and_award(user_id, "tournament_wins", total_wins)


# Global service instance
achievement_service = AchievementService()
