"""
Start handler - /start command and onboarding
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from src.database import get_session
from src.database.models import User, Referral, ReferralStatus
from src.repositories import UserRepository, SubscriptionRepository
from src.keyboards.inline import (
    main_menu_keyboard,
    channel_subscription_keyboard,
    premium_features_keyboard,
    onboarding_keyboard,
    onboarding_guide_keyboard,
    learning_path_keyboard
)
from src.core.logging import get_logger
from src.config import settings

logger = get_logger(__name__)
router = Router(name="start")


@router.message(CommandStart(deep_link=True))
async def start_with_referral(
    message: Message,
    command: CommandObject,
    db_user: User
):
    """Handle /start with referral code"""
    referral_code = command.args
    
    if not referral_code:
        return await start_command(message, db_user)

    # Check if it's a payment deep link (from forwarded invoice)
    if referral_code.startswith("premium_"):
        plan_id = referral_code[8:]  # Remove "premium_" prefix
        from src.services import payment_service
        plan = payment_service.get_plan(plan_id)
        if plan:
            try:
                await payment_service.create_invoice(
                    chat_id=message.chat.id,
                    user_id=db_user.user_id,
                    plan_id=plan_id
                )
                return
            except Exception as e:
                logger.error(f"Deep link payment error: {e}")
                await message.answer(
                    "❌ To'lov yaratishda xatolik yuz berdi. Keyinroq urinib ko'ring."
                )
                return
        # Invalid plan - fall through to regular start

    # Check if it's a referral code
    if referral_code.startswith("ref_"):
        code = referral_code[4:]
        
        async with get_session() as session:
            user_repo = UserRepository(session)
            
            # Find referrer
            referrer = await user_repo.get_by_referral_code(code)
            
            if referrer and referrer.user_id != message.from_user.id:
                # Check if already referred
                if db_user.referred_by_id is None:
                    # Save referral
                    db_user.referred_by_id = referrer.user_id
                    await user_repo.save(db_user)
                    
                    # Create referral record
                    from sqlalchemy import select
                    from src.database.models import Referral
                    
                    existing = await session.execute(
                        select(Referral).where(
                            Referral.referred_id == message.from_user.id
                        )
                    )
                    
                    if not existing.scalar_one_or_none():
                        referral = Referral(
                            referrer_id=referrer.user_id,
                            referred_id=message.from_user.id,
                            referral_code=code,
                            status=ReferralStatus.PENDING,
                            required_quizzes=settings.REFERRAL_MIN_QUIZZES
                        )
                        session.add(referral)
                        await session.flush()  # get_session() auto-commits
                    
                    await message.answer(
                        f"🎉 Siz {referrer.full_name} orqali ro'yxatdan o'tdingiz!\n\n"
                        f"📚 {settings.REFERRAL_MIN_QUIZZES} ta quiz tugatganingizda "
                        f"ikkalangiz ham sovg'a olasiz!"
                    )
                    
                    logger.info(
                        "Referral registered",
                        referrer_id=referrer.user_id,
                        referred_id=message.from_user.id
                    )
    
    return await start_command(message, db_user)


@router.message(CommandStart())
async def start_command(message: Message, db_user: User, **kwargs):
    """Handle /start command"""
    from datetime import date

    # Check for required channels
    not_subscribed = kwargs.get("not_subscribed_channels", [])

    if not_subscribed:
        channels_text = "\n".join(
            f"• {ch.icon} {ch.title}"
            for ch in not_subscribed
        )

        await message.answer(
            f"👋 Assalomu alaykum, {db_user.full_name}!\n\n"
            f"📢 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
            f"{channels_text}",
            reply_markup=channel_subscription_keyboard(not_subscribed)
        )
        return

    # Kunlik progressni yangilash
    today = date.today()
    if db_user.last_learning_date != today:
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_user_id(db_user.user_id)
            if user:
                user.reset_daily_progress()
                await user_repo.save(user)
                db_user = user

    # Get streak info
    streak_count = 0
    if db_user.streak:
        streak_count = db_user.streak.current_streak

    # Birinchi marta kirganlar uchun - Onboarding
    if not db_user.onboarding_completed:
        await show_onboarding(message, db_user)
        return

    # Quick Start uchun ma'lumotlar
    level_name = ""
    if db_user.current_level_id:
        try:
            from src.services import quiz_service
            levels = await quiz_service.get_levels()
            for level in levels:
                if level["id"] == db_user.current_level_id:
                    level_name = level["name"]
                    break
        except Exception as e:
            # Level topilmasa kritik emas, faqat debug log
            logger.debug(f"Level lookup failed for user {db_user.user_id}: {e}")

    # Progress bar
    word_progress = db_user.daily_word_progress
    word_bar = _create_progress_bar(word_progress)
    quiz_progress = db_user.daily_quiz_progress
    quiz_bar = _create_progress_bar(quiz_progress)

    # Umumiy statistika
    total_answered = db_user.total_questions
    accuracy = round(db_user.total_correct / db_user.total_questions * 100, 1) if db_user.total_questions > 0 else 0

    # SM-2 statistikasi
    try:
        from src.repositories.spaced_rep_repo import SpacedRepetitionRepository
        async with get_session() as session:
            sr_repo = SpacedRepetitionRepository(session)
            sm2_stats = await sr_repo.get_user_stats(db_user.user_id)
    except Exception:
        sm2_stats = {"total": 0, "mastered": 0, "learning": 0, "due_today": 0, "accuracy": 0}

    # Maqsadga erishish xabari
    goal_message = ""
    if db_user.daily_goal_reached:
        goal_message = "\n🎉 <b>Bugungi maqsadga erishdingiz!</b>"
    else:
        remaining = db_user.daily_word_goal - db_user.words_learned_today
        goal_message = f"\n📝 Maqsadgacha: <b>{remaining}</b> ta so'z qoldi"

    # Takrorlash kerakmi?
    due_message = ""
    if sm2_stats["due_today"] > 0:
        due_message = f"\n🔄 <b>Bugun takrorlash:</b> {sm2_stats['due_today']} ta so'z"

    welcome_text = f"""
