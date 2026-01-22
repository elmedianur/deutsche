"""
Quiz Bot Pro - Main entry point
Professional Telegram Quiz Bot with Premium features
"""
import asyncio
import sys
from typing import Optional
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from src.config import settings
from src.core.logging import setup_logging, get_logger
from src.core.redis import get_redis, close_redis
from src.database import init_database, close_database
from src.middlewares.auth import (
    LoggingMiddleware,
    AuthMiddleware,
    RateLimitMiddleware,
    SubscriptionMiddleware,
)
from src.services import payment_service, achievement_service
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Setup logging first
setup_logging()
logger = get_logger(__name__)


def create_bot() -> Bot:
    """Create bot instance"""
    return Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )


async def create_dispatcher() -> Dispatcher:
    """Create dispatcher with storage and middlewares"""
    from aiogram.fsm.storage.memory import MemoryStorage
    
    # Try Redis storage, fallback to memory
    try:
        redis = await get_redis()
        # Check if it's real Redis or fallback
        if hasattr(redis, 'ping'):
            await redis.ping()
            storage = RedisStorage(redis)
            logger.info("Using Redis storage for FSM")
        else:
            storage = MemoryStorage()
            logger.info("Using Memory storage for FSM (Redis unavailable)")
    except Exception as e:
        logger.warning(f"Redis unavailable, using MemoryStorage: {e}")
        storage = MemoryStorage()
    
    dp = Dispatcher(storage=storage)
    
    # Register middlewares (order matters!)
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    return dp


def register_handlers(dp: Dispatcher, bot: Bot) -> None:
    """Register all handlers"""
    from src.handlers.user.start import router as start_router
    from src.handlers.user.menu import router as menu_router
    from src.handlers.quiz.personal import router as quiz_router
    from src.handlers.payment.stars import router as payment_router
    from src.handlers.admin.panel import router as admin_router
    from src.handlers.duel import router as duel_router
    from src.handlers.flashcard import router as flashcard_router
    from src.handlers.tournament import router as tournament_router
    from src.handlers.shop import router as shop_router
    from src.handlers.learning import router as learning_router

    # Include routers
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(learning_router)  # So'z o'rganish
    dp.include_router(quiz_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)
    dp.include_router(duel_router)
    dp.include_router(flashcard_router)
    dp.include_router(tournament_router)
    dp.include_router(shop_router)

    logger.info("Handlers registered")




# ============================================================
# SCHEDULER TASKS
# ============================================================

scheduler: Optional[AsyncIOScheduler] = None

async def check_tournament_end():
    """Turnir tugashini tekshirish va yangi boshlash"""
    from src.services import tournament_service
    from src.core.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        # Tugagan turnirni yakunlash
        result = await tournament_service.finish_expired_tournaments()
        if result:
            logger.info(f"Tournament finished: {result}")
        
        # Yangi turnir yaratish (agar yo'q bo'lsa)
        tournament = await tournament_service.get_or_create_weekly_tournament()
        if tournament:
            logger.info(f"Active tournament: {tournament.name}")
    except Exception as e:
        logger.error(f"Tournament scheduler error: {e}")


async def send_daily_reminders(bot: Bot):
    """Kunlik eslatmalar yuborish"""
    from src.database import get_session
    from src.repositories import UserRepository
    from src.core.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        async with get_session() as session:
            user_repo = UserRepository(session)
            users = await user_repo.get_users_for_reminder()
            
            sent = 0
            failed = 0
            for user in users:
                try:
                    await bot.send_message(
                        user.user_id,
                        "🔥 <b>Kunlik eslatma!</b>\n\n"
                        "Bugun hali quiz o'ynamadingiz. "
                        "Streak'ingizni yo'qotmang!\n\n"
                        "📚 /start - Quiz boshlash",
                        parse_mode="HTML"
                    )
                    sent += 1
                except Exception as e:
                    failed += 1
                    # Faqat kutilmagan xatolarni log qilish (blocked bot emas)
                    if "blocked" not in str(e).lower() and "deactivated" not in str(e).lower():
                        logger.debug(f"Reminder failed for user {user.user_id}: {e}")

            logger.info(f"Daily reminders: sent={sent}, failed={failed}")
    except Exception as e:
        logger.error(f"Reminder error: {e}")


