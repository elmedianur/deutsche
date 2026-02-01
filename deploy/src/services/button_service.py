"""
Button Text Service - Tugmalar matnini dinamik boshqarish
Admin panel orqali tugma nomlarini o'zgartirish imkoniyati
"""
from typing import Dict, Optional
from sqlalchemy import select

from src.database.connection import get_session
from src.database.models import BotSettings


# Default button texts
DEFAULT_BUTTONS: Dict[str, str] = {
    # Main menu buttons
    "btn_quiz_start": "📚 Quiz boshlash",
    "btn_flashcards": "🃏 Flashcards",
    "btn_duel": "⚔️ Duel",
    "btn_tournament": "🏆 Turnir",
    "btn_stats": "📊 Statistika",
    "btn_streak": "🔥 Streak",
    "btn_achievements": "🏅 Yutuqlar",
    "btn_shop": "🛒 Do'kon",
    "btn_premium": "⭐ Premium",
    "btn_settings": "⚙️ Sozlamalar",

    # Common buttons
    "btn_back": "◀️ Orqaga",
    "btn_main_menu": "🏠 Asosiy menyu",
    "btn_cancel": "❌ Bekor qilish",
    "btn_confirm_yes": "✅ Ha",
    "btn_confirm_no": "❌ Yo'q",

    # Quiz buttons
    "btn_skip_question": "⏭ O'tkazib yuborish",
    "btn_review_errors": "📋 Xatolarni ko'rish",
    "btn_retry_quiz": "🔄 Qayta urinish",
    "btn_another_quiz": "📚 Boshqa quiz",
    "btn_listen_audio": "🔊 Tinglash",
    "btn_all_topics": "📚 Barcha mavzular",

    # Flashcard buttons
    "btn_start_learning": "📖 O'rganishni boshlash",
    "btn_decks": "📚 Decklar",
    "btn_progress": "📊 Progress",
    "btn_show_answer": "🔍 Javobni ko'rsat",
    "btn_knew": "✅ Bildim",
    "btn_didnt_know": "❌ Bilmadim",

    # Duel buttons
    "btn_random_opponent": "⚔️ Tasodifiy raqib",
    "btn_invite_friend": "📨 Do'stni chaqirish",
    "btn_duel_stats": "📊 Duel statistikasi",
    "btn_accept": "✅ Qabul qilish",
    "btn_decline": "❌ Rad etish",

    # Premium buttons
    "btn_promo_code": "🎁 Promo kod",
    "btn_referral": "👥 Referal",
    "btn_buy_premium": "💳 Premium olish",

    # Settings buttons
    "btn_learning_settings": "📚 O'rganish sozlamalari",
    "btn_quiz_settings": "📝 Quiz sozlamalari",
    "btn_notifications": "Bildirishnomalar",
    "btn_reminders": "Eslatmalar",
    "btn_language": "🌐 Til",

    # Onboarding buttons
    "btn_start_guide": "🚀 Boshlash yo'riqnomasi",
    "btn_start_a1": "🎯 A1 dan boshlash",
    "btn_level_test": "📊 Darajamni aniqlash",
    "btn_choose_myself": "📚 O'zim tanlash",

    # Admin buttons
    "btn_admin_stats": "📊 Statistika",
    "btn_admin_users": "👥 Foydalanuvchilar",
    "btn_admin_questions": "❓ Savollar",
    "btn_admin_premium": "⭐ Premium",
    "btn_admin_broadcast": "📢 Xabar yuborish",
    "btn_admin_settings": "⚙️ Sozlamalar",

    # ============================================
    # SHOP (DO'KON) ICHKI TUGMALARI
    # ============================================
    "btn_shop_boost": "🚀 Boost",
    "btn_shop_protection": "🛡️ Himoya",
    "btn_shop_help": "💡 Yordam",
    "btn_shop_content": "📚 Kontent",
    "btn_shop_cosmetic": "🎨 Kosmetik",
    "btn_shop_special": "🎁 Maxsus",
    "btn_shop_bundles": "🎊 CHEGIRMALAR (51% gacha!)",
    "btn_shop_daily": "⭐ Kunlik Taklif",
    "btn_shop_popular": "🔥 Ommabop",
    "btn_shop_decks": "🃏 So'z Kartalari",
    "btn_shop_inventory": "📦 Mening Inventarim",

    # ============================================
    # TURNIR ICHKI TUGMALARI
    # ============================================
    "btn_tournament_current": "🏆 Joriy turnir",
    "btn_tournament_leaderboard": "📊 Reyting",
    "btn_tournament_prizes": "🎁 Sovrinlar",
    "btn_tournament_rules": "📜 Qoidalar",
    "btn_tournament_my_stats": "📈 Natijam",
    "btn_tournament_play": "🎮 Quiz o'ynash",
    "btn_tournament_join": "🎮 Qatnashish",
    "btn_tournament_play_more": "🎮 Yana o'ynash",

    # ============================================
    # STATISTIKA ICHKI TUGMALARI
    # ============================================
    "btn_stats_overall": "📊 Umumiy statistika",
    "btn_stats_weekly": "📅 Haftalik",
    "btn_stats_monthly": "📆 Oylik",
    "btn_stats_achievements": "🏅 Yutuqlar",
    "btn_stats_history": "📜 Tarix",

    # ============================================
    # ACHIEVEMENTS ICHKI TUGMALARI
    # ============================================
    "btn_achievements_all": "🏅 Barcha yutuqlar",
    "btn_achievements_earned": "✅ Qo'lga kiritilgan",
    "btn_achievements_locked": "🔒 Qolganlar",

    # ============================================
    # STREAK ICHKI TUGMALARI
    # ============================================
    "btn_streak_freeze": "❄️ Streak muzlatish",
    "btn_streak_history": "📊 Streak tarixi",
    "btn_streak_play": "🎮 Bugun o'ynash",
}

