"""
Menu handler - Main menu and navigation
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from src.database import get_session
from src.database.models import User
from src.repositories import ProgressRepository, StreakRepository
from src.services import achievement_service
from src.keyboards.inline import (
    main_menu_keyboard,
    settings_keyboard,
    back_button,
)
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="menu")


@router.callback_query(F.data == "menu:main")
async def main_menu(callback: CallbackQuery, db_user: User):
    """Show main menu"""
    text = f"""
🏠 <b>Asosiy menyu</b>

👤 {db_user.full_name}
📊 Quiz'lar: {db_user.total_quizzes} | To'g'ri: {db_user.total_correct}

Quyidagi menyudan tanlang 👇
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "stats:menu")
async def stats_menu(callback: CallbackQuery, db_user: User):
    """Show statistics menu"""
    async with get_session() as session:
        progress_repo = ProgressRepository(session)
        streak_repo = StreakRepository(session)
        
        stats = await progress_repo.get_user_stats(db_user.user_id)
        streak = await streak_repo.get_or_create(db_user.user_id)
        
        # Get achievement stats
        ach_stats = await achievement_service.get_achievement_stats(db_user.user_id)
    user_rank = await get_user_rank(db_user.user_id)
    
    text = f"""
📊 <b>Sizning statistikangiz</b>

<b>Quiz natijalari:</b>
• Jami quiz: {stats['total_quizzes']}
• To'g'ri javoblar: {stats['total_correct']}
• Jami savollar: {stats['total_questions']}
• Aniqlik: {stats['accuracy']:.1f}%
• O'rtacha vaqt: {stats['avg_time']:.1f}s

<b>Streak:</b>
🔥 Joriy streak: {streak.current_streak} kun
🏆 Eng uzun streak: {streak.longest_streak} kun

<b>Yutuqlar:</b>
🏅 {ach_stats['earned']}/{ach_stats['total']} ({ach_stats['percentage']:.0f}%)

<b>Reyting:</b>
🥇 #{user_rank} o'rin
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_button()
    )
    await callback.answer()


async def get_user_rank(user_id: int) -> int:
    """Get user's rank"""
    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        return await user_repo.get_user_rank(user_id)


@router.callback_query(F.data == "streak:info")
async def streak_info(callback: CallbackQuery, db_user: User):
    """Show streak information"""
    async with get_session() as session:
        streak_repo = StreakRepository(session)
        streak = await streak_repo.get_or_create(db_user.user_id)
    
    days_left, milestone = streak.days_until_milestone
    
    if streak.current_streak > 0:
        status_emoji = "🔥"
        status_text = f"Ajoyib! {streak.current_streak} kunlik streak!"
    else:
        status_emoji = "❄️"
        status_text = "Streak yo'q. Bugun quizni boshlang!"
    
    freeze_text = f"🛡 Freeze: {streak.freeze_count} ta" if streak.freeze_count > 0 else ""
    
    text = f"""
{status_emoji} <b>Streak ma'lumotlari</b>

{status_text}

📅 Joriy streak: <b>{streak.current_streak}</b> kun
🏆 Eng uzun streak: <b>{streak.longest_streak}</b> kun
{freeze_text}

<b>Keyingi milestone:</b>
🎯 {milestone} kun - yana {days_left} kun qoldi

<b>Streak bonuslari:</b>
• 7 kun - 50 ⭐
• 30 kun - 200 ⭐ + 7 kun Premium
• 100 kun - 500 ⭐ + 30 kun Premium
• 365 kun - 2000 ⭐ + 90 kun Premium
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "achievements:menu")
async def achievements_menu(callback: CallbackQuery, db_user: User):
    """Show achievements - page 0"""
    await show_achievements_page(callback, db_user, page=0)


@router.callback_query(F.data.startswith("achievements:page:"))
async def achievements_page(callback: CallbackQuery, db_user: User):
    """Show achievements - specific page"""
    page = int(callback.data.split(":")[2])
    await show_achievements_page(callback, db_user, page=page)


async def show_achievements_page(callback: CallbackQuery, db_user: User, page: int = 0):
    """Show achievements with pagination"""
    per_page = 8
    
    achievements = await achievement_service.get_user_achievements(
        db_user.user_id,
        include_unearned=True
    )

    # Group by earned/not earned
    earned = [a for a in achievements if a["is_earned"]]
    unearned = [a for a in achievements if not a["is_earned"] and not a["is_secret"]]
    
    # All achievements for pagination
    all_achs = earned + unearned
    total_pages = (len(all_achs) + per_page - 1) // per_page
    
    # Get current page items
    start = page * per_page
    end = start + per_page
    current_achs = all_achs[start:end]
    
    # Stats
    stats = await achievement_service.get_achievement_stats(db_user.user_id)
    
    text = f"🏅 <b>Yutuqlar</b> ({page + 1}/{total_pages})\n"
    text += f"📊 Progress: {stats['earned']}/{stats['total']} ({stats['percentage']:.0f}%)\n\n"
    
    for ach in current_achs:
        if ach["is_earned"]:
            text += f"✅ {ach['icon']} {ach['name']} {ach['rarity_icon']}\n"
        else:
            text += f"🔒 ⬜ {ach['name']}\n   <i>{ach['description']}</i>\n"
    
    # Build keyboard with pagination
    builder = InlineKeyboardBuilder()
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"achievements:page:{page-1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"achievements:page:{page+1}")
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="menu:main")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "settings:menu")
async def settings_menu(callback: CallbackQuery, db_user: User):
    """Show settings menu"""
    settings_data = {
        "notifications": db_user.notifications_enabled,
        "daily_reminder": db_user.daily_reminder_enabled,
    }
    
    text = f"""
