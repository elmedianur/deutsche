# -*- coding: utf-8 -*-
"""
🛒 PREMIUM SHOP HANDLER
To'liq boyitilgan va chiroyli market interfeysi
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery, InlineKeyboardMarkup
from src.database.models import User
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from datetime import datetime
import random

from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="shop")

# ╔══════════════════════════════════════════════════════════════════╗
# ║                    🏪 MARKET MAHSULOTLARI                        ║
# ╚══════════════════════════════════════════════════════════════════╝

SHOP_ITEMS = {
    # ═══════════════════════════════════════════════════════════════
    # 🚀 BOOST KATEGORIYASI - XP va Coin ko'paytirish
    # ═══════════════════════════════════════════════════════════════
    "xp_boost_2x": {
        "name": "⚡ 2x XP Boost",
        "description": "2 soat davomida 2 baravar ko'p XP oling!",
        "emoji": "⚡",
        "price": 15,
        "category": "boost",
        "duration": "2 soat",
        "icon": "⚡"
    },
    "xp_boost_3x": {
        "name": "🔥 3x XP Boost",
        "description": "1 soat davomida 3 baravar XP - tez o'sish!",
        "emoji": "🔥",
        "price": 25,
        "category": "boost",
        "duration": "1 soat",
        "icon": "🔥"
    },
    "xp_boost_5x": {
        "name": "💥 5x MEGA Boost",
        "description": "30 daqiqada 5x XP - maksimal o'sish!",
        "emoji": "💥",
        "price": 40,
        "category": "boost",
        "duration": "30 daq",
        "icon": "💥"
    },
    "xp_boost_10x": {
        "name": "🌟 10x ULTRA Boost",
        "description": "15 daqiqada 10x XP - SUPER tezlik!",
        "emoji": "🌟",
        "price": 75,
        "category": "boost",
        "duration": "15 daq",
        "icon": "🌟",
        "rare": True
    },
    "double_coins": {
        "name": "💰 2x Coin Boost",
        "description": "24 soat davomida 2x coin yig'ing",
        "emoji": "💰",
        "price": 30,
        "category": "boost",
        "duration": "24 soat",
        "icon": "💰"
    },
    "triple_coins": {
        "name": "💎 3x Coin Boost",
        "description": "12 soat davomida 3x coin - boylik!",
        "emoji": "💎",
        "price": 50,
        "category": "boost",
        "duration": "12 soat",
        "icon": "💎"
    },
    "lucky_boost": {
        "name": "🍀 Lucky Boost",
        "description": "Tasodifiy 2x-5x XP (1 soat)",
        "emoji": "🍀",
        "price": 20,
        "category": "boost",
        "duration": "1 soat",
        "icon": "🍀"
    },

    # ═══════════════════════════════════════════════════════════════
    # 🛡️ HIMOYA KATEGORIYASI - Streak va hayot saqlash
    # ═══════════════════════════════════════════════════════════════
    "streak_freeze": {
        "name": "❄️ Streak Freeze",
        "description": "1 kun streak yo'qolishidan himoya",
        "emoji": "❄️",
        "price": 20,
        "category": "protection",
        "duration": "1 kun",
        "icon": "❄️"
    },
    "streak_freeze_3": {
        "name": "🧊 3x Streak Freeze",
        "description": "3 kunlik streak himoyasi (25% tejash!)",
        "emoji": "🧊",
        "price": 45,
        "category": "protection",
        "duration": "3 kun",
        "icon": "🧊"
    },
    "streak_freeze_7": {
        "name": "🏔️ Haftalik Himoya",
        "description": "7 kunlik to'liq streak himoyasi",
        "emoji": "🏔️",
        "price": 80,
        "category": "protection",
        "duration": "7 kun",
        "icon": "🏔️"
    },
    "streak_freeze_30": {
        "name": "🏰 Oylik Himoya",
        "description": "30 kunlik MEGA himoya (50% tejash!)",
        "emoji": "🏰",
        "price": 200,
        "category": "protection",
        "duration": "30 kun",
        "icon": "🏰",
        "rare": True
    },
    "life_5": {
        "name": "❤️ 5 Hayot",
        "description": "5 ta qo'shimcha hayot",
        "emoji": "❤️",
        "price": 15,
        "category": "protection",
        "quantity": 5,
        "icon": "❤️"
    },
    "life_10": {
        "name": "💗 10 Hayot",
        "description": "10 ta hayot (17% tejash)",
        "emoji": "💗",
        "price": 25,
        "category": "protection",
        "quantity": 10,
        "icon": "💗"
    },
    "life_unlimited": {
        "name": "💖 Cheksiz Hayot",
        "description": "24 soat cheksiz hayot!",
        "emoji": "💖",
        "price": 60,
        "category": "protection",
        "duration": "24 soat",
        "icon": "💖"
    },
    "mistake_eraser": {
        "name": "✨ Xato O'chirish",
        "description": "Oxirgi 3 xatoni o'chiring",
        "emoji": "✨",
        "price": 35,
        "category": "protection",
        "quantity": 3,
        "icon": "✨"
    },

    # ═══════════════════════════════════════════════════════════════
    # 💡 YORDAM KATEGORIYASI - Quiz'da yordam
    # ═══════════════════════════════════════════════════════════════
    "hint_5": {
        "name": "💡 5 Hint",
        "description": "5 ta savol uchun hint",
        "emoji": "💡",
        "price": 10,
        "category": "help",
        "quantity": 5,
        "icon": "💡"
    },
    "hint_20": {
        "name": "🔦 20 Hint",
        "description": "20 hint paketi (25% tejash)",
        "emoji": "🔦",
        "price": 30,
        "category": "help",
        "quantity": 20,
        "icon": "🔦"
    },
    "hint_50": {
        "name": "🌟 50 Hint",
        "description": "MEGA hint paketi (40% tejash)",
        "emoji": "🌟",
        "price": 60,
        "category": "help",
        "quantity": 50,
        "icon": "🌟"
    },
    "hint_unlimited": {
        "name": "💫 Cheksiz Hint",
        "description": "1 hafta cheksiz hint!",
        "emoji": "💫",
        "price": 150,
        "category": "help",
        "duration": "7 kun",
        "icon": "💫",
        "rare": True
    },
    "skip_5": {
        "name": "⏭️ 5 Skip",
        "description": "5 ta qiyin savolni o'tkazish",
        "emoji": "⏭️",
        "price": 15,
        "category": "help",
        "quantity": 5,
        "icon": "⏭️"
    },
    "skip_20": {
        "name": "⏩ 20 Skip",
        "description": "20 ta skip (33% tejash)",
        "emoji": "⏩",
        "price": 40,
        "category": "help",
        "quantity": 20,
        "icon": "⏩"
    },
    "extra_time_10": {
        "name": "⏱️ +10s Vaqt",
        "description": "Har savolga +10 soniya (10 ta)",
        "emoji": "⏱️",
        "price": 20,
        "category": "help",
        "quantity": 10,
        "icon": "⏱️"
    },
    "extra_time_30": {
        "name": "⏰ +30s Vaqt",
        "description": "Har savolga +30 soniya (5 ta)",
        "emoji": "⏰",
        "price": 25,
        "category": "help",
        "quantity": 5,
        "icon": "⏰"
    },
    "fifty_fifty": {
        "name": "✂️ 50/50",
        "description": "2 ta noto'g'ri javobni o'chirish (10 ta)",
        "emoji": "✂️",
        "price": 30,
        "category": "help",
        "quantity": 10,
        "icon": "✂️"
    },
    "double_chance": {
        "name": "🎯 Ikkinchi Imkoniyat",
        "description": "Xato javobda qayta urinish (5 ta)",
        "emoji": "🎯",
        "price": 25,
        "category": "help",
        "quantity": 5,
        "icon": "🎯"
    },
    "answer_reveal": {
        "name": "👁️ Javob Ko'rish",
        "description": "To'g'ri javobni ko'rsatish (3 ta)",
        "emoji": "👁️",
        "price": 40,
        "category": "help",
        "quantity": 3,
        "icon": "👁️"
    },

    # ═══════════════════════════════════════════════════════════════
    # 📚 KONTENT KATEGORIYASI - Qo'shimcha materiallar
    # ═══════════════════════════════════════════════════════════════
    "unlock_a2": {
        "name": "📗 A2 Daraja",
        "description": "A2 darajadagi barcha savollar",
        "emoji": "📗",
        "price": 100,
        "category": "content",
        "icon": "📗"
    },
    "unlock_b1": {
        "name": "📘 B1 Daraja",
        "description": "B1 darajadagi barcha savollar",
        "emoji": "📘",
        "price": 150,
        "category": "content",
        "icon": "📘"
    },
    "unlock_b2": {
        "name": "📙 B2 Daraja",
        "description": "B2 darajadagi barcha savollar",
        "emoji": "📙",
        "price": 200,
        "category": "content",
        "icon": "📙"
    },
    "unlock_c1": {
        "name": "📕 C1 Daraja",
        "description": "C1 professional daraja",
        "emoji": "📕",
        "price": 300,
        "category": "content",
        "icon": "📕"
    },
    "unlock_c2": {
        "name": "📓 C2 Daraja",
        "description": "C2 mutaxassis daraja",
        "emoji": "📓",
        "price": 400,
        "category": "content",
        "icon": "📓"
    },
    "unlock_all": {
        "name": "📚 BARCHA Darajalar",
        "description": "A1-C2 to'liq paket (40% tejash!)",
        "emoji": "📚",
        "price": 700,
        "category": "content",
        "icon": "📚",
        "rare": True
    },
    "audio_pack": {
        "name": "🎧 Audio Pack",
        "description": "Barcha so'zlar uchun talaffuz",
        "emoji": "🎧",
        "price": 100,
        "category": "content",
        "icon": "🎧"
    },
    "grammar_pack": {
        "name": "📖 Grammatika Pack",
        "description": "Qo'shimcha grammatika savollari",
        "emoji": "📖",
        "price": 80,
        "category": "content",
        "icon": "📖"
    },
    "idioms_pack": {
        "name": "🗣️ Idiomalar Pack",
        "description": "500+ nemis idiomalar",
        "emoji": "🗣️",
        "price": 120,
        "category": "content",
        "icon": "🗣️"
    },
    "business_german": {
        "name": "💼 Biznes Nemischa",
        "description": "Ish va biznes lug'ati",
        "emoji": "💼",
        "price": 150,
        "category": "content",
        "icon": "💼"
    },

    # ═══════════════════════════════════════════════════════════════
    # 🎨 KOSMETIK KATEGORIYASI - Profilni bezash
    # ═══════════════════════════════════════════════════════════════
    "badge_vip": {
        "name": "👑 VIP Badge",
        "description": "Profilingizda VIP belgisi",
        "emoji": "👑",
        "price": 200,
        "category": "cosmetic",
        "icon": "👑"
    },
    "badge_pro": {
        "name": "🏆 PRO Badge",
        "description": "Professional o'rganuvchi belgisi",
        "emoji": "🏆",
        "price": 150,
        "category": "cosmetic",
        "icon": "🏆"
    },
    "badge_scholar": {
        "name": "🎓 Scholar Badge",
        "description": "Olim belgisi",
        "emoji": "🎓",
        "price": 100,
        "category": "cosmetic",
        "icon": "🎓"
    },
    "badge_star": {
        "name": "⭐ Star Badge",
        "description": "Yulduz belgisi",
        "emoji": "⭐",
        "price": 80,
        "category": "cosmetic",
        "icon": "⭐"
    },
    "badge_fire": {
        "name": "🔥 Fire Badge",
        "description": "Streak ustasi belgisi",
        "emoji": "🔥",
        "price": 120,
        "category": "cosmetic",
        "icon": "🔥"
    },
    "badge_diamond": {
        "name": "💎 Diamond Badge",
        "description": "Noyob olmos belgisi",
        "emoji": "💎",
        "price": 300,
        "category": "cosmetic",
        "icon": "💎",
        "rare": True
    },
    "badge_legend": {
        "name": "🌟 Legend Badge",
        "description": "Afsonaviy o'rganuvchi",
        "emoji": "🌟",
        "price": 500,
        "category": "cosmetic",
        "icon": "🌟",
        "rare": True
    },
    "frame_gold": {
        "name": "🖼️ Oltin Ramka",
        "description": "Profil uchun oltin ramka",
        "emoji": "🖼️",
        "price": 150,
        "category": "cosmetic",
        "icon": "🖼️"
    },
    "frame_rainbow": {
        "name": "🌈 Kamalak Ramka",
        "description": "Rangli chiroyli ramka",
        "emoji": "🌈",
        "price": 180,
        "category": "cosmetic",
        "icon": "🌈"
    },
    "theme_dark": {
        "name": "🌙 Dark Tema",
        "description": "Qorong'u interfeys",
        "emoji": "🌙",
        "price": 80,
        "category": "cosmetic",
        "icon": "🌙"
    },
    "theme_nature": {
        "name": "🌿 Tabiat Temasi",
        "description": "Yashil tabiat dizayni",
        "emoji": "🌿",
        "price": 80,
        "category": "cosmetic",
        "icon": "🌿"
    },
    "theme_ocean": {
        "name": "🌊 Okean Temasi",
        "description": "Ko'k okean dizayni",
        "emoji": "🌊",
        "price": 80,
        "category": "cosmetic",
        "icon": "🌊"
    },
    "custom_emoji": {
        "name": "😎 Maxsus Emoji",
        "description": "Profilda maxsus emoji",
        "emoji": "😎",
        "price": 50,
        "category": "cosmetic",
        "icon": "😎"
    },

    # ═══════════════════════════════════════════════════════════════
    # 🎁 MAXSUS KATEGORIYA - Noyob va cheklangan
    # ═══════════════════════════════════════════════════════════════
    "mystery_box": {
        "name": "🎁 Mystery Box",
        "description": "Tasodifiy 3-5 ta mahsulot!",
        "emoji": "🎁",
        "price": 50,
        "category": "special",
        "icon": "🎁"
    },
    "mega_mystery": {
        "name": "🎊 MEGA Mystery",
        "description": "5-10 ta PREMIUM mahsulot!",
        "emoji": "🎊",
        "price": 150,
        "category": "special",
        "icon": "🎊",
        "rare": True
    },
    "gift_card_50": {
        "name": "🎀 50⭐ Gift Card",
        "description": "Do'stga sovg'a qiling!",
        "emoji": "🎀",
        "price": 50,
        "category": "special",
        "icon": "🎀"
    },
    "gift_card_100": {
        "name": "🎗️ 100⭐ Gift Card",
        "description": "Katta sovg'a kartasi",
        "emoji": "🎗️",
        "price": 100,
        "category": "special",
        "icon": "🎗️"
    },
    "vip_access": {
        "name": "🌟 VIP Access",
        "description": "1 hafta VIP imkoniyatlar",
        "emoji": "🌟",
        "price": 100,
        "category": "special",
        "duration": "7 kun",
        "icon": "🌟"
    },
    "early_access": {
        "name": "🚀 Early Access",
        "description": "Yangi xususiyatlarga erta kirish",
        "emoji": "🚀",
        "price": 200,
        "category": "special",
        "duration": "30 kun",
        "icon": "🚀"
    },
}

# ╔══════════════════════════════════════════════════════════════════╗
# ║                    🎁 CHEGIRMALI PAKETLAR                        ║
# ╚══════════════════════════════════════════════════════════════════╝

BUNDLES = {
    "starter_pack": {
        "name": "🌱 Boshlang'ich",
        "description": "Yangi boshlovchilar uchun ideal to'plam",
        "items": ["streak_freeze", "hint_5", "xp_boost_2x", "life_5"],
        "original": 60,
        "price": 35,
        "emoji": "🌱",
        "discount": 42
    },
    "learner_pack": {
        "name": "📖 O'rganuvchi",
        "description": "Faol o'rganuvchilar uchun",
        "items": ["streak_freeze_3", "hint_20", "xp_boost_3x", "extra_time_10", "skip_5"],
        "original": 140,
        "price": 85,
        "emoji": "📖",
        "discount": 39
    },
    "pro_pack": {
        "name": "💎 Professional",
        "description": "Jiddiy o'rganuvchilar uchun",
        "items": ["streak_freeze_7", "hint_50", "xp_boost_5x", "fifty_fifty", "double_chance"],
        "original": 235,
        "price": 140,
        "emoji": "💎",
        "discount": 40
    },
    "ultimate_pack": {
        "name": "🏆 Ultimate",
        "description": "Hamma narsa bir joyda!",
        "items": ["streak_freeze_30", "hint_unlimited", "xp_boost_10x", "unlock_all", "badge_vip"],
        "original": 1325,
        "price": 650,
        "emoji": "🏆",
        "discount": 51
    },
    "boost_bundle": {
        "name": "⚡ Boost Master",
        "description": "Barcha boost'lar birgalikda",
        "items": ["xp_boost_2x", "xp_boost_3x", "xp_boost_5x", "double_coins", "lucky_boost"],
        "original": 130,
        "price": 75,
        "emoji": "⚡",
        "discount": 42
    },
    "protection_bundle": {
        "name": "🛡️ Himoya Master",
        "description": "To'liq himoya paketi",
        "items": ["streak_freeze_7", "life_unlimited", "mistake_eraser"],
        "original": 175,
        "price": 99,
        "emoji": "🛡️",
        "discount": 43
    },
    "help_bundle": {
        "name": "💡 Yordam Master",
        "description": "Barcha yordam vositalari",
        "items": ["hint_50", "skip_20", "fifty_fifty", "double_chance", "answer_reveal"],
        "original": 195,
        "price": 110,
        "emoji": "💡",
        "discount": 44
    },
    "cosmetic_bundle": {
        "name": "🎨 Style Master",
        "description": "To'liq bezash paketi",
        "items": ["badge_pro", "badge_scholar", "frame_gold", "theme_dark", "custom_emoji"],
        "original": 460,
        "price": 250,
        "emoji": "🎨",
        "discount": 46
    },
    "weekly_deal": {
        "name": "📅 Haftalik Deal",
        "description": "Faqat shu hafta - super chegirma!",
        "items": ["xp_boost_5x", "streak_freeze_3", "hint_20", "skip_5"],
        "original": 130,
        "price": 60,
        "emoji": "📅",
        "discount": 54,
        "limited": True
    },
}

# ╔══════════════════════════════════════════════════════════════════╗
# ║                    📂 KATEGORIYALAR                              ║
# ╚══════════════════════════════════════════════════════════════════╝

CATEGORIES = {
    "boost": {
        "name": "🚀 Boost",
        "icon": "🚀",
        "color": "🟡",
        "description": "XP va coin ko'paytirish"
    },
    "protection": {
        "name": "🛡️ Himoya",
        "icon": "🛡️",
        "color": "🔵",
        "description": "Streak va hayotni saqlash"
    },
    "help": {
        "name": "💡 Yordam",
        "icon": "💡",
        "color": "🟢",
        "description": "Quiz'da yordam va hint"
    },
    "content": {
        "name": "📚 Kontent",
        "icon": "📚",
        "color": "🟣",
        "description": "Qo'shimcha darajalar va materiallar"
    },
    "cosmetic": {
        "name": "🎨 Kosmetik",
        "icon": "🎨",
        "color": "🟠",
        "description": "Profilni bezash va badge'lar"
    },
    "special": {
        "name": "🎁 Maxsus",
        "icon": "🎁",
        "color": "🔴",
        "description": "Noyob va cheklangan mahsulotlar"
    },
}

# ╔══════════════════════════════════════════════════════════════════╗
# ║                    🎮 MARKET INTERFEYSI                          ║
# ╚══════════════════════════════════════════════════════════════════╝

def get_shop_header() -> str:
    """Chiroyli market sarlavhasi"""
    return """
