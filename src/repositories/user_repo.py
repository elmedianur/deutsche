"""
User repository - User data access
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, func, desc

from src.database.models import User, UserStreak, Subscription, SubscriptionPlan
from src.repositories.base import BaseRepository
from src.core.security import generate_referral_code


class UserRepository(BaseRepository[User]):
    """Repository for User model"""
    
    model = User
    
    async def get_by_user_id(self, user_id: int) -> Optional[User]:
        """Get user by Telegram user_id"""
        result = await self.session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: str = "uz"
    ) -> tuple[User, bool]:
        """
        Get existing user or create new one.
        Returns (user, created) tuple.
        """
        user = await self.get_by_user_id(user_id)
        
        if user:
            # Update info if changed
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
                user.last_active_at = datetime.utcnow()
                await self.save(user)
            
            return user, False
        
        # Create new user
        user = await self.create(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            referral_code=generate_referral_code(user_id),
            last_active_at=datetime.utcnow()
        )
        
        # Create default streak
        streak = UserStreak(user_id=user_id)
        self.session.add(streak)
        
        # Create default subscription
        subscription = Subscription(
            user_id=user_id,
            plan=SubscriptionPlan.FREE
        )
        self.session.add(subscription)
        
        await self.session.flush()
        
        return user, True
    
    async def get_by_referral_code(self, code: str) -> Optional[User]:
        """Get user by referral code"""
        result = await self.session.execute(
            select(User).where(User.referral_code == code.upper())
        )
        return result.scalar_one_or_none()
    
    async def get_all_active(self, limit: int = 1000, offset: int = 0) -> List[User]:
        """Get all non-blocked users"""
        result = await self.session.execute(
            select(User)
            .where(User.is_blocked == False)
            .order_by(desc(User.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_premium_users(self) -> List[User]:
        """Get all premium users"""
        result = await self.session.execute(
            select(User).where(User.is_premium == True)
        )
        return list(result.scalars().all())
    
    async def get_top_users(self, limit: int = 10) -> List[User]:
        """Get top users by score"""
        result = await self.session.execute(
            select(User)
            .where(User.total_questions > 0)
            .order_by(desc(User.total_correct))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_user_rank(self, user_id: int) -> int:
        """Get user's rank by total correct answers"""
        user = await self.get_by_user_id(user_id)
        if not user:
            return 0
        
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(User.total_correct > user.total_correct)
        )
        return result.scalar() + 1
    
    async def update_stats(
        self,
        user_id: int,
        correct: int,
        total: int
    ) -> Optional[User]:
        """Update user quiz statistics"""
        user = await self.get_by_user_id(user_id)
        if not user:
            return None
        
        user.update_stats(correct, total)
        await self.save(user)
        return user
    
    async def block_user(self, user_id: int) -> bool:
        """Block user"""
        user = await self.get_by_user_id(user_id)
        if not user:
            return False
        
        user.is_blocked = True
        await self.save(user)
        return True
    
    async def unblock_user(self, user_id: int) -> bool:
        """Unblock user"""
        user = await self.get_by_user_id(user_id)
        if not user:
            return False
        
        user.is_blocked = False
        await self.save(user)
        return True
    
    async def count_all(self) -> int:
        """Count all users"""
        return await self.count()
    
    async def count_active(self) -> int:
        """Count non-blocked users"""
        return await self.count({"is_blocked": False})
    
    async def count_premium(self) -> int:
        """Count premium users"""
        return await self.count({"is_premium": True})
    
    async def increment_referral_count(self, user_id: int) -> None:
        """Increment referral count for user"""
        user = await self.get_by_user_id(user_id)
        if user:
            user.referral_count += 1
            await self.save(user)


    async def count_today(self) -> int:
        """Count users registered today"""
        from datetime import datetime, timedelta
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= today)
        )
        return result.scalar() or 0
    
    async def count_week(self) -> int:
        """Count users registered this week"""
        from datetime import datetime, timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        result = await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        return result.scalar() or 0
    
    async def get_recent(self, limit: int = 15) -> List[User]:
        """Get recently registered users"""
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_users_for_reminder(self) -> List[User]:
        """Eslatma yuborish kerak bo'lgan userlarni olish

        Returns:
            List[User]: Eslatma yuborish kerak bo'lgan foydalanuvchilar ro'yxati
        """
        from datetime import datetime, timedelta
        from sqlalchemy import and_

        yesterday = datetime.utcnow() - timedelta(hours=24)
        two_days_ago = datetime.utcnow() - timedelta(hours=48)

        # Shartlar:
        # 1. daily_reminder_enabled = True
        # 2. Oxirgi quiz 24-48 soat oldin (streak yo'qolish xavfi)
        # 3. Bloklangan emas
        result = await self.session.execute(
            select(User).where(
                and_(
                    User.daily_reminder_enabled == True,
                    User.is_blocked == False,
                    User.last_quiz_at < yesterday,
                    User.last_quiz_at > two_days_ago
                )
            ).limit(100)  # Bir vaqtda 100 tagacha
        )
        return list(result.scalars().all())
