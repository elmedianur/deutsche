"""
User repository - database operations for users
"""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import User, UserStreak, Subscription, SubscriptionPlan
from src.repositories.base import BaseRepository
from src.core.logging import get_logger

logger = get_logger(__name__)


class UserRepository(BaseRepository[User]):
    model = User
    """User repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_by_user_id(self, user_id: int) -> Optional[User]:
        """Get user by Telegram user_id"""
        query = (
            select(User)
            .where(User.user_id == user_id)
            .options(
                selectinload(User.subscription),
                selectinload(User.streak),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: str = "uz",
        referral_code: Optional[str] = None,
    ) -> tuple[User, bool]:
        """Get existing user or create new one"""
        user = await self.get_by_user_id(user_id)
        
        if user:
            # Update user info if changed
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updated = True
            
            if updated:
                await self.session.flush()
            
            return user, False
        
        # Create new user
        from src.core.security import generate_referral_code
        
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            referral_code=generate_referral_code(user_id),
            last_active_at=datetime.utcnow(),
        )
        self.session.add(user)
        await self.session.flush()
        
        # Create related entities
        subscription = Subscription(user_id=user_id, plan=SubscriptionPlan.FREE)
        streak = UserStreak(user_id=user_id)
        self.session.add(subscription)
        self.session.add(streak)
        await self.session.flush()
        
        # Refresh to get relationships
        await self.session.refresh(user)
        
        return user, True
    
    async def update_activity(self, user_id: int) -> None:
        """Update user's last activity timestamp"""
        await self.update_by_filter(
            {"user_id": user_id},
            last_active_at=datetime.utcnow()
        )
    
    async def update_stats(
        self,
        user_id: int,
        correct: int,
        total: int
    ) -> None:
        """Update user's quiz statistics"""
        user = await self.get_by_user_id(user_id)
        if user:
            user.total_quizzes += 1
            user.total_correct += correct
            user.total_questions += total
            user.last_quiz_at = datetime.utcnow()
            await self.session.flush()
    
    async def get_all_users(
        self,
        skip: int = 0,
        limit: int = 100,
        is_blocked: Optional[bool] = None,
        is_premium: Optional[bool] = None,
    ) -> List[User]:
        """Get users with optional filters"""
        query = select(User)
        
        conditions = []
        if is_blocked is not None:
            conditions.append(User.is_blocked == is_blocked)
        if is_premium is not None:
            conditions.append(User.is_premium == is_premium)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_active_users(self, days: int = 7) -> List[User]:
        """Get users active in the last N days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = (
            select(User)
            .where(
                and_(
                    User.last_active_at >= cutoff,
                    User.is_blocked == False
                )
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_premium_users(self) -> List[User]:
        """Get all premium users"""
        query = (
            select(User)
            .join(Subscription)
            .where(
                and_(
                    Subscription.plan != SubscriptionPlan.FREE,
                    or_(
                        Subscription.expires_at > datetime.utcnow(),
                        Subscription.plan == SubscriptionPlan.LIFETIME
                    )
                )
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_user_by_referral_code(self, code: str) -> Optional[User]:
        """Get user by referral code"""
        return await self.get_one(referral_code=code.upper())
    
    async def get_leaderboard(
        self,
        limit: int = 10,
        period_days: Optional[int] = None
    ) -> List[User]:
        """Get top users by score"""
        query = (
            select(User)
            .where(User.is_blocked == False)
            .order_by(User.total_correct.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_user_rank(self, user_id: int) -> int:
        """Get user's rank in leaderboard"""
        user = await self.get_by_user_id(user_id)
        if not user:
            return 0
        
        query = (
            select(func.count())
            .select_from(User)
            .where(
                and_(
                    User.total_correct > user.total_correct,
                    User.is_blocked == False
                )
            )
        )
        result = await self.session.execute(query)
        return (result.scalar() or 0) + 1
    
    async def search_users(
        self,
        search_term: str,
        limit: int = 20
    ) -> List[User]:
        """Search users by username or name"""
        search = f"%{search_term}%"
        query = (
            select(User)
            .where(
                or_(
                    User.username.ilike(search),
                    User.first_name.ilike(search),
                    User.last_name.ilike(search),
                )
            )
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count_users(
        self,
        is_blocked: Optional[bool] = None,
        is_premium: Optional[bool] = None,
        since: Optional[datetime] = None,
    ) -> int:
        """Count users with filters"""
        query = select(func.count()).select_from(User)
        
        conditions = []
        if is_blocked is not None:
            conditions.append(User.is_blocked == is_blocked)
        if is_premium is not None:
            conditions.append(User.is_premium == is_premium)
        if since:
            conditions.append(User.created_at >= since)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def block_user(self, user_id: int) -> bool:
        """Block a user"""
        return await self.update_by_filter(
            {"user_id": user_id},
            is_blocked=True
        ) > 0
    
    async def unblock_user(self, user_id: int) -> bool:
        """Unblock a user"""
        return await self.update_by_filter(
            {"user_id": user_id},
            is_blocked=False
        ) > 0