╔═══════════════════════════════════╗
║      🛒 PREMIUM MARKET 🛒        ║
╚═══════════════════════════════════╝

🎯 <i>O'rganishni tezlashtiruvchi mahsulotlar!</i>

"""


def shop_menu_keyboard() -> InlineKeyboardMarkup:
    """Asosiy market menyusi"""
    builder = InlineKeyboardBuilder()

    # Kategoriyalar - 2 tadan
    builder.row(
        InlineKeyboardButton(text="🚀 Boost", callback_data="shop:cat:boost"),
        InlineKeyboardButton(text="🛡️ Himoya", callback_data="shop:cat:protection")
    )
    builder.row(
        InlineKeyboardButton(text="💡 Yordam", callback_data="shop:cat:help"),
        InlineKeyboardButton(text="📚 Kontent", callback_data="shop:cat:content")
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Kosmetik", callback_data="shop:cat:cosmetic"),
        InlineKeyboardButton(text="🎁 Maxsus", callback_data="shop:cat:special")
    )

    # Maxsus bo'limlar
    builder.row(
        InlineKeyboardButton(text="🎊 CHEGIRMALAR (51% gacha!)", callback_data="shop:bundles")
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Kunlik Taklif", callback_data="shop:daily"),
        InlineKeyboardButton(text="🔥 Ommabop", callback_data="shop:popular")
    )
    builder.row(
        InlineKeyboardButton(text="🃏 So'z Kartalari", callback_data="shop:decks")
    )

    # Inventar va orqaga
    builder.row(
        InlineKeyboardButton(text="📦 Mening Inventarim", callback_data="shop:inventory")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="menu:main")
    )

    return builder.as_markup()


@router.callback_query(F.data == "shop:menu")
async def shop_menu(callback: CallbackQuery):
    """Asosiy market sahifasi"""
    text = get_shop_header()

    text += """
