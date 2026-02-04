"""
Async database session management
SQLAlchemy 2.0 async support
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Engine instance
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create async engine"""
    global _engine
    
    if _engine is None:
        # SQLite doesn't support pool settings
        if "sqlite" in settings.DATABASE_URL:
            _engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DATABASE_ECHO,
                poolclass=NullPool,  # SQLite requires NullPool
            )
        else:
            _engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DATABASE_ECHO,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections after 1 hour
            )
        logger.info("Database engine created", url=settings.DATABASE_URL.split('@')[-1])
    
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create async session factory"""
    global _async_session_factory
    
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    
    Usage:
        async with get_session() as session:
            result = await session.execute(query)
    """
    factory = get_session_factory()
    session = factory()
    
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error("Database session error", error=str(e))
        raise
    finally:
        await session.close()


async def init_database() -> None:
    """Initialize database - create tables"""
    from src.database.base import Base
    # Import all models to register them
    from src.database.models import (  # noqa: F401
        User, Language, Level, Day, Question,
        QuestionVote, UserProgress, UserStreak,
        Achievement, UserAchievement, Referral,
        Subscription, Payment, FlashcardDeck,
        Flashcard, UserFlashcard, Tournament,
        TournamentParticipant, RequiredChannel, BotSettings,
        UserTopicPurchase
    )
    
    engine = get_engine()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created")


async def close_database() -> None:
    """Close database connections"""
    global _engine, _async_session_factory
    
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connections closed")


# Dependency for FastAPI style injection
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides database session"""
    async with get_session() as session:
        yield session
