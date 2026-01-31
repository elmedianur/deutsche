"""
Shop Service - Qo'shimcha mahsulotlar do'koni
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

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
    async def purchase_item(user_id: int, item_id: str) -> bool:
        """Mahsulot sotib olish"""
        item = SHOP_ITEMS.get(item_id)
        if not item:
            return False
        
        # TODO: Implement actual purchase logic
        # 1. Check user balance
        # 2. Deduct stars
        # 3. Add item to user inventory
        
        return True


shop_service = ShopService()
