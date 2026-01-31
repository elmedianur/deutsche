"""Day Repository"""
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Day
from src.repositories.base import BaseRepository


class DayRepository(BaseRepository[Day]):
    """Day repository"""
    
    model = Day

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_level(self, level_id: int) -> List[Day]:
        """Get days by level"""
        result = await self.session.execute(
            select(Day).where(
                Day.level_id == level_id,
                Day.is_active == True
            ).order_by(Day.day_number)
        )
        return list(result.scalars().all())
