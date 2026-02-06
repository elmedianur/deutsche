"""
User service - business logic for user operations
"""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, UserStreak
from src.repositories import UserRepository
from src.repositories.subscription_repo import SubscriptionRepository
from src.core.logging import get_logger, LoggerMixin
from src.core.exceptions import UserBlockedError, EntityNotFoundError

logger = get_logger(__name__)


class UserService(LoggerMixin):
    """User service - handles user business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)
    
    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: str = "uz",
        referral_code: Optional[str] = None
    ) -> tuple[User, bool]:
        """Get existing user or create new one"""
        user, created = await self.user_repo.get_or_create_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            referral_code=referral_code
        )
        
        if created:
            self.logger.info("New user created", user_id=user_id, username=username)
            
            # Handle referral if code provided
            if referral_code:
                await self._process_referral(user, referral_code)
        
        return user, created
    
    async def _process_referral(self, user: User, referral_code: str) -> None:
        """Process referral for new user"""
        from src.database.models import Referral, ReferralStatus
        from src.config import settings
        from sqlalchemy import update

        # Find referrer
        referrer = await self.user_repo.get_user_by_referral_code(referral_code)
        if not referrer or referrer.user_id == user.user_id:
            return

        # Create referral record
        referral = Referral(
            referrer_id=referrer.user_id,
            referred_id=user.user_id,
            referral_code=referral_code,
            required_quizzes=settings.REFERRAL_MIN_QUIZZES
        )
        self.session.add(referral)

        # Update user's referred_by
        user.referred_by_id = referrer.user_id

        # Atomic SQL increment (race condition oldini olish)
        await self.session.execute(
            update(User)
            .where(User.user_id == referrer.user_id)
            .values(referral_count=User.referral_count + 1)
        )

        await self.session.flush()
        
        self.logger.info(
            "Referral created",
            referrer_id=referrer.user_id,
            referred_id=user.user_id
        )
    
    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by Telegram user_id"""
        return await self.user_repo.get_by_user_id(user_id)
    
    async def get_user_or_error(self, user_id: int) -> User:
        """Get user or raise error"""
        user = await self.get_user(user_id)
        if not user:
            raise EntityNotFoundError("User", user_id)
        return user
    
    async def check_user_access(self, user_id: int) -> tuple[bool, str]:
        """Check if user can access bot"""
        user = await self.get_user(user_id)
        
        if not user:
            return True, "new_user"
        
        if user.is_blocked:
            return False, "blocked"
        
        return True, "ok"
    
    async def update_user_activity(self, user_id: int) -> None:
        """Update user's last activity"""
        await self.user_repo.update_activity(user_id)
    
    async def update_user_stats(
        self,
        user_id: int,
        correct: int,
        total: int
    ) -> None:
        """Update user's quiz statistics"""
        await self.user_repo.update_stats(user_id, correct, total)
    
    async def is_premium(self, user_id: int) -> bool:
        """Check if user has premium subscription"""
        from src.config import settings
        # Super adminlar doim premium
        if settings.is_super_admin(user_id):
            return True
        return await self.sub_repo.is_premium(user_id)
    
    async def get_user_profile(self, user_id: int) -> dict:
        """Get comprehensive user profile"""
        user = await self.get_user_or_error(user_id)
        is_premium = await self.is_premium(user_id)
        
        # Get rank
        rank = await self.user_repo.get_user_rank(user_id)
        
        return {
            "user": user,
            "is_premium": is_premium,
            "rank": rank,
            "streak": user.streak.current_streak if user.streak else 0,
            "accuracy": user.accuracy,
            "stats": {
                "total_quizzes": user.total_quizzes,
                "total_correct": user.total_correct,
                "total_questions": user.total_questions
            }
        }
    
    async def get_leaderboard(
        self,
        limit: int = 10,
        user_id: Optional[int] = None
    ) -> dict:
        """Get leaderboard with optional user position"""
        leaders = await self.user_repo.get_leaderboard(limit)
        
        result = {
            "leaders": leaders,
            "user_rank": None,
            "user_in_top": False
        }
        
        if user_id:
            rank = await self.user_repo.get_user_rank(user_id)
            result["user_rank"] = rank
            result["user_in_top"] = any(u.user_id == user_id for u in leaders)
        
        return result
    
    async def block_user(self, user_id: int, admin_id: int) -> bool:
        """Block a user"""
        from src.core.logging import audit_logger
        
        success = await self.user_repo.block_user(user_id)
        
        if success:
            audit_logger.log_admin_action(
                admin_id=admin_id,
                action="block_user",
                target=str(user_id)
            )
        
        return success
    
    async def unblock_user(self, user_id: int, admin_id: int) -> bool:
        """Unblock a user"""
        from src.core.logging import audit_logger
        
        success = await self.user_repo.unblock_user(user_id)
        
        if success:
            audit_logger.log_admin_action(
                admin_id=admin_id,
                action="unblock_user",
                target=str(user_id)
            )
        
        return success


class StreakService(LoggerMixin):
    """Streak service - handles streak business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def update_streak(self, user_id: int) -> dict:
        """Update user's streak after activity"""
        from sqlalchemy import select
        
        query = select(UserStreak).where(UserStreak.user_id == user_id)
        result = await self.session.execute(query)
        streak = result.scalar_one_or_none()
        
        if not streak:
            streak = UserStreak(user_id=user_id)
            self.session.add(streak)
            await self.session.flush()
        
        result = streak.check_and_update()
        await self.session.flush()
        
        if result.get("streak_increased"):
            self.logger.info(
                "Streak increased",
                user_id=user_id,
                new_streak=result["new_streak"]
            )
        elif result.get("streak_lost"):
            self.logger.info(
                "Streak lost",
                user_id=user_id,
                previous_streak=result.get("previous_streak")
            )
        
        return result
    
    async def get_streak_info(self, user_id: int) -> dict:
        """Get streak information for user"""
        from sqlalchemy import select
        
        query = select(UserStreak).where(UserStreak.user_id == user_id)
        result = await self.session.execute(query)
        streak = result.scalar_one_or_none()
        
        if not streak:
            return {
                "current": 0,
                "longest": 0,
                "freeze_available": 0,
                "is_active_today": False,
                "days_until_milestone": 7,
                "next_milestone": 7
            }
        
        days_until, milestone = streak.days_until_milestone
        
        return {
            "current": streak.current_streak,
            "longest": streak.longest_streak,
            "freeze_available": streak.freeze_count,
            "is_active_today": streak.is_active_today,
            "days_until_milestone": days_until,
            "next_milestone": milestone,
            "total_bonus": streak.total_bonus_earned
        }
    
    async def add_freeze(self, user_id: int, count: int = 1) -> bool:
        """Add streak freeze to user"""
        from sqlalchemy import select
        
        query = select(UserStreak).where(UserStreak.user_id == user_id)
        result = await self.session.execute(query)
        streak = result.scalar_one_or_none()
        
        if streak:
            streak.freeze_count += count
            await self.session.flush()
            return True
        
        return False