┌─────────────────────────────────┐
│  🚀 <b>Boost</b> - XP va coin ↑↑      │
│  🛡️ <b>Himoya</b> - Streak saqlash    │
│  💡 <b>Yordam</b> - Hint va skip      │
│  📚 <b>Kontent</b> - Yangi darajalar  │
│  🎨 <b>Kosmetik</b> - Badge va tema   │
│  🎁 <b>Maxsus</b> - Noyob mahsulotlar │
└─────────────────────────────────┘

🎊 <b>CHEGIRMALAR</b> - 51% gacha tejash!
⭐ <b>Kunlik Taklif</b> - Har kuni yangi!

💳 <b>To'lov:</b> Telegram Stars ⭐
"""

    await callback.message.edit_text(text, reply_markup=shop_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("shop:cat:"))
async def show_category(callback: CallbackQuery):
    """Kategoriya sahifasi"""
    category = callback.data.split(":")[-1]
    cat_info = CATEGORIES.get(category, {"name": category, "icon": "📦", "description": ""})

    # Sarlavha
    text = f"""
╔═══════════════════════════════════╗
║   {cat_info['icon']} {cat_info['name'].upper()} {cat_info['icon']}
╚═══════════════════════════════════╝

<i>{cat_info['description']}</i>

"""

    builder = InlineKeyboardBuilder()

    # Mahsulotlar
    items_in_cat = [(k, v) for k, v in SHOP_ITEMS.items() if v["category"] == category]

    for item_id, item in items_in_cat:
        # Qo'shimcha ma'lumot
        extra = ""
        if item.get("duration"):
            extra = f" ⏱{item['duration']}"
        elif item.get("quantity"):
            extra = f" x{item['quantity']}"

        # Noyob belgisi
        rare_mark = "🌟 " if item.get("rare") else ""

        text += f"{item['icon']} <b>{item['name']}</b> — {item['price']}⭐{extra}\n"
        text += f"    <i>{item['description']}</i>\n\n"

        builder.row(InlineKeyboardButton(
            text=f"{rare_mark}{item['icon']} {item['name']} — {item['price']}⭐",
            callback_data=f"shop:buy:{item_id}"
        ))

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:menu"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "shop:bundles")
async def show_bundles(callback: CallbackQuery):
    """Chegirmali paketlar"""
    text = """