# Button categories for admin panel
BUTTON_CATEGORIES = {
    "main": {
        "name": "Asosiy menyu",
        "keys": ["btn_quiz_start", "btn_flashcards", "btn_duel", "btn_tournament",
                 "btn_stats", "btn_streak", "btn_achievements", "btn_shop",
                 "btn_premium", "btn_settings"]
    },
    "common": {
        "name": "Umumiy tugmalar",
        "keys": ["btn_back", "btn_main_menu", "btn_cancel", "btn_confirm_yes", "btn_confirm_no"]
    },
    "quiz": {
        "name": "Quiz tugmalari",
        "keys": ["btn_skip_question", "btn_review_errors", "btn_retry_quiz",
                 "btn_another_quiz", "btn_listen_audio", "btn_all_topics"]
    },
    "flashcard": {
        "name": "Flashcard tugmalari",
        "keys": ["btn_start_learning", "btn_decks", "btn_progress",
                 "btn_show_answer", "btn_knew", "btn_didnt_know"]
    },
    "duel": {
        "name": "Duel tugmalari",
        "keys": ["btn_random_opponent", "btn_invite_friend", "btn_duel_stats",
                 "btn_accept", "btn_decline"]
    },
    "premium": {
        "name": "Premium tugmalari",
        "keys": ["btn_promo_code", "btn_referral", "btn_buy_premium"]
    },
    "settings": {
        "name": "Sozlamalar tugmalari",
        "keys": ["btn_learning_settings", "btn_quiz_settings", "btn_notifications",
                 "btn_reminders", "btn_language"]
    },
    "onboarding": {
        "name": "Onboarding tugmalari",
        "keys": ["btn_start_guide", "btn_start_a1", "btn_level_test", "btn_choose_myself"]
    },
    "admin": {
        "name": "Admin tugmalari",
        "keys": ["btn_admin_stats", "btn_admin_users", "btn_admin_questions",
                 "btn_admin_premium", "btn_admin_broadcast", "btn_admin_settings"]
    },
    # ============================================
    # YANGI KATEGORIYALAR - ICHKI MENYULAR
    # ============================================
    "shop_inner": {
        "name": "🛒 Do'kon ichki tugmalari",
        "keys": ["btn_shop_boost", "btn_shop_protection", "btn_shop_help",
                 "btn_shop_content", "btn_shop_cosmetic", "btn_shop_special",
                 "btn_shop_bundles", "btn_shop_daily", "btn_shop_popular",
                 "btn_shop_decks", "btn_shop_inventory"]
    },
    "tournament_inner": {
        "name": "🏆 Turnir ichki tugmalari",
        "keys": ["btn_tournament_current", "btn_tournament_leaderboard",
                 "btn_tournament_prizes", "btn_tournament_rules",
                 "btn_tournament_my_stats", "btn_tournament_play",
                 "btn_tournament_join", "btn_tournament_play_more"]
    },
    "stats_inner": {
        "name": "📊 Statistika ichki tugmalari",
        "keys": ["btn_stats_overall", "btn_stats_weekly", "btn_stats_monthly",
                 "btn_stats_achievements", "btn_stats_history"]
    },
    "achievements_inner": {
        "name": "🏅 Yutuqlar ichki tugmalari",
        "keys": ["btn_achievements_all", "btn_achievements_earned", "btn_achievements_locked"]
    },
    "streak_inner": {
        "name": "🔥 Streak ichki tugmalari",
        "keys": ["btn_streak_freeze", "btn_streak_history", "btn_streak_play"]
    }
}