⚙️ <b>Sozlamalar</b>

O'zgartirmoqchi bo'lgan sozlamani tanlang:
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=settings_keyboard(settings_data)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:toggle:"))
async def toggle_setting(callback: CallbackQuery, db_user: User):
    """Toggle a setting"""
    setting = callback.data.split(":")[-1]
    
    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        
        user = await user_repo.get_by_user_id(db_user.user_id)
        
        if setting == "notifications":
            user.notifications_enabled = not user.notifications_enabled
            new_value = user.notifications_enabled
        elif setting == "daily_reminder":
            user.daily_reminder_enabled = not user.daily_reminder_enabled
            new_value = user.daily_reminder_enabled
        else:
            await callback.answer("Noma'lum sozlama", show_alert=True)
            return
        
        await user_repo.save(user)
    
    status = "yoqildi ✅" if new_value else "o'chirildi ❌"
    await callback.answer(f"Sozlama {status}")
    
    # Refresh settings menu
    await settings_menu(callback, db_user)


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    """No operation callback (for disabled buttons)"""
    await callback.answer()


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, db_user: User):
    """Show language settings"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="settings:set_lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="settings:set_lang:ru")
    )
    builder.row(
        InlineKeyboardButton(text="🇬🇧 English", callback_data="settings:set_lang:en")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:menu")
    )
    
    await callback.message.edit_text(
        "🌐 <b>Til sozlamalari</b>\n\n"
        "Bot tilini tanlang:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_lang:"))
async def set_language(callback: CallbackQuery, db_user: User):
    """Set user language"""
    lang = callback.data.split(":")[-1]

    lang_names = {"uz": "O'zbekcha", "ru": "Русский", "en": "English"}

    # Save to database
    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.language = lang
            await user_repo.save(user)

    await callback.answer(f"✅ Til o'zgartirildi: {lang_names.get(lang, lang)}", show_alert=True)
    await settings_menu(callback, db_user)


@router.callback_query(F.data == "settings:learning_path")
async def settings_learning_path(callback: CallbackQuery):
    """O'rganish yo'li - daraja tanlash"""
    text = """
📚 <b>O'rganish yo'li</b>

🎓 <b>Darajalar:</b>
┌─ 🟢 <b>A1</b> - Boshlang'ich (Boshlovchilar uchun)
├─ 🟡 <b>A2</b> - Elementar
├─ 🔵 <b>B1</b> - O'rta
├─ 🟣 <b>B2</b> - Yuqori o'rta
├─ 🟠 <b>C1</b> - Ilg'or
└─ 🔴 <b>C2</b> - Mutaxassis

💡 <b>Tavsiya:</b> A1 dan boshlang va har kuni kamida 1 ta quiz yeching!