╔═══════════════════════════════════╗
║     🎊 CHEGIRMALI PAKETLAR 🎊    ║
╚═══════════════════════════════════╝

<i>Paketlar alohida sotib olishdan ancha arzon!</i>

"""

    builder = InlineKeyboardBuilder()

    for bundle_id, b in BUNDLES.items():
        limited = "🔥 " if b.get("limited") else ""

        text += f"{b['emoji']} <b>{b['name']}</b>\n"
        text += f"    <i>{b['description']}</i>\n"
        text += f"    <s>{b['original']}⭐</s> → <b>{b['price']}⭐</b> "
        text += f"<code>(-{b['discount']}%)</code>\n"
        text += f"    📦 {len(b['items'])} ta mahsulot\n\n"

        builder.row(InlineKeyboardButton(
            text=f"{limited}{b['emoji']} {b['name']} — {b['price']}⭐ (-{b['discount']}%)",
            callback_data=f"shop:bundle:{bundle_id}"
        ))

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:menu"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "shop:daily")
async def show_daily_deal(callback: CallbackQuery):
    """Kunlik maxsus taklif"""
    # Tasodifiy mahsulot tanlash (kunlik o'zgaradi)
    today = datetime.now().strftime("%Y%m%d")
    random.seed(int(today))

    all_items = list(SHOP_ITEMS.items())
    daily_items = random.sample(all_items, min(5, len(all_items)))

    text = """