👋 <b>Xush kelibsiz, {db_user.full_name}!</b>

🔥 Streak: <b>{streak_count}</b> kun | 📊 Daraja: <b>{level_name or "Tanlanmagan"}</b>

<b>📈 Umumiy progress:</b>
├ 📚 O'rganilgan so'zlar: <b>{db_user.total_words_learned}</b>
├ 🎯 Jami quizlar: <b>{db_user.total_quizzes}</b>
├ ✅ To'g'ri javoblar: <b>{db_user.total_correct}</b>/{total_answered}
├ 🎯 Aniqlik: <b>{accuracy}%</b>
├ ✅ O'zlashtirilgan: <b>{sm2_stats['mastered']}</b> ta
└ 📝 O'rganilmoqda: <b>{sm2_stats['learning']}</b> ta

<b>📅 Bugungi progress:</b>
📝 So'zlar: {db_user.words_learned_today}/{db_user.daily_word_goal}
{word_bar} {word_progress:.0f}%

🎯 Quizlar: {db_user.quizzes_today}/{db_user.daily_quiz_goal}
{quiz_bar} {quiz_progress:.0f}%
{goal_message}{due_message}

Davom etamizmi? 👇
"""

    # Keyboard with Quick Start
    keyboard = _create_start_keyboard(db_user, level_name)

    await message.answer(welcome_text, reply_markup=keyboard)


def _create_progress_bar(percentage: float, length: int = 10) -> str:
    """Progress bar yaratish"""
    filled = int(percentage / 100 * length)
    empty = length - filled
    return "█" * filled + "░" * empty


def _create_start_keyboard(db_user: User, level_name: str):
    """Start sahifasi uchun keyboard"""
    builder = InlineKeyboardBuilder()

    # Quick Start tugmasi (agar sozlamalar mavjud bo'lsa)
    if db_user.has_learning_settings:
        builder.row(
            InlineKeyboardButton(
                text=f"▶️ Davom etish ({level_name} - {db_user.current_day_number}-kun)",
                callback_data="quick:start"
            )
        )

    # Asosiy tugmalar
    builder.row(
        InlineKeyboardButton(text="📚 So'z o'rganish", callback_data="learn:words"),
        InlineKeyboardButton(text="🎯 Quiz", callback_data="quiz:start")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Statistika", callback_data="stats:menu"),
        InlineKeyboardButton(text="🏆 Yutuqlar", callback_data="achievements:menu")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="settings:menu"),
        InlineKeyboardButton(text="👋 Chiqish", callback_data="session:end")
    )

    return builder.as_markup()


async def show_onboarding(message: Message, db_user: User):
    """Birinchi marta kirganlar uchun onboarding"""
    text = f"""
