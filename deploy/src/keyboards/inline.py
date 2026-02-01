"""
Keyboard builders - Inline and Reply keyboards
DINAMIK TUGMALAR VERSIYASI - ButtonTextService bilan
"""
from typing import List, Optional, Dict, Any
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from src.services.button_service import ButtonTextService


# ============================================================
# MAIN MENU KEYBOARDS
# ============================================================

async def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard with dynamic button texts"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_quiz_start"),
            callback_data="quiz:start"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_flashcards"),
            callback_data="flashcard:menu"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_duel"),
            callback_data="duel:menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament"),
            callback_data="tournament:menu"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_stats"),
            callback_data="stats:menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_streak"),
            callback_data="streak:info"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_achievements"),
            callback_data="achievements:menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_shop"),
            callback_data="shop:menu"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_premium"),
            callback_data="premium:menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_settings"),
            callback_data="settings:menu"
        )
    )

    return builder.as_markup()


async def onboarding_keyboard() -> InlineKeyboardMarkup:
    """Onboarding keyboard for new users"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_start_guide"),
            callback_data="onboard:guide"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_start_a1") + " (Tavsiya)",
            callback_data="onboard:start_a1"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_level_test"),
            callback_data="onboard:level_test"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_choose_myself"),
            callback_data="quiz:start"
        )
    )

    return builder.as_markup()


async def onboarding_guide_keyboard() -> InlineKeyboardMarkup:
    """Guide step keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_start_a1"),
            callback_data="onboard:start_a1"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="onboard:menu"
        )
    )

    return builder.as_markup()


def learning_path_keyboard(current_level: str = None) -> InlineKeyboardMarkup:
    """Learning path progress keyboard"""
    builder = InlineKeyboardBuilder()

    levels = ["A1", "A2", "B1", "B2", "C1", "C2"]

    for level in levels:
        if current_level and level == current_level:
            text = f"📍 {level} (Hozirgi)"
        else:
            text = f"📚 {level}"
        builder.row(
            InlineKeyboardButton(text=text, callback_data=f"onboard:level:{level}")
        )

    builder.row(
        InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="menu:main")
    )

    return builder.as_markup()