╔═══════════════════════════════════╗
║      ⭐ KUNLIK TAKLIF ⭐          ║
╚═══════════════════════════════════╝

<i>Bugungi maxsus chegirmalar!</i>
<i>Faqat bugun amal qiladi!</i>

"""

    builder = InlineKeyboardBuilder()

    for item_id, item in daily_items:
        # 20-40% chegirma
        discount = random.randint(20, 40)
        original = item['price']
        new_price = int(original * (100 - discount) / 100)

        text += f"{item['icon']} <b>{item['name']}</b>\n"
        text += f"    <s>{original}⭐</s> → <b>{new_price}⭐</b> "
        text += f"<code>(-{discount}%)</code>\n\n"

        builder.row(InlineKeyboardButton(
            text=f"🔥 {item['icon']} {item['name']} — {new_price}⭐ (-{discount}%)",
            callback_data=f"shop:daily_buy:{item_id}:{new_price}"
        ))

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:menu"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "shop:popular")
async def show_popular(callback: CallbackQuery):
    """Ommabop mahsulotlar"""
    popular_ids = [
        "xp_boost_3x", "streak_freeze", "hint_20",
        "badge_pro", "unlock_b1", "mystery_box"
    ]

    text = """
╔═══════════════════════════════════╗
║       🔥 OMMABOP 🔥              ║
╚═══════════════════════════════════╝

<i>Eng ko'p sotib olingan mahsulotlar!</i>

