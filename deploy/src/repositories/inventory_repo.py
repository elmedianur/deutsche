"""
Inventory Repository - User inventory management
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import UserInventory
from src.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[UserInventory]):
    """Repository for UserInventory model"""
    
    model = UserInventory
    
    async def add_item(
        self,
        user_id: int,
        item_id: str,
        item_type: str = "item",
        quantity: int = 1,
        stars_paid: int = 0,
        payment_id: str = None,
        duration_hours: int = None
    ) -> UserInventory:
        """Add item to user inventory"""
        
        # Check if user already has this item (stackable)
        existing = await self.session.execute(
            select(UserInventory).where(
                and_(
                    UserInventory.user_id == user_id,
                    UserInventory.item_id == item_id,
                    UserInventory.is_active == False
                )
            )
        )
        existing_item = existing.scalar_one_or_none()
        
        if existing_item and item_type == "item":
            # Stack quantity
            existing_item.quantity += quantity
            await self.session.flush()
            return existing_item
        
        # Create new inventory entry
        expires_at = None
        if duration_hours:
            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
        
        inventory = UserInventory(
            user_id=user_id,
            item_id=item_id,
            item_type=item_type,
            quantity=quantity,
            stars_paid=stars_paid,
            telegram_payment_id=payment_id,
            expires_at=expires_at
        )
        self.session.add(inventory)
        await self.session.commit()
        return inventory
    
    async def get_user_items(
        self,
        user_id: int,
        item_type: str = None,
        active_only: bool = False
    ) -> List[UserInventory]:
        """Get all items in user's inventory"""
        query = select(UserInventory).where(UserInventory.user_id == user_id)
        
        if item_type:
            query = query.where(UserInventory.item_type == item_type)
        
        if active_only:
            query = query.where(UserInventory.is_active == True)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_item_quantity(self, user_id: int, item_id: str) -> int:
        """Get quantity of specific item"""
        result = await self.session.execute(
            select(UserInventory).where(
                and_(
                    UserInventory.user_id == user_id,
                    UserInventory.item_id == item_id
                )
            )
        )
        items = result.scalars().all()
        return sum(item.quantity for item in items)
    
    async def use_item(self, user_id: int, item_id: str, quantity: int = 1) -> bool:
        """Use item from inventory"""
        result = await self.session.execute(
            select(UserInventory).where(
                and_(
                    UserInventory.user_id == user_id,
                    UserInventory.item_id == item_id,
                    UserInventory.quantity >= quantity
                )
            )
        )
        item = result.scalar_one_or_none()
        
        if not item:
            return False
        
        item.quantity -= quantity
        if item.quantity <= 0:
            await self.session.delete(item)
        
        await self.session.commit()
        return True
    
    async def activate_item(
        self,
        user_id: int,
        item_id: str,
        duration_hours: int = None
    ) -> Optional[UserInventory]:
        """Activate an item (e.g., XP boost)"""
        result = await self.session.execute(
            select(UserInventory).where(
                and_(
                    UserInventory.user_id == user_id,
                    UserInventory.item_id == item_id,
                    UserInventory.quantity > 0
                )
            )
        )
        item = result.scalar_one_or_none()
        
        if not item:
            return None
        
        item.quantity -= 1
        item.is_active = True
        item.activated_at = datetime.utcnow()
        
        if duration_hours:
            item.expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
        
        await self.session.commit()
        return item
