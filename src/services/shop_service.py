"""
Shop Service - Qo'shimcha mahsulotlar do'koni
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from src.core.logging import get_logger

logger = get_logger(__name__)

# Do'kon mahsulotlari
SHOP_ITEMS = {
    # === BOOST ITEMS ===
    "xp_boost_2x": {
        "name": "2x XP Boost",
        "description": "2 soat davomida 2 baravar ko'p XP",
        "emoji": "🚀",
        "price": 10,  # Stars
        "duration_hours": 2,
        "category": "boost"
    },
    "streak_freeze": {
        "name": "Streak Freeze",
        "description": "1 kun streak yo'qolmaydi",
        "emoji": "🛡️",
        "price": 20,
        "uses": 1,
        "category": "protection"
    },
    "hint_pack_5": {
        "name": "5 ta Hint",
        "description": "Quiz paytida hint olish",
        "emoji": "💡",
        "price": 15,
        "uses": 5,
        "category": "help"
    },
    "hint_pack_20": {
        "name": "20 ta Hint",
        "description": "Quiz paytida hint olish (25% chegirma)",
        "emoji": "💡",
        "price": 45,
        "uses": 20,
        "category": "help"
    },
    
    # === CONTENT PACKS ===
    "extra_questions_50": {
        "name": "50 ta Qo'shimcha Savol",
        "description": "A1 darajasi uchun qo'shimcha savollar",
        "emoji": "📚",
        "price": 50,
        "category": "content"
    },
    "audio_pack": {
        "name": "Audio Pack",
        "description": "Barcha so'zlar talaffuzi",
        "emoji": "🎧",
        "price": 100,
        "category": "content"
    },
    
    # === COSMETICS ===
    "badge_vip": {
        "name": "VIP Badge",
        "description": "Profilingizda VIP belgisi",
        "emoji": "👑",
        "price": 200,
        "category": "cosmetic"
    },
    "custom_title": {
        "name": "Maxsus Unvon",
        "description": "O'zingiz xohlagan unvon",
        "emoji": "🏷️",
        "price": 150,
        "category": "cosmetic"
    }
}

# Chegirmalar
BUNDLES = {
    "starter_pack": {
        "name": "Starter Pack",
        "description": "Yangi boshlovchilar uchun",
        "items": ["streak_freeze", "hint_pack_5", "xp_boost_2x"],
        "original_price": 45,
        "price": 30,  # 33% off
        "emoji": "🎁"
    },
    "pro_pack": {
        "name": "Pro Pack",
        "description": "Jiddiy o'rganuvchilar uchun",
        "items": ["streak_freeze", "streak_freeze", "hint_pack_20", "audio_pack"],
        "original_price": 185,
        "price": 120,  # 35% off
        "emoji": "💎"
    }
}


class ShopService:
    """Do'kon xizmati"""
    
    @staticmethod
    def get_all_items() -> Dict:
        return SHOP_ITEMS
    
    @staticmethod
    def get_item(item_id: str) -> Optional[Dict]:
        return SHOP_ITEMS.get(item_id)
    
    @staticmethod
    def get_bundles() -> Dict:
        return BUNDLES
    
    @staticmethod
    def get_items_by_category(category: str) -> List[Dict]:
        return [
            {**item, "id": item_id}
            for item_id, item in SHOP_ITEMS.items()
            if item.get("category") == category
        ]
    
    @staticmethod
    async def purchase_item(user_id: int, item_id: str) -> Dict[str, Any]:
        """
        Mahsulot sotib olish.

        Args:
            user_id: Foydalanuvchi ID
            item_id: Mahsulot ID

        Returns:
            dict: {"success": bool, "error": str | None, "item": dict | None}
        """
        from src.database import get_session
        from src.repositories import UserRepository

        item = SHOP_ITEMS.get(item_id)
        if not item:
            return {"success": False, "error": "Mahsulot topilmadi", "item": None}

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)

                # 1. User olish va balansni tekshirish
                user = await user_repo.get_by_user_id(user_id)
                if not user:
                    return {"success": False, "error": "Foydalanuvchi topilmadi", "item": None}

                # Stars balansini tekshirish (agar user modelida stars maydoni bo'lsa)
                user_stars = getattr(user, 'stars', 0) or 0
                if user_stars < item["price"]:
                    return {
                        "success": False,
                        "error": f"Yetarli stars yo'q. Kerak: {item['price']}, Mavjud: {user_stars}",
                        "item": None
                    }

                # 2. Stars ayirish
                user.stars = user_stars - item["price"]

                # 3. Mahsulotni qo'llash (category ga qarab)
                category = item.get("category", "")

                if category == "protection" and item_id == "streak_freeze":
                    # Streak freeze qo'shish
                    if hasattr(user, 'streak') and user.streak:
                        user.streak.freeze_count += item.get("uses", 1)
                    else:
                        logger.warning(f"User {user_id} has no streak record for freeze")

                elif category == "help" and "hint" in item_id:
                    # Hint qo'shish
                    hints_to_add = item.get("uses", 5)
                    current_hints = getattr(user, 'hints', 0) or 0
                    user.hints = current_hints + hints_to_add

                elif category == "boost" and "xp_boost" in item_id:
                    # XP boost - bu alohida jadvalda saqlanishi kerak
                    # Hozircha faqat log qilamiz
                    logger.info(f"XP boost purchased by user {user_id}")

                # Save changes
                await user_repo.save(user)

            logger.info(
                f"Item purchased",
                extra={
                    "user_id": user_id,
                    "item_id": item_id,
                    "price": item["price"]
                }
            )

            return {
                "success": True,
                "error": None,
                "item": {**item, "id": item_id}
            }

        except Exception as e:
            logger.error(f"Purchase error for user {user_id}: {e}")
            return {"success": False, "error": "Xatolik yuz berdi", "item": None}


shop_service = ShopService()