"""

    builder = InlineKeyboardBuilder()

    for item_id in popular_ids:
        if item_id in SHOP_ITEMS:
            item = SHOP_ITEMS[item_id]
            text += f"{item['icon']} <b>{item['name']}</b> — {item['price']}⭐\n"
            text += f"    <i>{item['description']}</i>\n\n"

            builder.row(InlineKeyboardButton(
                text=f"🔥 {item['icon']} {item['name']} — {item['price']}⭐",
                callback_data=f"shop:buy:{item_id}"
            ))

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:menu"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    💳 TO'LOV TIZIMI                              ║
# ╚══════════════════════════════════════════════════════════════════╝

@router.callback_query(F.data.startswith("shop:buy:"))
async def buy_item(callback: CallbackQuery, bot: Bot):
    """Mahsulot sotib olish"""
    item_id = callback.data.split(":")[-1]
    item = SHOP_ITEMS.get(item_id)

    if not item:
        await callback.answer("❌ Mahsulot topilmadi!", show_alert=True)
        return

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"{item['icon']} {item['name']}",
            description=item['description'],
            payload=f"shop:{item_id}",
            currency="XTR",
            prices=[LabeledPrice(label=item['name'], amount=item['price'])]
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await callback.answer(f"❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(F.data.startswith("shop:daily_buy:"))
async def buy_daily_item(callback: CallbackQuery, bot: Bot):
    """Kunlik chegirmali mahsulot"""
    parts = callback.data.split(":")
    item_id = parts[2]
    price = int(parts[3])
    item = SHOP_ITEMS.get(item_id)

    if not item:
        await callback.answer("❌ Mahsulot topilmadi!", show_alert=True)
        return

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"🔥 {item['icon']} {item['name']} (Kunlik!)",
            description=f"{item['description']} — Kunlik chegirma!",
            payload=f"daily:{item_id}",
            currency="XTR",
            prices=[LabeledPrice(label=item['name'], amount=price)]
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await callback.answer(f"❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(F.data.startswith("shop:bundle:"))
async def buy_bundle(callback: CallbackQuery, bot: Bot):
    """Paket sotib olish"""
    bundle_id = callback.data.split(":")[-1]
    bundle = BUNDLES.get(bundle_id)

    if not bundle:
        await callback.answer("❌ Paket topilmadi!", show_alert=True)
        return

    items_list = [SHOP_ITEMS.get(i, {}).get('name', i) for i in bundle['items']]

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"{bundle['emoji']} {bundle['name']}",
            description=f"Ichida: {', '.join(items_list[:3])}...",
            payload=f"bundle:{bundle_id}",
            currency="XTR",
            prices=[LabeledPrice(label=bundle['name'], amount=bundle['price'])]
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await callback.answer(f"❌ Xatolik yuz berdi", show_alert=True)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    ✅ TO'LOV TASDIQLASH                          ║
# ╚══════════════════════════════════════════════════════════════════╝

@router.pre_checkout_query(
    F.invoice_payload.startswith("shop:") |
    F.invoice_payload.startswith("bundle:") |
    F.invoice_payload.startswith("daily:")
)
async def shop_pre_checkout(pre_checkout: PreCheckoutQuery):
    """To'lovni tasdiqlash"""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def shop_successful_payment(message: Message, db_user: User):
    """Muvaffaqiyatli to'lov"""
    payment = message.successful_payment
    payload = payment.invoice_payload

    try:
        if payload.startswith("shop:") or payload.startswith("daily:"):
            item_id = payload.split(":")[-1]
            item = SHOP_ITEMS.get(item_id)

            if item:
                await message.answer(
                    f"""
╔═══════════════════════════════════╗
║     🎉 XARID MUVAFFAQIYATLI!     ║
╚═══════════════════════════════════╝

{item['icon']} <b>{item['name']}</b>

✅ Mahsulot inventaringizga qo'shildi!

Rahmat xaridingiz uchun! 🙏
""",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📦 Inventar", callback_data="shop:inventory")],
                        [InlineKeyboardButton(text="🛒 Do'kon", callback_data="shop:menu")],
                        [InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main")]
                    ])
                )
                logger.info(f"Purchase: user={db_user.user_id}, item={item_id}")

        elif payload.startswith("bundle:"):
            bundle_id = payload.split(":")[-1]
            bundle = BUNDLES.get(bundle_id)

            if bundle:
                items_text = "\n".join([
                    f"   • {SHOP_ITEMS.get(i, {}).get('icon', '📦')} {SHOP_ITEMS.get(i, {}).get('name', i)}"
                    for i in bundle['items']
                ])

                await message.answer(
                    f"""
╔═══════════════════════════════════╗
║     🎊 PAKET SOTIB OLINDI!       ║
╚═══════════════════════════════════╝

{bundle['emoji']} <b>{bundle['name']}</b>

<b>Qo'shildi:</b>
{items_text}

✅ Barcha mahsulotlar inventarda!
""",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📦 Inventar", callback_data="shop:inventory")],
                        [InlineKeyboardButton(text="🛒 Do'kon", callback_data="shop:menu")],
                        [InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main")]
                    ])
                )
                logger.info(f"Bundle: user={db_user.user_id}, bundle={bundle_id}")

    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await message.answer("❌ Xatolik yuz berdi. Admin bilan bog'laning.")


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    📦 INVENTAR                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