Darajangizni tanlang 👇
"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🟢 A1", callback_data="onboard:level:A1"),
        InlineKeyboardButton(text="🟡 A2", callback_data="onboard:level:A2")
    )
    builder.row(
        InlineKeyboardButton(text="🔵 B1", callback_data="onboard:level:B1"),
        InlineKeyboardButton(text="🟣 B2", callback_data="onboard:level:B2")
    )
    builder.row(
        InlineKeyboardButton(text="🟠 C1", callback_data="onboard:level:C1"),
        InlineKeyboardButton(text="🔴 C2", callback_data="onboard:level:C2")
    )
    builder.row(
        InlineKeyboardButton(text="📖 Qo'llanma", callback_data="onboard:guide")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:menu")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# =====================================================
# O'RGANISH SOZLAMALARI (Learning Settings)
# =====================================================

@router.callback_query(F.data == "settings:learning")
async def settings_learning(callback: CallbackQuery, db_user: User):
    """O'rganish sozlamalari - asosiy sahifa"""
    from src.services import quiz_service

    # Joriy daraja nomini olish
    current_level_name = "Tanlanmagan"
    current_day_text = ""

    if db_user.current_level_id:
        try:
            levels = await quiz_service.get_levels()
            for level in levels:
                if level["id"] == db_user.current_level_id:
                    current_level_name = level["name"]
                    break
            current_day_text = f"\n📅 Joriy kun: <b>{db_user.current_day_number}-kun</b>"
        except Exception as e:
            # Level topilmasa kritik emas, default qiymatlar ishlatiladi
            logger.debug(f"Level lookup failed: {e}")

    # Progress bar yasash
    word_progress = db_user.daily_word_progress
    word_bar = _create_progress_bar(word_progress)

    quiz_progress = db_user.daily_quiz_progress
    quiz_bar = _create_progress_bar(quiz_progress)

    # Algoritm nomi
    algorithm = db_user.sr_algorithm or "sm2"
    algorithm_name = "SM-2" if algorithm == "sm2" else "Anki"

    text = f"""
📚 <b>O'rganish sozlamalari</b>

<b>Joriy holat:</b>
📊 Daraja: <b>{current_level_name}</b>{current_day_text}
🧠 Algoritm: <b>{algorithm_name}</b>

<b>Kunlik maqsadlar:</b>
📝 So'zlar: {db_user.words_learned_today}/{db_user.daily_word_goal}
{word_bar} {word_progress:.0f}%

🎯 Quizlar: {db_user.quizzes_today}/{db_user.daily_quiz_goal}
{quiz_bar} {quiz_progress:.0f}%

<b>Umumiy statistika:</b>
📖 Jami o'rganilgan so'zlar: {db_user.total_words_learned}
✅ Tugatilgan kunlar: {db_user.total_days_completed}

Sozlashni tanlang 👇
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"📊 Daraja: {current_level_name}",
            callback_data="settings:change_level"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🧠 Algoritm: {algorithm_name}",
            callback_data="settings:algorithm"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"📝 Kunlik so'z: {db_user.daily_word_goal}",
            callback_data="settings:daily_words"
        ),
        InlineKeyboardButton(
            text=f"🎯 Kunlik quiz: {db_user.daily_quiz_goal}",
            callback_data="settings:daily_quizzes"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Progressni qayta boshlash",
            callback_data="settings:reset_progress"
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:menu")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


def _create_progress_bar(percentage: float, length: int = 10) -> str:
    """Progress bar yaratish"""
    filled = int(percentage / 100 * length)
    empty = length - filled
    return "█" * filled + "░" * empty


# =====================================================
# SPACED REPETITION ALGORITHM SETTINGS
# =====================================================

@router.callback_query(F.data == "settings:algorithm")
async def settings_algorithm(callback: CallbackQuery, db_user: User):
    """Takrorlash algoritmi sozlamalari"""
    current_algo = db_user.sr_algorithm or "sm2"

    text = """
🧠 <b>Takrorlash algoritmi</b>

So'zlarni takrorlash uchun algoritmni tanlang:

<b>SM-2 (SuperMemo 2)</b>
├ Klassik spaced repetition
├ Intervallar: 1 → 6 → 15 → 38 → 95 kun
├ Barqaror interval o'sishi
└ Anki dan sekinroq

<b>Anki</b>
├ Modified SM-2 algoritmi
├ Intervallar: 1 → 3 → 8 → 20 → 50 kun
├ Easy/Hard tugmalari ta'siri kuchli
└ Tezroq o'rganish

⚠️ <i>Algoritm o'zgartirilsa, yangi so'zlar uchun amal qiladi.
Mavjud so'zlar oldingi algoritm bo'yicha davom etadi.</i>
"""

    builder = InlineKeyboardBuilder()

    sm2_check = " ✓" if current_algo == "sm2" else ""
    anki_check = " ✓" if current_algo == "anki" else ""

    builder.row(
        InlineKeyboardButton(
            text=f"📊 SM-2 (Klassik){sm2_check}",
            callback_data="settings:set_algo:sm2"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🃏 Anki (Tez){anki_check}",
            callback_data="settings:set_algo:anki"
        )
    )
    builder.row(
        InlineKeyboardButton(text="📖 Taqqoslash", callback_data="settings:algo_compare")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:learning")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_algo:"))
async def settings_set_algorithm(callback: CallbackQuery, db_user: User):
    """Algoritmni o'rnatish"""
    algo = callback.data.split(":")[-1]

    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.sr_algorithm = algo
            await user_repo.save(user)

    algo_name = "SM-2" if algo == "sm2" else "Anki"
    await callback.answer(f"✅ Algoritm o'zgartirildi: {algo_name}", show_alert=True)
    await settings_algorithm(callback, db_user)


@router.callback_query(F.data == "settings:algo_compare")
async def settings_algo_compare(callback: CallbackQuery, db_user: User):
    """Algoritmlarni taqqoslash"""
    text = """
📊 <b>SM-2 vs Anki taqqoslash</b>

┌─────────────┬──────────────────┬──────────────────┐
│ Takrorlash  │      SM-2        │      Anki        │
├─────────────┼──────────────────┼──────────────────┤
│ 1           │ 1 kun            │ 1 kun            │
│ 2           │ 6 kun            │ ~3 kun           │
│ 3           │ ~15 kun          │ ~8 kun           │
│ 4           │ ~38 kun          │ ~20 kun          │
│ 5           │ ~95 kun          │ ~50 kun          │
│ 6           │ Arxiv ✓          │ ~125 kun         │
│ 7           │ -                │ Arxiv ✓          │
└─────────────┴──────────────────┴──────────────────┘

📌 <b>Arxiv qoidasi:</b> Interval 180+ kunga yetsa = Arxiv

<b>SM-2 uchun:</b>
✅ 5 ta muvaffaqiyatli takrorlashdan keyin arxivga
✅ Sekinroq, lekin puxta o'rganish
✅ Klassik, sinovdan o'tgan

<b>Anki uchun:</b>
✅ 6 ta muvaffaqiyatli takrorlashdan keyin arxivga
✅ Easy/Hard tugmalari ta'siri kuchli
✅ Ko'proq moslashuvchan

💡 <i>Agar birinchi marta o'rgansangiz - SM-2
Agar tez takrorlash kerak bo'lsa - Anki</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:algorithm")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "settings:change_level")
async def settings_change_level(callback: CallbackQuery, db_user: User):
    """Darajani o'zgartirish"""
    from src.services import quiz_service

    levels = await quiz_service.get_levels()

    text = """
📊 <b>Darajani tanlang</b>

Yangi darajani tanlasangiz, o'rganish 1-kundan boshlanadi.

⚠️ Joriy progressingiz saqlanadi, lekin yangi darajadan boshlanadi.
"""

    builder = InlineKeyboardBuilder()

    level_icons = {"A1": "🟢", "A2": "🟡", "B1": "🔵", "B2": "🟣", "C1": "🟠", "C2": "🔴"}

    for level in levels:
        icon = level_icons.get(level["name"], "📚")
        is_current = " ✓" if level["id"] == db_user.current_level_id else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {level['name']}{is_current}",
                callback_data=f"settings:set_level:{level['id']}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:learning")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_level:"))