class ButtonTextService:
    """Service for managing dynamic button texts"""

    _cache: Dict[str, str] = {}
    _loaded: bool = False

    @classmethod
    async def _load_cache(cls) -> None:
        """Load all button texts from database to cache"""
        if cls._loaded:
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(BotSettings).where(BotSettings.key.like("button:%"))
                )
                settings = result.scalars().all()

                for setting in settings:
                    # Remove "button:" prefix
                    key = setting.key[7:]  # len("button:") = 7
                    cls._cache[key] = setting.value

            cls._loaded = True
        except Exception:
            # If database error, use defaults
            pass

    @classmethod
    async def get(cls, key: str) -> str:
        """Get button text by key"""
        # Load cache if not loaded
        if not cls._loaded:
            await cls._load_cache()

        # Return from cache or default
        if key in cls._cache:
            return cls._cache[key]

        return DEFAULT_BUTTONS.get(key, key)

    @classmethod
    async def set(cls, key: str, value: str) -> bool:
        """Set button text"""
        try:
            async with get_session() as session:
                # Check if exists
                result = await session.execute(
                    select(BotSettings).where(BotSettings.key == f"button:{key}")
                )
                setting = result.scalar_one_or_none()

                if setting:
                    setting.value = value
                else:
                    setting = BotSettings(key=f"button:{key}", value=value)
                    session.add(setting)

                await session.commit()

                # Update cache
                cls._cache[key] = value
                return True
        except Exception:
            return False

    @classmethod
    async def get_all(cls) -> Dict[str, str]:
        """Get all button texts (cached + defaults)"""
        if not cls._loaded:
            await cls._load_cache()

        result = DEFAULT_BUTTONS.copy()
        result.update(cls._cache)
        return result

    @classmethod
    async def get_by_category(cls, category: str) -> Dict[str, str]:
        """Get button texts by category"""
        if category not in BUTTON_CATEGORIES:
            return {}

        if not cls._loaded:
            await cls._load_cache()

        keys = BUTTON_CATEGORIES[category]["keys"]
        result = {}

        for key in keys:
            if key in cls._cache:
                result[key] = cls._cache[key]
            else:
                result[key] = DEFAULT_BUTTONS.get(key, key)

        return result

    @classmethod
    async def reset_to_default(cls, key: str) -> bool:
        """Reset button text to default"""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(BotSettings).where(BotSettings.key == f"button:{key}")
                )
                setting = result.scalar_one_or_none()

                if setting:
                    await session.delete(setting)
                    await session.commit()

                # Remove from cache
                if key in cls._cache:
                    del cls._cache[key]

                return True
        except Exception:
            return False

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cache (useful for testing)"""
        cls._cache.clear()
        cls._loaded = False