async def send_flashcard_reminders(bot: Bot):
    """Flashcard takrorlash eslatmalari"""
    from src.database import get_session
    from src.repositories import UserRepository, UserFlashcardRepository
    from src.core.logging import get_logger
    logger = get_logger(__name__)

    try:
        async with get_session() as session:
            user_repo = UserRepository(session)
            user_fc_repo = UserFlashcardRepository(session)

            # Notification yoqilgan userlar
            users = await user_repo.get_users_for_reminder()

            sent = 0
            failed = 0
            for user in users:
                try:
                    # Due cards sonini tekshirish
                    due_cards = await user_fc_repo.get_due_cards(user.user_id, limit=1)
                    if due_cards:
                        due_count_result = await user_fc_repo.get_user_card_stats(user.user_id)
                        due_count = due_count_result.get("due_today", 0)

                        if due_count > 0:
                            await bot.send_message(
                                user.user_id,
                                f"🔔 <b>Flashcard eslatma!</b>\n\n"
                                f"Bugun <b>{due_count} ta</b> kartochkani takrorlash kerak.\n\n"
                                f"📚 /flashcard - Boshlash",
                            )
                            sent += 1
                except Exception as e:
                    failed += 1
                    if "blocked" not in str(e).lower() and "deactivated" not in str(e).lower():
                        logger.debug(f"Flashcard reminder failed for user {user.user_id}: {e}")
            logger.info(f"Flashcard reminders: sent={sent}, failed={failed}")
    except Exception as e:
        logger.error(f"Flashcard reminder error: {e}")



async def cleanup_expired_items():
    """Muddati tugagan itemlarni tozalash"""
    from src.database import get_session
    from src.database.models import UserInventory
    from sqlalchemy import update
    from datetime import datetime
    from src.core.logging import get_logger
    logger = get_logger(__name__)

    try:
        # Poll sessions cleanup
        try:
            from src.handlers.quiz.personal import cleanup_old_sessions
            cleanup_old_sessions()
            logger.debug("Poll sessions cleaned up")
        except Exception as pe:
            logger.debug(f"Poll cleanup skipped: {pe}")

        # Database cleanup - ORM orqali (SQLite va PostgreSQL uchun universal)
        async with get_session() as session:
            now = datetime.utcnow()
            stmt = (
                update(UserInventory)
                .where(UserInventory.expires_at < now)
                .where(UserInventory.is_active == True)
                .values(is_active=False)
            )
            result = await session.execute(stmt)
            await session.commit()
            logger.info(f"Expired items cleaned up: {result.rowcount} items")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


async def cleanup_memory_and_sessions():
    """Memory va session cleanup - tez-tez ishlaydigan job"""
    from src.core.logging import get_logger
    logger = get_logger(__name__)

    try:
        # 1. Poll sessions cleanup
        try:
            from src.handlers.quiz.personal import cleanup_old_sessions, get_memory_stats
            cleanup_old_sessions()
            stats = get_memory_stats()
            logger.debug(f"Poll cleanup: {stats}")
        except Exception as e:
            logger.debug(f"Poll cleanup skipped: {e}")

        # 2. Duel sessions cleanup
        try:
            from src.handlers.duel import cleanup_old_duels, get_duel_stats
            cleanup_old_duels()
            stats = get_duel_stats()
            logger.debug(f"Duel cleanup: {stats}")
        except Exception as e:
            logger.debug(f"Duel cleanup skipped: {e}")

        # 3. Memory fallback cleanup (TTL expired items)
        try:
            from src.core.redis import get_memory_stats as redis_memory_stats, _cleanup_expired_memory
            _cleanup_expired_memory()
            stats = redis_memory_stats()
            if stats["total_items"] > 0:
                logger.debug(f"Memory fallback: {stats}")
        except Exception as e:
            logger.debug(f"Memory cleanup skipped: {e}")

    except Exception as e:
        logger.error(f"Memory cleanup error: {e}")

async def auto_suspend_mastered_cards():
    """Mastered kartochkalarni avtomatik arxivlash (180+ kun interval)"""
    from src.database import get_session
    from src.services.flashcard_maintenance import FlashcardMaintenanceService
    from src.core.logging import get_logger
    
    logger = get_logger(__name__)
    
    try:
        async with get_session() as session:
            maintenance = FlashcardMaintenanceService(session)
            result = await maintenance.run_auto_suspend(threshold_days=180)
            
            if result.get("status") == "success":
                logger.info(
                    f"Auto-suspend: {result['total_suspended']} ta kartochka arxivlandi"
                )
            else:
                logger.error(f"Auto-suspend xatolik: {result.get('error')}")
                
    except Exception as e:
        logger.error(f"Auto-suspend job error: {e}")