async def settings_set_level(callback: CallbackQuery, db_user: User):
    """Darajani o'rnatish"""
    level_id = int(callback.data.split(":")[-1])

    async with get_session() as session:
        from src.repositories import UserRepository
        from src.services import quiz_service

        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)

        if user:
            user.current_level_id = level_id
            user.current_day_number = 1
            user.current_day_id = None  # Birinchi kun avtomatik tanlanadi

            # Birinchi kunni olish
            days = await quiz_service.get_days(level_id)
            if days:
                user.current_day_id = days[0]["id"]

            user.onboarding_completed = True
            await user_repo.save(user)

    await callback.answer("✅ Daraja o'zgartirildi! 1-kundan boshlanadi.", show_alert=True)
    await settings_learning(callback, db_user)


@router.callback_query(F.data == "settings:daily_words")
async def settings_daily_words(callback: CallbackQuery, db_user: User):
    """Kunlik so'z maqsadini sozlash"""
    text = f"""
📝 <b>Kunlik so'z maqsadi</b>

Joriy: <b>{db_user.daily_word_goal}</b> ta so'z

Har kuni nechta so'z o'rganmoqchisiz?
"""

    builder = InlineKeyboardBuilder()
    goals = [10, 20, 30, 50, 100]

    for goal in goals:
        is_current = " ✓" if goal == db_user.daily_word_goal else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{goal} ta so'z{is_current}",
                callback_data=f"settings:set_word_goal:{goal}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:learning")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_word_goal:"))