👋 <b>Xush kelibsiz, {db_user.full_name}!</b>

🎓 <b>Quiz Bot Pro</b> - til o'rganish uchun eng yaxshi bot!

Sizni til o'rganish sayohatingizda qo'llab-quvvatlaymiz.

<b>Boshlash uchun bir necha sozlama:</b>

1️⃣ O'rganish darajangizni tanlang
2️⃣ Kunlik maqsadingizni belgilang
3️⃣ O'rganishni boshlang!

Darajangizni tanlang 👇
"""

    builder = InlineKeyboardBuilder()

    level_icons = {"A1": "🟢", "A2": "🟡", "B1": "🔵", "B2": "🟣", "C1": "🟠", "C2": "🔴"}

    builder.row(
        InlineKeyboardButton(text="🟢 A1 - Boshlang'ich", callback_data="onboard:setup:A1"),
        InlineKeyboardButton(text="🟡 A2 - Elementar", callback_data="onboard:setup:A2")
    )
    builder.row(
        InlineKeyboardButton(text="🔵 B1 - O'rta", callback_data="onboard:setup:B1"),
        InlineKeyboardButton(text="🟣 B2 - Yuqori o'rta", callback_data="onboard:setup:B2")
    )
    builder.row(
        InlineKeyboardButton(text="🟠 C1 - Ilg'or", callback_data="onboard:setup:C1"),
        InlineKeyboardButton(text="🔴 C2 - Mutaxassis", callback_data="onboard:setup:C2")
    )
    builder.row(
        InlineKeyboardButton(text="❓ Qaysi darajani tanlashni bilmayman", callback_data="onboard:help_level")
    )

    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "onboard:help_level")
async def onboard_help_level(callback: CallbackQuery):
    """Daraja tanlashda yordam"""
    text = """
❓ <b>Qaysi darajani tanlash kerak?</b>

<b>🟢 A1 - Boshlang'ich</b>
• Hech narsa bilmayman
• Yangi boshlayman

<b>🟡 A2 - Elementar</b>
• Oddiy so'zlarni bilaman
• Salomlashish, o'zimni tanishtira olaman

<b>🔵 B1 - O'rta</b>
• Oddiy gaplar tuza olaman
• Kundalik mavzularda gaplasha olaman

<b>🟣 B2 - Yuqori o'rta</b>
• Erkin gaplasha olaman
• Murakkab matnlarni tushunaman

<b>💡 Tavsiya:</b>
Ishonchsiz bo'lsangiz, <b>A1</b> dan boshlang!
Keyinroq sozlamalardan o'zgartirishingiz mumkin.
"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🟢 A1 dan boshlash", callback_data="onboard:setup:A1")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="onboard:back")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "onboard:back")
async def onboard_back(callback: CallbackQuery, db_user: User):
    """Onboarding ga qaytish"""
    await callback.message.delete()
    # Re-send as new message
    await show_onboarding(callback.message, db_user)
    await callback.answer()


