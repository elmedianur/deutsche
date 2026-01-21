"""Level Repository"""
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Level
from src.repositories.base import BaseRepository


class LevelRepository(BaseRepository[Level]):
    """Level repository"""

    model = Level

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_language(self, language_id: int) -> List[Level]:
        """Get levels by language"""
        result = await self.session.execute(
            select(Level).where(
                Level.language_id == language_id,
                Level.is_active == True
            ).order_by(Level.display_order)
        )
        return list(result.scalars().all())

    async def get_all_active(self) -> List[Level]:
        """Get all active levels (without language filter)"""
        result = await self.session.execute(
            select(Level).where(
                Level.is_active == True
            ).order_by(Level.display_order)
        )
        return list(result.scalars().all())