async def back_button(callback_data: str = "menu:main") -> InlineKeyboardMarkup:
    """Simple back button"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=await ButtonTextService.get("btn_back"),
        callback_data=callback_data
    ))
    return builder.as_markup()


# ============================================================
# QUIZ KEYBOARDS
# ============================================================

async def language_keyboard(languages: List[Dict]) -> InlineKeyboardMarkup:
    """Language selection keyboard"""
    builder = InlineKeyboardBuilder()

    for lang in languages:
        builder.row(
            InlineKeyboardButton(
                text=f"{lang['flag']} {lang['name']} ({lang['levels_count']} daraja)",
                callback_data=f"quiz:lang:{lang['id']}"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


async def level_keyboard(levels: List[Dict], language_id: int = None) -> InlineKeyboardMarkup:
    """Level selection keyboard"""
    builder = InlineKeyboardBuilder()

    for level in levels:
        premium_mark = "⭐ " if level.get("is_premium") else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{premium_mark}{level['name']} ({level['questions_count']} savol)",
                callback_data=f"quiz:level:{level['id']}"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


async def day_keyboard(
    days: List[Dict],
    language_id: int = None,
    level_id: Optional[int] = None,
    include_all: bool = True
) -> InlineKeyboardMarkup:
    """
    Day/Topic selection keyboard - mavzu nomlari bilan

    Args:
        days: Kunlar/mavzular ro'yxati
        language_id: Til ID (deprecated, not used)
        level_id: Daraja ID (barcha mavzular uchun)
        include_all: "Barcha mavzular" tugmasini ko'rsatish
    """
    builder = InlineKeyboardBuilder()

    # "Barcha mavzular" tugmasi (agar level_id berilgan bo'lsa)
    if include_all and level_id is not None:
        total_questions = sum(d.get("questions_count", 0) for d in days)
        all_topics_text = await ButtonTextService.get("btn_all_topics")
        builder.row(
            InlineKeyboardButton(
                text=f"{all_topics_text} ({total_questions} savol)",
                callback_data=f"quiz:day:all:{level_id}"
            )
        )

    # Mavzularni alohida qatorlarda ko'rsatish (topic nomi bilan)
    for day in days:
        premium_mark = "⭐ " if day.get("is_premium") else ""
        # Mavzu nomi yoki topic yoki "Kun X" formatida
        topic_name = day.get("topic") or day.get("name") or f"Kun {day['number']}"
        questions_count = day.get("questions_count", 0)

        # Uzun nomlarni qisqartirish
        if len(topic_name) > 25:
            topic_name = topic_name[:22] + "..."

        btn_text = f"{premium_mark}{topic_name} ({questions_count})"

        builder.row(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"quiz:day:{day['id']}"
            )
        )

    # Orqaga tugmasi - Level tanlash sahifasiga qaytish
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="quiz:start"
        )
    )

    return builder.as_markup()


async def question_count_keyboard(
    max_questions: int = 100,
    day_id: Optional[int] = None,
    level_id: Optional[int] = None,
    back_callback: str = "quiz:start"
) -> InlineKeyboardMarkup:
    """Question count selection keyboard"""
    builder = InlineKeyboardBuilder()

    # Standard counts
    counts = [5, 10, 15, 20, 50, 100]

    for count in counts:
        if count <= max_questions:
            builder.button(
                text=f"📝 {count} ta",
                callback_data=f"quiz:count:{count}"
            )

    builder.adjust(2)  # 2 buttons per row

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data=back_callback
        )
    )

    return builder.as_markup()


async def quiz_control_keyboard(
    question_id: int,
    show_audio: bool = False
) -> InlineKeyboardMarkup:
    """Quiz control buttons (audio, skip, cancel)"""
    builder = InlineKeyboardBuilder()

    if show_audio:
        builder.add(
            InlineKeyboardButton(
                text=await ButtonTextService.get("btn_listen_audio"),
                callback_data=f"quiz:audio:{question_id}"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_skip_question"),
            callback_data="quiz:skip"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_cancel"),
            callback_data="quiz:cancel"
        )
    )

    return builder.as_markup()


async def quiz_result_keyboard(
    show_review: bool = True,
    day_id: Optional[int] = None
) -> InlineKeyboardMarkup:
    """Quiz result actions keyboard"""
    builder = InlineKeyboardBuilder()

    if show_review:
        builder.row(
            InlineKeyboardButton(
                text=await ButtonTextService.get("btn_review_errors"),
                callback_data="quiz:review"
            )
        )

    if day_id:
        builder.row(
            InlineKeyboardButton(
                text=await ButtonTextService.get("btn_retry_quiz"),
                callback_data=f"quiz:retry:{day_id}"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_another_quiz"),
            callback_data="quiz:start"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_main_menu"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


def question_vote_keyboard(
    question_id: int,
    current_vote: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Question voting keyboard"""
    builder = InlineKeyboardBuilder()

    up_text = "👍" + (" ✓" if current_vote == "up" else "")
    down_text = "👎" + (" ✓" if current_vote == "down" else "")

    builder.row(
        InlineKeyboardButton(text=up_text, callback_data=f"vote:up:{question_id}"),
        InlineKeyboardButton(text=down_text, callback_data=f"vote:down:{question_id}")
    )

    return builder.as_markup()


# ============================================================
# PREMIUM KEYBOARDS
# ============================================================

