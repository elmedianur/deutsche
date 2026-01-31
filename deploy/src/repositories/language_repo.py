"""
Language repository - Language, Level, Day data access
"""
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.database.models import Language, Level, Day
from src.repositories.base import BaseRepository


class LanguageRepository(BaseRepository[Language]):
    """Repository for Language model"""
    
    model = Language
    
    async def get_by_code(self, code: str) -> Optional[Language]:
        """Get language by code"""
        result = await self.session.execute(
            select(Language).where(Language.code == code.lower())
        )
        return result.scalar_one_or_none()
    
    async def get_active_languages(self) -> List[Language]:
        """Get all active languages with levels loaded"""
        result = await self.session.execute(
            select(Language)
            .options(selectinload(Language.levels))
            .where(Language.is_active == True)
            .order_by(Language.display_order, Language.name)
        )
        return list(result.scalars().all())
    
    async def get_with_levels(self, language_id: int) -> Optional[Language]:
        """Get language with levels loaded"""
        result = await self.session.execute(
            select(Language)
            .options(selectinload(Language.levels))
            .where(Language.id == language_id)
        )
        return result.scalar_one_or_none()
    
    async def create_language(
        self,
        name: str,
        code: str,
        flag: str = "🌐",
        description: str = None
    ) -> Language:
        """Create new language"""
        return await self.create(
            name=name,
            code=code.lower(),
            flag=flag,
            description=description
        )


class LevelRepository(BaseRepository[Level]):
    """Repository for Level model"""
    
    model = Level
    
    async def get_by_language(
        self,
        language_id: int,
        active_only: bool = True
    ) -> List[Level]:
        """Get levels for language"""
        query = select(Level).where(Level.language_id == language_id)
        
        if active_only:
            query = query.where(Level.is_active == True)
        
        query = query.order_by(Level.display_order, Level.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_with_days(self, level_id: int) -> Optional[Level]:
        """Get level with days loaded"""
        result = await self.session.execute(
            select(Level)
            .options(selectinload(Level.days))
            .where(Level.id == level_id)
        )
        return result.scalar_one_or_none()
    
    async def create_level(
        self,
        language_id: int,
        name: str,
        description: str = None,
        display_order: int = 0
    ) -> Level:
        """Create new level"""
        return await self.create(
            language_id=language_id,
            name=name,
            description=description,
            display_order=display_order
        )
    
    async def get_by_language_and_name(
        self,
        language_id: int,
        name: str
    ) -> Optional[Level]:
        """Get level by language and name"""
        result = await self.session.execute(
            select(Level).where(
                and_(
                    Level.language_id == language_id,
                    Level.name == name
                )
            )
        )
        return result.scalar_one_or_none()


class DayRepository(BaseRepository[Day]):
    """Repository for Day model"""
    
    model = Day
    
    async def get_by_level(
        self,
        level_id: int,
        active_only: bool = True
    ) -> List[Day]:
        """Get days for level"""
        query = select(Day).where(Day.level_id == level_id)
        
        if active_only:
            query = query.where(Day.is_active == True)
        
        query = query.order_by(Day.day_number)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_number(
        self,
        level_id: int,
        day_number: int
    ) -> Optional[Day]:
        """Get day by level and number"""
        result = await self.session.execute(
            select(Day).where(
                and_(
                    Day.level_id == level_id,
                    Day.day_number == day_number
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def create_day(
        self,
        level_id: int,
        day_number: int,
        name: str = None,
        description: str = None,
        topic: str = None
    ) -> Day:
        """Create new day"""
        return await self.create(
            level_id=level_id,
            day_number=day_number,
            name=name,
            description=description,
            topic=topic
        )
    
    async def get_with_questions(self, day_id: int) -> Optional[Day]:
        """Get day with questions loaded"""
        from src.database.models import Question
        
        result = await self.session.execute(
            select(Day)
            .options(selectinload(Day.questions))
            .where(Day.id == day_id)
        )
        return result.scalar_one_or_none()