async def settings_set_word_goal(callback: CallbackQuery, db_user: User):
    """Kunlik so'z maqsadini o'rnatish"""
    goal = int(callback.data.split(":")[-1])

    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.daily_word_goal = goal
            await user_repo.save(user)

    await callback.answer(f"✅ Kunlik maqsad: {goal} ta so'z", show_alert=True)
    await settings_learning(callback, db_user)


@router.callback_query(F.data == "settings:daily_quizzes")
async def settings_daily_quizzes(callback: CallbackQuery, db_user: User):
    """Kunlik quiz maqsadini sozlash"""
    text = f"""
🎯 <b>Kunlik quiz maqsadi</b>

Joriy: <b>{db_user.daily_quiz_goal}</b> ta quiz

Har kuni nechta quiz yechmoqchisiz?
"""

    builder = InlineKeyboardBuilder()
    goals = [3, 5, 10, 15, 20]

    for goal in goals:
        is_current = " ✓" if goal == db_user.daily_quiz_goal else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{goal} ta quiz{is_current}",
                callback_data=f"settings:set_quiz_goal:{goal}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:learning")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_quiz_goal:"))
async def settings_set_quiz_goal(callback: CallbackQuery, db_user: User):
    """Kunlik quiz maqsadini o'rnatish"""
    goal = int(callback.data.split(":")[-1])

    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.daily_quiz_goal = goal
            await user_repo.save(user)

    await callback.answer(f"✅ Kunlik maqsad: {goal} ta quiz", show_alert=True)
    await settings_learning(callback, db_user)


@router.callback_query(F.data == "settings:reset_progress")
async def settings_reset_progress(callback: CallbackQuery, db_user: User):
    """Progressni qayta boshlash - tasdiqlash"""
    text = """
⚠️ <b>Progressni qayta boshlash</b>

Bu amal quyidagilarni qayta boshlaydi:
• Joriy kun 1-kunga qaytadi
• Kunlik progress nollanadi

<b>Statistikangiz saqlanadi:</b>
• Jami o'rganilgan so'zlar
• Streak
• Yutuqlar

Davom etasizmi?
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Ha, qayta boshlash", callback_data="settings:confirm_reset"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data="settings:learning")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "settings:confirm_reset")
async def settings_confirm_reset(callback: CallbackQuery, db_user: User):
    """Progressni qayta boshlash - amalga oshirish"""
    async with get_session() as session:
        from src.repositories import UserRepository
        from src.services import quiz_service

        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)

        if user:
            user.current_day_number = 1
            user.words_learned_today = 0
            user.quizzes_today = 0

            # Birinchi kunni olish
            if user.current_level_id:
                days = await quiz_service.get_days(user.current_level_id)
                if days:
                    user.current_day_id = days[0]["id"]

            await user_repo.save(user)

    await callback.answer("✅ Progress qayta boshlandi!", show_alert=True)
    await settings_learning(callback, db_user)
