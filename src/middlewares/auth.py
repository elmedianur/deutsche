"""
Middlewares - Request processing pipeline
"""
from typing import Any, Awaitable, Callable, Dict
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject, Update

from src.database import get_session
from src.repositories import UserRepository, SubscriptionRepository
from src.core.logging import get_logger, bind_user_context, bind_chat_context, clear_context
from src.core.security import rate_limiter
from src.core.exceptions import RateLimitException, UserBlockedError
from src.config import settings

logger = get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Log all incoming updates"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Extract user and chat info
        user = None
        chat = None
        
        if isinstance(event, Message):
            user = event.from_user
            chat = event.chat
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            chat = event.message.chat if event.message else None
        
        # Bind context for logging
        if user:
            bind_user_context(user.id, user.username)
        if chat:
            bind_chat_context(chat.id, chat.type)
        
        start_time = datetime.utcnow()
        
        try:
            result = await handler(event, data)
            
            # Log successful handling
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.debug(
                "Request handled",
                elapsed=elapsed,
                event_type=type(event).__name__
            )
            
            return result
            
        except Exception as e:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.error(
                "Request failed",
                elapsed=elapsed,
                error=str(e),
                event_type=type(event).__name__
            )
            raise
            
        finally:
            clear_context()


class AuthMiddleware(BaseMiddleware):
    """
    Authentication middleware.
    - Registers/updates users
    - Checks if user is blocked
    - Loads user data into context
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Get user from event
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if not user:
            return await handler(event, data)
        
        # Get or create user in database
        async with get_session() as session:
            user_repo = UserRepository(session)

            db_user, created = await user_repo.get_or_create(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code or "uz"
            )

            # Check if blocked
            if db_user.is_blocked:
                logger.warning("Blocked user attempt", user_id=user.id)
                raise UserBlockedError(user.id)

            # Relationship'larni yuklash (session yopilgandan keyin ham ishlashi uchun)
            # selectin lazy load ishlatilgan, lekin explicit yuklash xavfsizroq
            _ = db_user.streak  # streak ni yuklash
            _ = db_user.subscription  # subscription ni yuklash

            # Ob'ektni session'dan ajratish (detach)
            # Bu session yopilgandan keyin ham ob'ekt bilan ishlash imkonini beradi
            session.expunge(db_user)

            # Add to data context
            data["db_user"] = db_user
            data["is_premium"] = db_user.is_premium
            data["is_admin"] = settings.is_admin(user.id)

            if created:
                logger.info("New user registered", user_id=user.id)

        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Rate limiting middleware"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not settings.RATE_LIMIT_ENABLED:
            return await handler(event, data)
        
        # Get user ID
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if not user:
            return await handler(event, data)
        
        # Different limits for messages and callbacks
        if isinstance(event, Message):
            key = f"msg:{user.id}"
            limit = settings.RATE_LIMIT_MESSAGES_PER_MINUTE
        else:
            key = f"cb:{user.id}"
            limit = settings.RATE_LIMIT_COMMANDS_PER_MINUTE * 2  # More lenient for callbacks
        
        try:
            rate_limiter.check_rate_limit(key, limit, 60)
        except RateLimitException as e:
            logger.warning(
                "Rate limit exceeded",
                user_id=user.id,
                retry_after=e.retry_after
            )
            
            # Send rate limit message
            if isinstance(event, Message):
                await event.answer(
                    f"⏳ Iltimos, {e.retry_after} soniya kutib turing."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    f"⏳ Juda tez! {e.retry_after}s kutib turing.",
                    show_alert=True
                )
            
            return None
        
        return await handler(event, data)


class SubscriptionMiddleware(BaseMiddleware):
    """
    Check subscription status and load subscription data.
    AuthMiddleware allaqachon db_user va subscription yuklagan bo'lsa,
    qayta database query qilmaslik.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Get user from event
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        # AuthMiddleware dan kelgan db_user ni tekshirish
        db_user = data.get("db_user")
        if db_user and db_user.subscription:
            # Subscription allaqachon yuklangan - qayta query qilmaslik
            data["subscription"] = db_user.subscription
            data["is_premium"] = db_user.subscription.is_active
            return await handler(event, data)

        # Agar db_user yo'q bo'lsa yoki subscription yuklanmagan bo'lsa
        async with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            subscription = await sub_repo.get_or_create(user.id)

            # Ob'ektni session'dan ajratish
            session.expunge(subscription)

            data["subscription"] = subscription
            data["is_premium"] = subscription.is_active

        return await handler(event, data)


class ChannelCheckMiddleware(BaseMiddleware):
    """
    Check if user is subscribed to required channels.
    Only applies to /start command in private chats.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Only check for messages in private chats
        if not isinstance(event, Message):
            return await handler(event, data)
        
        if event.chat.type != "private":
            return await handler(event, data)
        
        # Skip channel check for certain commands
        if event.text and event.text.startswith("/admin"):
            return await handler(event, data)
        
        user = event.from_user
        if not user:
            return await handler(event, data)
        
        # Load required channels
        from src.database.models import RequiredChannel
        from sqlalchemy import select
        
        async with get_session() as session:
            result = await session.execute(
                select(RequiredChannel).where(
                    RequiredChannel.is_active == True,
                    RequiredChannel.channel_type == "telegram"
                )
            )
            channels = result.scalars().all()
        
        if not channels:
            return await handler(event, data)
        
        # Check each channel
        not_subscribed = []
        
        for channel in channels:
            if not channel.chat_id:
                continue
            
            try:
                member = await self.bot.get_chat_member(
                    chat_id=channel.chat_id,
                    user_id=user.id
                )
                
                if member.status in ["left", "kicked"]:
                    not_subscribed.append(channel)
                    
            except Exception as e:
                logger.debug(f"Channel check failed: {e}")
                continue
        
        if not_subscribed:
            # Save to data for handler to use
            data["not_subscribed_channels"] = not_subscribed
        
        return await handler(event, data)