@router.callback_query(F.data.startswith("onboard:setup:"))
async def onboard_setup_level(callback: CallbackQuery, db_user: User):
    """Onboarding - daraja va maqsad sozlash"""
    level_name = callback.data.split(":")[-1]

    from src.services import quiz_service

    try:
        # Tilni olish (nemis)
        languages = await quiz_service.get_languages()
        german = None
        for lang in languages:
            if "german" in lang["name"].lower() or "nemis" in lang["name"].lower():
                german = lang
                break
        if not german and languages:
            german = languages[0]

        if not german:
            await callback.answer("❌ Tillar topilmadi!", show_alert=True)
            return

        # Darajani olish
        levels = await quiz_service.get_levels(german["id"])
        selected_level = None
        for level in levels:
            if level_name.upper() in level["name"].upper():
                selected_level = level
                break

        if not selected_level:
            await callback.answer("❌ Daraja topilmadi!", show_alert=True)
            return

        # Birinchi kunni olish
        days = await quiz_service.get_days(selected_level["id"])
        first_day_id = days[0]["id"] if days else None

        # Ma'lumotlarni saqlash
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_user_id(db_user.user_id)
            if user:
                user.current_language_id = german["id"]
                user.current_level_id = selected_level["id"]
                user.current_day_id = first_day_id
                user.current_day_number = 1
                user.onboarding_completed = True
                await user_repo.save(user)

        # Kunlik maqsad tanlash
        text = f"""
✅ <b>{level_name} darajasi tanlandi!</b>

Endi kunlik maqsadingizni belgilang.

<b>Har kuni nechta so'z o'rganmoqchisiz?</b>
"""

        builder = InlineKeyboardBuilder()
        goals = [
            ("10 ta so'z (Yengil)", 10),
            ("20 ta so'z (O'rtacha)", 20),
            ("30 ta so'z (Jadal)", 30),
            ("50 ta so'z (Intensiv)", 50),
        ]

        for label, value in goals:
            builder.row(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"onboard:goal:{value}"
                )
            )

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer(f"✅ {level_name} tanlandi!")

    except Exception as e:
        logger.error(f"Onboard setup error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)


@router.callback_query(F.data.startswith("onboard:goal:"))
async def onboard_set_goal(callback: CallbackQuery, db_user: User):
    """Kunlik maqsadni saqlash va yakunlash"""
    goal = int(callback.data.split(":")[-1])

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.daily_word_goal = goal
            await user_repo.save(user)

    text = f"""
🎉 <b>Ajoyib! Hammasi tayyor!</b>

✅ Daraja sozlandi
✅ Kunlik maqsad: <b>{goal}</b> ta so'z

<b>Endi nima qilasiz?</b>

📚 <b>So'z o'rganish</b> - yangi so'zlarni o'rganing
🎯 <b>Quiz</b> - bilimingizni tekshiring

Omad! 🍀
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 So'z o'rganishni boshlash", callback_data="learn:words")
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Quiz boshlash", callback_data="quick:start")
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:main")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer("🎉 Sozlamalar saqlandi!")


# =====================================================
# QUICK START - Tezkor boshlash
# =====================================================

@router.callback_query(F.data == "quick:start")
async def quick_start(callback: CallbackQuery, db_user: User, state: FSMContext):
    """Tezkor boshlash - saqlangan darajadan davom etish"""
    from src.services import quiz_service
    from src.handlers.quiz.personal import QuizStates

    if not db_user.has_learning_settings:
        await callback.answer("⚙️ Avval sozlamalarni bajaring!", show_alert=True)
        await show_onboarding(callback.message, db_user)
        return

    try:
        # Joriy daraja nomini olish
        level_name = ""
        levels = await quiz_service.get_levels()
        for level in levels:
            if level["id"] == db_user.current_level_id:
                level_name = level["name"]
                break

        # FSM state'ni o'rnatish - bu juda muhim!
        await state.clear()
        await state.set_state(QuizStates.selecting_count)

        # Kerakli ma'lumotlarni FSM state'ga saqlash
        await state.update_data(
            day_id=db_user.current_day_id,
            selected_level_id=db_user.current_level_id,
            all_days=False,
            is_premium=db_user.is_premium
        )

        # Quizga yo'naltirish (joriy kun bilan)
        from src.keyboards.inline import question_count_keyboard

        text = f"""
▶️ <b>Davom etish</b>

📊 Daraja: <b>{level_name}</b>
📅 Kun: <b>{db_user.current_day_number}</b>

🔢 Savollar sonini tanlang:
"""

        await callback.message.edit_text(
            text,
            reply_markup=question_count_keyboard(back_callback="menu:main")
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Quick start error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)


# =====================================================
# CHIQISH - Session yakunlash
# =====================================================

@router.callback_query(F.data == "session:end")
async def session_end(callback: CallbackQuery, db_user: User):
    """Sessiyani yakunlash va natijalarni ko'rsatish"""

    # Streak ma'lumotlari
    streak_count = 0
    if db_user.streak:
        streak_count = db_user.streak.current_streak

    # Bugungi yutuqlar
    achievements_today = []
    extra_message = ""

    # Maqsadga erishganmi?
    if db_user.daily_goal_reached:
        extra_message = "\n🎉 <b>Bugungi maqsadga erishdingiz! Ajoyib!</b>"
        achievements_today.append("🎯 Kunlik maqsad bajarildi")

    # Streak yutuqi
    if streak_count > 0 and streak_count % 7 == 0:
        achievements_today.append(f"🔥 {streak_count} kunlik streak!")

    # Yangi so'zlar
    if db_user.words_learned_today >= 10:
        achievements_today.append(f"📚 {db_user.words_learned_today} ta yangi so'z")

    achievements_text = ""
    if achievements_today:
        achievements_text = "\n\n<b>🏆 Bugungi yutuqlar:</b>\n" + "\n".join(f"• {a}" for a in achievements_today)

    # Keyingi sessiya uchun eslatma
    remaining_words = max(0, db_user.daily_word_goal - db_user.words_learned_today)
    remaining_quizzes = max(0, db_user.daily_quiz_goal - db_user.quizzes_today)

    next_session_text = ""
    if remaining_words > 0 or remaining_quizzes > 0:
        next_session_text = f"""

<b>📋 Keyingi safar:</b>
"""
        if remaining_words > 0:
            next_session_text += f"• 📝 {remaining_words} ta so'z o'rganish\n"
        if remaining_quizzes > 0:
            next_session_text += f"• 🎯 {remaining_quizzes} ta quiz yechish\n"

    text = f"""
👋 <b>Xayr, {db_user.full_name}!</b>

<b>Bugungi natijalar:</b>
├ 📝 O'rganilgan so'zlar: {db_user.words_learned_today}
├ 🎯 Yechilgan quizlar: {db_user.quizzes_today}
├ 🔥 Streak: {streak_count} kun
└ 📊 Umumiy so'zlar: {db_user.total_words_learned}
{extra_message}{achievements_text}{next_session_text}
<i>Ertaga yana kuting! Streak'ni yo'qotmang! 🌟</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="▶️ Davom etish", callback_data="quick:start")
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:main")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer("👋 Ko'rishguncha!")


@router.callback_query(F.data == "check:subscription")
async def check_subscription(callback: CallbackQuery, db_user: User, **kwargs):
    """Check subscription and show main menu"""
    not_subscribed = kwargs.get("not_subscribed_channels", [])
    
    if not_subscribed:
        await callback.answer(
            "❌ Siz hali barcha kanallarga obuna bo'lmadingiz!",
            show_alert=True
        )
        return
    
    await callback.message.edit_text(
        f"✅ Ajoyib! Endi botdan foydalanishingiz mumkin.\n\n"
        f"Quyidagi menyudan tanlang 👇",
        reply_markup=main_menu_keyboard()
    )


@router.message(Command("help"))
async def help_command(message: Message):
    """Help command"""
    help_text = """
📚 <b>Yordam</b>

<b>Asosiy buyruqlar:</b>
/start - Botni boshlash
/quiz - Quiz boshlash
/stats - Statistika
/streak - Streak ma'lumotlari
/premium - Premium obuna
/settings - Sozlamalar
/help - Yordam

<b>Premium afzalliklari:</b>
⭐ Premium savollar
⭐ Cheksiz quiz
⭐ Streak himoyasi
⭐ Audio talaffuz
⭐ Reklamsiz

Savollar bo'lsa: @admin_username
"""
    
    await message.answer(help_text, reply_markup=main_menu_keyboard())


@router.message(Command("premium"))
async def premium_command(message: Message, db_user: User, is_premium: bool):
    """Premium command"""
    if is_premium:
        text = """
⭐ <b>Sizda Premium obuna mavjud!</b>

✅ Barcha premium imkoniyatlardan foydalanishingiz mumkin.

Premium afzalliklari:
• 📚 Premium savollar
• 🔊 Audio talaffuz
• 🛡 Streak himoyasi
• ♾ Cheksiz quiz
"""
    else:
        text = """
⭐ <b>Premium obuna</b>

Premium afzalliklari:
• 📚 Premium savollar - qo'shimcha kontentga kirish
• 🔊 Audio talaffuz - to'g'ri talaffuzni tinglash
• 🛡 Streak himoyasi - 1 kun o'tkazib yuborish mumkin
• ♾ Cheksiz quiz - limitlarsiz o'rganish
• 📊 Batafsil statistika

<b>Narxlar:</b>
⭐ 1 oy - 100 yulduz
⭐ 1 yil - 1000 yulduz (40% chegirma!)
💎 Lifetime - 5000 yulduz
"""
    
    from src.keyboards.inline import premium_menu_keyboard
    await message.answer(text, reply_markup=premium_menu_keyboard(is_premium))


@router.message(Command("quiz"))
async def quiz_command(message: Message):
    """Quiz boshlash"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Quiz boshlash", callback_data="quiz:start"))
    builder.row(InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main"))
    
    await message.answer(
        "📚 <b>Quiz</b>\n\n"
        "Til o'rganish quizini boshlash uchun tugmani bosing:",
        reply_markup=builder.as_markup()
    )


@router.message(Command("stats"))
async def stats_command(message: Message):
    """Statistika ko'rsatish"""
    user_id = message.from_user.id
    
    from src.database import get_session
    from src.repositories import UserRepository
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(user_id)
    
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi!")
        return
    
    # SM-2 statistikasi
    try:
        from src.repositories.spaced_rep_repo import SpacedRepetitionRepository
        async with get_session() as session:
            sr_repo = SpacedRepetitionRepository(session)
            sm2_stats = await sr_repo.get_user_stats(user_id)
    except Exception as e:
        logger.debug(f"SM-2 stats error: {e}")
        sm2_stats = {"total": 0, "mastered": 0, "learning": 0, "due_today": 0, "accuracy": 0}
    
    # Hisoblash
    total_answered = user.total_correct + (user.total_questions - user.total_correct)
    accuracy = round(user.total_correct / user.total_questions * 100, 1) if user.total_questions > 0 else 0
    
    text = f"""
📊 <b>Sizning statistikangiz</b>

👤 <b>Umumiy:</b>
├ 📝 Quizlar: {user.total_quizzes}
├ ✅ To'g'ri javoblar: {user.total_correct}
├ 📊 Jami savollar: {user.total_questions}
├ 🎯 Aniqlik: {accuracy}%
└ 💎 Premium: {'Ha' if user.is_premium else "Yo'q"}

📚 <b>O'rganish (SM-2):</b>
├ 📖 Jami savollar: {sm2_stats['total']}
├ ✅ O'zlashtirilgan: {sm2_stats['mastered']}
├ 📝 O'rganilmoqda: {sm2_stats['learning']}
├ 🔄 Bugun takrorlash: {sm2_stats['due_today']}
└ 🎯 Aniqlik: {sm2_stats['accuracy']}%
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Quiz", callback_data="quiz:start"))
    builder.row(InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main"))
    
    await message.answer(text, reply_markup=builder.as_markup())


# ============================================================
# ONBOARDING HANDLERS
# ============================================================

@router.callback_query(F.data == "onboard:menu")
async def onboard_menu(callback: CallbackQuery, db_user: User):
    """Show onboarding menu"""
    welcome_text = f"""
👋 <b>Xush kelibsiz, {db_user.full_name}!</b>

🎓 <b>Quiz Bot Pro</b> - nemis tilini o'rganish uchun eng yaxshi bot!

📚 <b>O'rganish yo'li:</b>
┌─ 🟢 <b>A1</b> - Boshlang'ich (Boshlovchilar uchun)
├─ 🟡 <b>A2</b> - Elementar
├─ 🔵 <b>B1</b> - O'rta
├─ 🟣 <b>B2</b> - Yuqori o'rta
├─ 🟠 <b>C1</b> - Ilg'or
└─ 🔴 <b>C2</b> - Mutaxassis

💡 <b>Tavsiya:</b> A1 dan boshlang va har kuni kamida 1 ta quiz yeching!

Qayerdan boshlaysiz? 👇
"""
    await callback.message.edit_text(
        welcome_text,
        reply_markup=onboarding_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "onboard:guide")
async def onboard_guide(callback: CallbackQuery):
    """Show learning guide"""
    guide_text = """
📖 <b>O'rganish yo'riqnomasi</b>

<b>1️⃣ Daraja tanlang:</b>
   Boshlang'ich bo'lsangiz → <b>A1</b>
   Biroz bilsangiz → <b>A2</b> yoki <b>B1</b>

<b>2️⃣ Kun/Mavzu tanlang:</b>
   Har bir daraja 30-70 kungacha bo'lingan
   Har kuni yangi mavzu bor

<b>3️⃣ Quiz yeching:</b>
   5, 10, 15 yoki 20 ta savol tanlang
   Har bir to'g'ri javob uchun ball olasiz

<b>4️⃣ Takrorlang:</b>
   🃏 Flashcards - so'zlarni eslab qolish
   🔄 SM-2 tizimi avtomatik takrorlash

<b>5️⃣ Raqobatlashing:</b>
   ⚔️ Duel - do'stlar bilan bellashish
   🏆 Turnir - haftalik musobaqalar

<b>💡 Maslahat:</b>
Har kuni 15-30 daqiqa o'rganing va
🔥 streak ni yo'qotmang!
"""
    await callback.message.edit_text(
        guide_text,
        reply_markup=onboarding_guide_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "onboard:start_a1")
async def onboard_start_a1(callback: CallbackQuery, state: FSMContext):
    """Start from A1 level - redirect to quiz with A1"""
    from src.services import quiz_service

    try:
        languages = await quiz_service.get_languages()

        # Find German (or first language)
        german = None
        for lang in languages:
            if "german" in lang["name"].lower() or "nemis" in lang["name"].lower():
                german = lang
                break

        if not german and languages:
            german = languages[0]

        if german:
            # Get levels for this language
            levels = await quiz_service.get_levels(german["id"])

            # Find A1 level
            a1_level = None
            for level in levels:
                if "A1" in level["name"].upper():
                    a1_level = level
                    break

            if a1_level:
                # Redirect to A1 days selection
                from src.keyboards.inline import day_keyboard
                days = await quiz_service.get_days(a1_level["id"])

                # Set state for quiz flow
                from src.handlers.quiz.personal import QuizStates
                await state.set_state(QuizStates.selecting_day)
                await state.update_data(language_id=german["id"], level_id=a1_level["id"])

                text = f"""
🎯 <b>{german['flag']} {german['name']} - {a1_level['name']}</b>

📚 Kunni tanlang (1-kundan boshlash tavsiya etiladi):

💡 Har bir kun yangi mavzuni o'z ichiga oladi.
Ketma-ket o'rganish eng yaxshi natija beradi!
"""
                await callback.message.edit_text(
                    text,
                    reply_markup=day_keyboard(days, level_id=a1_level["id"])
                )
                await callback.answer("🎯 A1 darajasi tanlandi!")
                return

        # No languages or levels found
        await callback.answer("❌ Tillar yoki darajalar topilmadi!", show_alert=True)

    except Exception as e:
        logger.error(f"Onboard start A1 error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)


@router.callback_query(F.data == "onboard:level_test")
async def onboard_level_test(callback: CallbackQuery):
    """Show level test info"""
    text = """
📊 <b>Darajangizni aniqlash</b>

Hozircha avtomatik test mavjud emas.

<b>O'zingiz baholang:</b>

🟢 <b>A1</b> - Hech narsa bilmayman
🟡 <b>A2</b> - Oddiy so'zlar va iboralarni bilaman
🔵 <b>B1</b> - Oddiy gaplar tuza olaman
🟣 <b>B2</b> - Erkin muloqot qila olaman

💡 Ishonchsiz bo'lsangiz, <b>A1</b> dan boshlang!
"""
    await callback.message.edit_text(
        text,
        reply_markup=learning_path_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("onboard:level:"))
async def onboard_select_level(callback: CallbackQuery, state: FSMContext):
    """Handle level selection from onboarding"""
    level_name = callback.data.split(":")[-1]  # A1, A2, B1, etc.

    from src.services import quiz_service

    try:
        languages = await quiz_service.get_languages()

        # Find German (or first language)
        german = None
        for lang in languages:
            if "german" in lang["name"].lower() or "nemis" in lang["name"].lower():
                german = lang
                break

        if not german and languages:
            german = languages[0]

        if german:
            levels = await quiz_service.get_levels(german["id"])

            # Find selected level
            selected_level = None
            for level in levels:
                if level_name.upper() in level["name"].upper():
                    selected_level = level
                    break

            if selected_level:
                from src.keyboards.inline import day_keyboard
                days = await quiz_service.get_days(selected_level["id"])

                # Set state for quiz flow
                from src.handlers.quiz.personal import QuizStates
                await state.set_state(QuizStates.selecting_day)
                await state.update_data(language_id=german["id"], level_id=selected_level["id"])

                text = f"""
🎯 <b>{german['flag']} {german['name']} - {selected_level['name']}</b>

📚 Kunni tanlang:

💡 1-kundan ketma-ket o'rganish tavsiya etiladi!
"""
                await callback.message.edit_text(
                    text,
                    reply_markup=day_keyboard(days, level_id=selected_level["id"])
                )
                await callback.answer(f"📚 {level_name} darajasi tanlandi!")
                return

        await callback.answer("Daraja topilmadi", show_alert=True)

    except Exception as e:
        logger.error(f"Onboard select level error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)