async def premium_menu_keyboard(is_premium: bool = False) -> InlineKeyboardMarkup:
    """Premium menu keyboard"""
    builder = InlineKeyboardBuilder()

    if is_premium:
        builder.row(
            InlineKeyboardButton(text="✅ Sizda Premium mavjud!", callback_data="premium:status")
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="⭐ 1 oy - 100 yulduz",
                callback_data="premium:buy:monthly"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⭐ 1 yil - 1000 yulduz (40% chegirma!)",
                callback_data="premium:buy:yearly"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="💎 Lifetime - 5000 yulduz",
                callback_data="premium:buy:lifetime"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_promo_code"),
            callback_data="premium:promo"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_referral"),
            callback_data="referral:menu"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


async def premium_features_keyboard() -> InlineKeyboardMarkup:
    """Premium features info keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_buy_premium"),
            callback_data="premium:menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


# ============================================================
# DUEL KEYBOARDS
# ============================================================

async def duel_menu_keyboard() -> InlineKeyboardMarkup:
    """Duel menu keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_random_opponent"),
            callback_data="duel:random"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_invite_friend"),
            callback_data="duel:invite"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_duel_stats"),
            callback_data="duel:stats"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


async def duel_challenge_keyboard(duel_id: int) -> InlineKeyboardMarkup:
    """Duel challenge accept/decline keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_accept"),
            callback_data=f"duel:accept:{duel_id}"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_decline"),
            callback_data=f"duel:decline:{duel_id}"
        )
    )

    return builder.as_markup()


# ============================================================
# FLASHCARD KEYBOARDS
# ============================================================

async def flashcard_menu_keyboard() -> InlineKeyboardMarkup:
    """Flashcard menu keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_start_learning"),
            callback_data="flashcard:start"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_decks"),
            callback_data="flashcard:decks"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_progress"),
            callback_data="flashcard:progress"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


async def flashcard_review_keyboard(card_id: int) -> InlineKeyboardMarkup:
    """Flashcard review keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_show_answer"),
            callback_data=f"flashcard:show:{card_id}"
        )
    )

    return builder.as_markup()


async def flashcard_answer_keyboard(card_id: int) -> InlineKeyboardMarkup:
    """Flashcard answer rating keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_knew"),
            callback_data=f"flashcard:knew:{card_id}"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_didnt_know"),
            callback_data=f"flashcard:didnt:{card_id}"
        )
    )

    return builder.as_markup()


# ============================================================
# SETTINGS KEYBOARDS
# ============================================================

async def settings_keyboard(settings_data: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Settings menu keyboard"""
    builder = InlineKeyboardBuilder()

    notif_status = "✅" if settings_data.get("notifications", True) else "❌"
    reminder_status = "✅" if settings_data.get("daily_reminder", True) else "❌"

    # O'rganish sozlamalari - eng muhimi
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_learning_settings"),
            callback_data="settings:learning"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_quiz_settings"),
            callback_data="quiz:settings"
        )
    )

    notif_text = await ButtonTextService.get("btn_notifications")
    reminder_text = await ButtonTextService.get("btn_reminders")

    builder.row(
        InlineKeyboardButton(
            text=f"{notif_status} {notif_text}",
            callback_data="settings:toggle:notifications"
        ),
        InlineKeyboardButton(
            text=f"{reminder_status} {reminder_text}",
            callback_data="settings:toggle:daily_reminder"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="menu:main"
        )
    )

    return builder.as_markup()


# ============================================================
# CHANNEL SUBSCRIPTION KEYBOARD
# ============================================================

async def channel_subscription_keyboard(
    channels: List[Any],
    check_callback: str = "check:subscription"
) -> InlineKeyboardMarkup:
    """Channel subscription keyboard"""
    builder = InlineKeyboardBuilder()

    for channel in channels:
        builder.row(
            InlineKeyboardButton(
                text=f"{channel.icon} {channel.title}",
                url=channel.url
            )
        )

    builder.row(
        InlineKeyboardButton(text="✅ Tekshirish", callback_data=check_callback)
    )

    return builder.as_markup()


# ============================================================
# CONFIRMATION KEYBOARDS
# ============================================================

async def confirm_keyboard(
    confirm_data: str,
    cancel_data: str = "menu:main",
    confirm_text: str = None,
    cancel_text: str = None
) -> InlineKeyboardMarkup:
    """Generic confirmation keyboard"""
    builder = InlineKeyboardBuilder()

    if confirm_text is None:
        confirm_text = await ButtonTextService.get("btn_confirm_yes")
    if cancel_text is None:
        cancel_text = await ButtonTextService.get("btn_confirm_no")

    builder.row(
        InlineKeyboardButton(text=confirm_text, callback_data=confirm_data),
        InlineKeyboardButton(text=cancel_text, callback_data=cancel_data)
    )

    return builder.as_markup()


# ============================================================
# PAGINATION KEYBOARD
# ============================================================

def pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """Pagination keyboard"""
    builder = InlineKeyboardBuilder()

    buttons = []

    if current_page > 1:
        buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"{callback_prefix}:{current_page - 1}"
            )
        )

    buttons.append(
        InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data="noop"
        )
    )

    if current_page < total_pages:
        buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"{callback_prefix}:{current_page + 1}"
            )
        )

    builder.row(*buttons)

    return builder.as_markup()


# Remove keyboard helper
def remove_keyboard() -> ReplyKeyboardRemove:
    """Remove reply keyboard"""
    return ReplyKeyboardRemove()