@router.callback_query(F.data == "shop:inventory")
async def show_inventory(callback: CallbackQuery, db_user: User):
    """Inventarni ko'rsatish"""
    text = """
╔═══════════════════════════════════╗
║       📦 MENING INVENTARIM       ║
╚═══════════════════════════════════╝

"""

    # TODO: Real inventar ma'lumotlari
    text += "<i>Inventaringiz bo'sh.</i>\n\n"
    text += "<i>Do'kondan mahsulot sotib oling!</i>"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Do'kon", callback_data="shop:menu"))
    builder.row(InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    🃏 SO'Z KARTALARI                             ║
# ╚══════════════════════════════════════════════════════════════════╝

@router.callback_query(F.data == "shop:decks")
async def shop_decks_levels(callback: CallbackQuery, db_user: User):
    """So'z kartalari do'koni - Avval darajalar ko'rsatiladi"""
    from src.database import get_session
    from src.database.models import Level, FlashcardDeck, UserDeckPurchase
    from sqlalchemy import select, func

    text = """
╔═══════════════════════════════════╗
║    🃏 SO'Z KARTALARI DO'KONI 🃏   ║
╚═══════════════════════════════════╝

<i>Darajani tanlang va mavzularni sotib oling!</i>
<i>Quiz va Flashcard birga ochiladi!</i>

"""

    builder = InlineKeyboardBuilder()

    # Level icons
    level_icons = {
        "A1": "🟢", "A2": "🟡", "B1": "🔵",
        "B2": "🟣", "C1": "🟠", "C2": "🔴"
    }

    async with get_session() as session:
        # Get levels with deck count
        result = await session.execute(
            select(Level).where(Level.is_active == True).order_by(Level.display_order)
        )
        levels = result.scalars().all()

        # Get purchased deck count per level
        purchased_result = await session.execute(
            select(UserDeckPurchase.deck_id).where(
                UserDeckPurchase.user_id == db_user.user_id,
                UserDeckPurchase.is_active == True
            )
        )
        purchased_ids = set(r[0] for r in purchased_result.all())

        for level in levels:
            # Count decks in this level
            deck_result = await session.execute(
                select(func.count(FlashcardDeck.id)).where(
                    FlashcardDeck.level_id == level.id,
                    FlashcardDeck.is_active == True
                )
            )
            deck_count = deck_result.scalar() or 0

            if deck_count == 0:
                continue

            # Count purchased decks in this level
            purchased_in_level = await session.execute(
                select(func.count(FlashcardDeck.id)).where(
                    FlashcardDeck.level_id == level.id,
                    FlashcardDeck.is_active == True,
                    FlashcardDeck.id.in_(purchased_ids) if purchased_ids else False
                )
            )
            purchased_count = purchased_in_level.scalar() or 0

            # Icon for level
            icon = level_icons.get(level.name.upper().split()[0], "📚")

            # Status text
            if purchased_count == deck_count and deck_count > 0:
                status = "✅"
            elif purchased_count > 0:
                status = f"📊 {purchased_count}/{deck_count}"
            else:
                status = f"📚 {deck_count} ta"

            builder.row(InlineKeyboardButton(
                text=f"{icon} {level.name} — {status}",
                callback_data=f"shop:decks_level:{level.id}"
            ))

    if not levels:
        text += "\n<i>Hozircha darajalar yo'q.</i>\n"

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:menu"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("shop:decks_level:"))
async def shop_decks_by_level(callback: CallbackQuery, db_user: User):
    """Daraja ichidagi mavzular (decklar)"""
    from src.database import get_session
    from src.database.models import Level, FlashcardDeck, UserDeckPurchase
    from sqlalchemy import select

    level_id = int(callback.data.split(":")[-1])

    async with get_session() as session:
        # Get level info
        level_result = await session.execute(
            select(Level).where(Level.id == level_id)
        )
        level = level_result.scalar_one_or_none()

        if not level:
            await callback.answer("❌ Daraja topilmadi!", show_alert=True)
            return

        # Level icons
        level_icons = {
            "A1": "🟢", "A2": "🟡", "B1": "🔵",
            "B2": "🟣", "C1": "🟠", "C2": "🔴"
        }
        icon = level_icons.get(level.name.upper().split()[0], "📚")

        text = f"""
╔═══════════════════════════════════╗
║   {icon} {level.name.upper()} MAVZULARI {icon}
╚═══════════════════════════════════╝

<i>Mavzuni sotib oling - Quiz va Flashcard birga ochiladi!</i>

✅ = Sotib olingan
🆓 = Bepul
⭐ = Premium

"""

        builder = InlineKeyboardBuilder()

        # Get decks in this level
        result = await session.execute(
            select(FlashcardDeck).where(
                FlashcardDeck.level_id == level_id,
                FlashcardDeck.is_active == True
            ).order_by(FlashcardDeck.display_order)
        )
        decks = result.scalars().all()

        # Get user's purchased decks
        purchased_result = await session.execute(
            select(UserDeckPurchase.deck_id).where(
                UserDeckPurchase.user_id == db_user.user_id,
                UserDeckPurchase.is_active == True
            )
        )
        purchased_ids = [r[0] for r in purchased_result.all()]

        for deck in decks:
            is_purchased = deck.id in purchased_ids
            is_free = not deck.is_premium or deck.price == 0

            if is_purchased:
                status = "✅"
                action = f"shop:deck_info:{deck.id}"
            elif is_free:
                status = "🆓"
                action = f"shop:deck_info:{deck.id}"
            else:
                status = "⭐"
                action = f"shop:deck_info:{deck.id}"

            price_text = f" — {deck.price}⭐" if deck.is_premium and deck.price > 0 and not is_purchased else ""

            builder.row(InlineKeyboardButton(
                text=f"{status} {deck.icon or '📚'} {deck.name}{price_text}",
                callback_data=action
            ))

        if not decks:
            text += "\n<i>Bu darajada mavzular yo'q.</i>\n"

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:decks"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("shop:deck_info:"))
async def deck_info(callback: CallbackQuery, db_user: User):
    """Deck haqida to'liq ma'lumot"""
    from src.database import get_session
    from src.database.models import FlashcardDeck, UserDeckPurchase, Level, Flashcard
    from sqlalchemy import select, func

    deck_id = int(callback.data.split(":")[-1])

    async with get_session() as session:
        result = await session.execute(
            select(FlashcardDeck).where(FlashcardDeck.id == deck_id)
        )
        deck = result.scalar_one_or_none()

        if not deck:
            await callback.answer("❌ Mavzu topilmadi!", show_alert=True)
            return

        # Get level info
        level = None
        level_icon = "📚"
        if deck.level_id:
            level_result = await session.execute(
                select(Level).where(Level.id == deck.level_id)
            )
            level = level_result.scalar_one_or_none()
            level_icons = {"A1": "🟢", "A2": "🟡", "B1": "🔵", "B2": "🟣", "C1": "🟠", "C2": "🔴", "PREMIUM": "💎"}
            if level:
                level_icon = level_icons.get(level.name.upper().split()[0], "📚")

        # Get actual card count
        card_count_result = await session.execute(
            select(func.count(Flashcard.id)).where(
                Flashcard.deck_id == deck_id,
                Flashcard.is_active == True
            )
        )
        actual_card_count = card_count_result.scalar() or 0

        # Check if purchased
        result = await session.execute(
            select(UserDeckPurchase).where(
                UserDeckPurchase.user_id == db_user.user_id,
                UserDeckPurchase.deck_id == deck_id
            )
        )
        is_purchased = result.scalar_one_or_none() is not None
        is_free = not deck.is_premium or deck.price == 0

    # Status badge
    if is_purchased:
        status_badge = "✅ SOTIB OLINGAN"
        price_section = ""
    elif is_free:
        status_badge = "🆓 BEPUL"
        price_section = ""
    else:
        status_badge = "⭐ PREMIUM"
        price_section = f"""
┌─────────────────────────────────┐
│  💰 <b>NARXI:</b> {deck.price} ⭐ (Stars)
│  💳 Telegram Stars orqali to'lov
└─────────────────────────────────┘
"""

    # Level description for usage
    level_name = level.name if level else "Umumiy"
    usage_tips = {
        "A1": "🎯 Kundalik oddiy muloqot, do'konda, ko'chada",
        "A2": "🎯 Do'stlar bilan suhbat, sayohat, xizmatlar",
        "B1": "🎯 Ish joyida, rasmiy yozishmalar, muhokamalar",
        "B2": "🎯 Murakkab mavzular, taqdimotlar, munozaralar",
        "C1": "🎯 Akademik muhit, professional soha, adabiyot",
        "C2": "🎯 Ona tili darajasida erkin muloqot",
        "PREMIUM": "🎯 Imtihonlarga tayyorgarlik, maxsus lug'at"
    }
    usage = usage_tips.get(level_name.upper().split()[0], "🎯 Kundalik muloqotda ishlatish mumkin")

    # What user will learn
    learn_section = f"""
📖 <b>NIMALARNI O'RGANASIZ:</b>
├ 🔤 {actual_card_count} ta so'z va ibora
├ 🗣 To'g'ri talaffuz (audio bilan)
├ 📝 Grammatik qoidalar
├ 💡 Amaliy misollar
└ 🎯 Real vaziyatlarda qo'llash
"""

    text = f"""
╔═══════════════════════════════════╗
║  {level_icon} <b>{deck.name}</b>
╚═══════════════════════════════════╝

{status_badge}

📋 <b>TAVSIF:</b>
{deck.description or "Bu mavzuda nemis tilining muhim so'z va iboralarini o'rganasiz."}

{learn_section}
🌍 <b>QAYERDA QO'LLAYSIZ:</b>
{usage}

📊 <b>STATISTIKA:</b>
├ 📚 So'zlar soni: <b>{actual_card_count}</b> ta
├ 👥 O'rganuvchilar: <b>{deck.users_studying or 0}</b> ta
├ 📈 Daraja: <b>{level_name}</b>
└ ⏱ Taxminiy vaqt: <b>{actual_card_count * 2}</b> daqiqa
{price_section}
<b>SOTIB OLSANGIZ:</b>
✅ Quiz testlari ochiladi
✅ Flashcard kartalari ochiladi
✅ Audio talaffuzlar
✅ Cheksiz takrorlash
"""

    builder = InlineKeyboardBuilder()

    if is_purchased or is_free:
        builder.row(
            InlineKeyboardButton(text="🃏 Flashcard", callback_data=f"flashcard:start:{deck_id}"),
            InlineKeyboardButton(text="📝 Quiz", callback_data=f"quiz:day:{deck.day_id}" if deck.day_id else "noop")
        )
    else:
        builder.row(InlineKeyboardButton(
            text=f"💳 Sotib olish — {deck.price} ⭐",
            callback_data=f"shop:deck_buy:{deck_id}"
        ))

    # Back button - go to level if available
    if deck.level_id:
        builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"shop:decks_level:{deck.level_id}"))
    else:
        builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop:decks"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("shop:deck_buy:"))
