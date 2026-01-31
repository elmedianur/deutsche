"""
Base repository with common CRUD operations
Repository pattern for data access
"""
from typing import Any, Generic, List, Optional, Type, TypeVar
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import Base
from src.core.logging import LoggerMixin
from src.core.exceptions import EntityNotFoundError

# Generic type for models
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType], LoggerMixin):
    """
    Base repository with CRUD operations.
    
    Usage:
        class UserRepository(BaseRepository[User]):
            model = User
    """
    
    model: Type[ModelType]
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """Get single record by ID"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_id_or_raise(self, id: int) -> ModelType:
        """Get by ID or raise EntityNotFoundError"""
        entity = await self.get_by_id(id)
        if entity is None:
            raise EntityNotFoundError(self.model.__name__, id)
        return entity
    
    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: Any = None
    ) -> List[ModelType]:
        """Get all records with pagination"""
        query = select(self.model)
        
        if order_by is not None:
            query = query.order_by(order_by)
        
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_filter(
        self,
        filters: dict,
        limit: int = 100,
        offset: int = 0
    ) -> List[ModelType]:
        """Get records matching filters"""
        query = select(self.model)
        
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_one_by_filter(self, filters: dict) -> Optional[ModelType]:
        """Get single record matching filters"""
        results = await self.get_by_filter(filters, limit=1)
        return results[0] if results else None
    
    async def create(self, **data) -> ModelType:
        """Create new record"""
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
    
    async def update(self, id: int, **data) -> Optional[ModelType]:
        """Update record by ID"""
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
    
    async def delete(self, id: int) -> bool:
        """Delete record by ID"""
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        
        await self.session.delete(instance)
        await self.session.flush()
        return True
    
    async def count(self, filters: dict = None) -> int:
        """Count records matching filters"""
        query = select(func.count()).select_from(self.model)
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
        
        result = await self.session.execute(query)
        return result.scalar()
    
    async def save(self, instance: ModelType) -> ModelType:
        """Save instance"""
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