def setup_scheduler(bot: Bot):
    """Scheduler sozlash"""
    global scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # Har soatda turnirni tekshirish
    scheduler.add_job(
        check_tournament_end,
        CronTrigger(minute=0),  # Har soat 00 daqiqada
        id="check_tournament",
        replace_existing=True
    )
    
    # Har kuni ertalab 9:00 da eslatma (UTC)
    scheduler.add_job(
        send_daily_reminders,
        CronTrigger(hour=9, minute=0),
        args=[bot],
        id="daily_reminders",
        replace_existing=True
    )

    # Flashcard eslatmalari - har kuni soat 10:00 va 18:00
    scheduler.add_job(
        send_flashcard_reminders,
        CronTrigger(hour=10, minute=0),
        args=[bot],
        id="flashcard_reminders_morning",
        replace_existing=True
    )
    scheduler.add_job(
        send_flashcard_reminders,
        CronTrigger(hour=18, minute=0),
        args=[bot],
        id="flashcard_reminders_evening",
        replace_existing=True
    )
    
    # Har kuni yarim tunda cleanup
    scheduler.add_job(
        cleanup_expired_items,
        CronTrigger(hour=0, minute=30),
        id="cleanup_items",
        replace_existing=True
    )
    # Har kuni 03:00 da mastered kartochkalarni arxivlash
    scheduler.add_job(
        auto_suspend_mastered_cards,
        CronTrigger(hour=3, minute=0),
        id="auto_suspend_cards",
        replace_existing=True
    )

    # Har 5 daqiqada memory/session cleanup (memory leak oldini olish)
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.add_job(
        cleanup_memory_and_sessions,
        IntervalTrigger(minutes=5),
        id="memory_cleanup",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler jobs: tournament, reminders, cleanup, memory_cleanup")
    return scheduler

async def on_startup(bot: Bot) -> None:
    """Startup hook"""
    logger.info("Starting up...")
    
    # Initialize database
    await init_database()
    
    # Initialize achievements
    await achievement_service.initialize_achievements()
    
    # Set bot for payment service
    payment_service.set_bot(bot)
    
    # Set webhook if enabled
    if settings.WEBHOOK_ENABLED and settings.WEBHOOK_URL:
        # Xavfsizlik ogohlantirishi
        if not settings.WEBHOOK_SECRET:
            logger.warning(
                "⚠️ WEBHOOK_SECRET sozlanmagan! "
                "Production muhitida WEBHOOK_SECRET ishlatish tavsiya etiladi."
            )
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            secret_token=settings.WEBHOOK_SECRET.get_secret_value() if settings.WEBHOOK_SECRET else None
        )
        logger.info(f"Webhook set to {settings.WEBHOOK_URL}")
    
    # Setup scheduler
    setup_scheduler(bot)
    logger.info("Scheduler started")
    
    # Get bot info
    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username}")


async def on_shutdown(bot: Bot) -> None:
    """Shutdown hook"""
    logger.info("Shutting down...")
    
    # Delete webhook
    if settings.WEBHOOK_ENABLED:
        await bot.delete_webhook()
    
    # Close connections
    await close_redis()
    await close_database()
    
    logger.info("Shutdown complete")


async def run_polling() -> None:
    """Run bot with polling"""
    bot = create_bot()
    dp = await create_dispatcher()
    
    register_handlers(dp, bot)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    try:
        logger.info("Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            close_bot_session=True
        )
    except Exception as e:
        logger.error(f"Polling error: {e}")
        raise


async def run_webhook() -> None:
    """Run bot with webhook"""
    bot = create_bot()
    dp = await create_dispatcher()
    
    register_handlers(dp, bot)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Create aiohttp app
    app = web.Application()
    
    # Setup webhook handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.WEBHOOK_SECRET.get_secret_value() if settings.WEBHOOK_SECRET else None
    )
    webhook_handler.register(app, path="/webhook")
    
    # Setup application
    setup_application(app, dp, bot=bot)
    
    # Run server
    logger.info(f"Starting webhook server on {settings.WEBHOOK_HOST}:{settings.WEBHOOK_PORT}")
    await web._run_app(
        app,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT
    )


def main() -> None:
    """Main entry point"""
    try:
        if settings.WEBHOOK_ENABLED:
            asyncio.run(run_webhook())
        else:
            asyncio.run(run_polling())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