async def deck_buy(callback: CallbackQuery, bot: Bot):
    """Deck sotib olish - Quiz va Flashcard birga"""
    from src.database import get_session
    from src.database.models import FlashcardDeck
    from sqlalchemy import select

    deck_id = int(callback.data.split(":")[-1])

    async with get_session() as session:
        result = await session.execute(
            select(FlashcardDeck).where(FlashcardDeck.id == deck_id)
        )
        deck = result.scalar_one_or_none()

    if not deck:
        await callback.answer("❌ Mavzu topilmadi!", show_alert=True)
        return

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"📚 {deck.name}",
            description=f"{deck.description or 'Premium mavzu'}\n\n✅ Quiz + Flashcard birga ochiladi!",
            payload=f"deck:{deck_id}",
            currency="XTR",
            prices=[LabeledPrice(label=deck.name, amount=deck.price)]
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Deck invoice error: {e}")
        await callback.answer("❌ Xatolik!", show_alert=True)


@router.pre_checkout_query(F.invoice_payload.startswith("deck:"))
async def deck_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Deck to'lov tasdiqlash"""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment.invoice_payload.startswith("deck:"))
async def deck_successful_payment(message: Message, db_user: User):
    """Deck sotib olish - Quiz va Flashcard birga ochiladi"""
    from src.database import get_session
    from src.database.models import FlashcardDeck, UserDeckPurchase
    from sqlalchemy import select

    payload = message.successful_payment.invoice_payload
    deck_id = int(payload.split(":")[-1])
    price = message.successful_payment.total_amount

    try:
        async with get_session() as session:
            # Get deck with day_id
            result = await session.execute(
                select(FlashcardDeck).where(FlashcardDeck.id == deck_id)
            )
            deck = result.scalar_one_or_none()

            if deck:
                # Check if already purchased
                result = await session.execute(
                    select(UserDeckPurchase).where(
                        UserDeckPurchase.user_id == db_user.user_id,
                        UserDeckPurchase.deck_id == deck_id
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    # Create purchase record
                    purchase = UserDeckPurchase(
                        user_id=db_user.user_id,
                        deck_id=deck_id,
                        price_paid=price,
                        is_active=True
                    )
                    session.add(purchase)

                    # Update deck users_studying count
                    deck.users_studying += 1

                    await session.commit()

                # Response message
                day_info = ""
                if deck.day_id:
                    day_info = "\n✅ Quiz savollari ham ochildi!"

                await message.answer(
                    f"""
🎉 <b>Xarid muvaffaqiyatli!</b>

📚 <b>{deck.name}</b>

✅ Flashcard kartalari ochildi!{day_info}

Endi bu mavzuni Quiz va Flashcard orqali o'rganishingiz mumkin!
""",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🃏 Flashcard boshlash", callback_data=f"flashcard:start:{deck_id}")],
                        [InlineKeyboardButton(text="🛒 Do'kon", callback_data="shop:menu")],
                        [InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main")]
                    ])
                )
                logger.info(f"Deck purchase: user={db_user.user_id}, deck={deck_id}, day_id={deck.day_id}")
            else:
                await message.answer("❌ Deck topilmadi!")

    except Exception as e:
        logger.error(f"Deck payment error: {e}")
        await message.answer("❌ Xatolik yuz berdi. Admin bilan bog'laning.")
