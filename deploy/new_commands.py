

# ==================== MAVZULAR BOSHQARUVI ====================

@router.message(Command("topics"))
async def list_topics(message: Message):
    """Barcha mavzularni ko'rsatish"""
    if not await is_admin_async(message.from_user.id):
        return

    args = message.text.split()

    async with get_session() as session:
        lang_repo = LanguageRepository(session)

        if len(args) >= 2:
            level_name = args[1].upper()
            result = await session.execute(
                select(Level).where(Level.name == level_name)
            )
            level = result.scalar_one_or_none()

            if not level:
                await message.answer(f"<b>{level_name}</b> darajasi topilmadi!", parse_mode="HTML")
                return

            result = await session.execute(
                select(Day).where(Day.level_id == level.id).order_by(Day.day_number)
            )
            days = result.scalars().all()

            lang = await lang_repo.get_by_id(level.language_id)
            text = f"<b>{lang.name} - {level.name} MAVZULARI</b>\n\n"

            for day in days:
                q_count = len([q for q in day.questions if q.is_active]) if day.questions else 0
                name = day.name or f"Kun {day.day_number}"
                text += f"<code>{day.id}</code> - {name} ({q_count} savol)\n"

            text += f"\nJami: {len(days)} mavzu"
            text += f"\n\nYangi mavzu: <code>/add_topic {level.name} Mavzu nomi</code>"
            text += f"\nImport: <code>/import [ID]</code>"

        else:
            result = await session.execute(select(Language).where(Language.is_active == True))
            languages = result.scalars().all()

            text = "<b>BARCHA MAVZULAR</b>\n"

            for lang in languages:
                result = await session.execute(
                    select(Level).where(Level.language_id == lang.id).order_by(Level.display_order)
                )
                levels = result.scalars().all()

                for level in levels:
                    result = await session.execute(
                        select(Day).where(Day.level_id == level.id).order_by(Day.day_number)
                    )
                    days = result.scalars().all()

                    if days:
                        text += f"\n<b>{lang.name} - {level.name}</b>\n"
                        for day in days:
                            q_count = len([q for q in day.questions if q.is_active]) if day.questions else 0
                            name = day.name or f"Kun {day.day_number}"
                            text += f"  <code>{day.id}</code> - {name} ({q_count})\n"

            text += f"\nBatafsil: <code>/topics A1</code>"
            text += f"\nYangi daraja: <code>/add_level de B1</code>"

        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await message.answer(text[i:i+4000], parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")


@router.message(Command("add_topic"))
async def add_topic_cmd(message: Message):
    """Yangi mavzu qo'shish: /add_topic A1 Salomlashish va xayrlashish"""
    if not await is_admin_async(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Format: <code>/add_topic [daraja] [mavzu nomi]</code>\n"
            "Masalan: <code>/add_topic A1 Salomlashish va xayrlashish</code>",
            parse_mode="HTML"
        )
        return

    level_name = parts[1].upper()
    topic_name = parts[2].strip()

    async with get_session() as session:
        result = await session.execute(
            select(Level).where(Level.name == level_name)
        )
        level = result.scalar_one_or_none()

        if not level:
            await message.answer(f"<b>{level_name}</b> darajasi topilmadi!", parse_mode="HTML")
            return

        result = await session.execute(
            select(Day).where(Day.level_id == level.id).order_by(Day.day_number.desc())
        )
        last_day = result.scalars().first()
        next_number = (last_day.day_number + 1) if last_day else 1

        new_day = Day(
            level_id=level.id,
            day_number=next_number,
            name=topic_name,
            topic=topic_name,
            is_active=True
        )
        session.add(new_day)
        await session.commit()
        await session.refresh(new_day)

        await message.answer(
            f"Yangi mavzu yaratildi!\n\n"
            f"<b>{level.name} - {topic_name}</b>\n"
            f"ID: <code>{new_day.id}</code>\n\n"
            f"Savol yuklash: <code>/import {new_day.id}</code>",
            parse_mode="HTML"
        )


@router.message(Command("add_level"))
async def add_level_text_cmd(message: Message):
    """Yangi daraja qo'shish: /add_level de A2"""
    if not await is_admin_async(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "Format: <code>/add_level [til] [daraja]</code>\n"
            "Masalan: <code>/add_level de A2</code>",
            parse_mode="HTML"
        )
        return

    lang_code = parts[1].lower()
    level_name = parts[2].upper()

    async with get_session() as session:
        result = await session.execute(
            select(Language).where(Language.code == lang_code)
        )
        language = result.scalar_one_or_none()

        if not language:
            await message.answer(f"<b>{lang_code}</b> tili topilmadi!", parse_mode="HTML")
            return

        result = await session.execute(
            select(Level).where(Level.language_id == language.id, Level.name == level_name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            await message.answer(f"<b>{level_name}</b> allaqachon mavjud (ID: {existing.id})", parse_mode="HTML")
            return

        result = await session.execute(
            select(Level).where(Level.language_id == language.id).order_by(Level.display_order.desc())
        )
        last_level = result.scalars().first()
        next_order = (last_level.display_order + 1) if last_level else 1

        new_level = Level(
            language_id=language.id,
            name=level_name,
            display_order=next_order,
            is_active=True
        )
        session.add(new_level)
        await session.commit()
        await session.refresh(new_level)

        await message.answer(
            f"Yangi daraja yaratildi!\n\n"
            f"<b>{language.name} - {level_name}</b>\n"
            f"ID: <code>{new_level.id}</code>\n\n"
            f"Mavzu qo'shish: <code>/add_topic {level_name} Mavzu nomi</code>",
            parse_mode="HTML"
        )


@router.message(Command("rename_topic"))
async def rename_topic_cmd(message: Message):
    """Mavzu nomini o'zgartirish: /rename_topic 3 Yangi nom"""
    if not await is_admin_async(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Format: <code>/rename_topic [ID] [yangi nom]</code>\n"
            "Masalan: <code>/rename_topic 3 Salomlashish</code>",
            parse_mode="HTML"
        )
        return

    try:
        day_id = int(parts[1])
    except ValueError:
        await message.answer("ID raqam bo'lishi kerak!")
        return

    new_name = parts[2].strip()

    async with get_session() as session:
        result = await session.execute(select(Day).where(Day.id == day_id))
        day = result.scalar_one_or_none()

        if not day:
            await message.answer(f"ID={day_id} mavzu topilmadi!")
            return

        old_name = day.name or f"Kun {day.day_number}"
        day.name = new_name
        day.topic = new_name
        await session.commit()

        await message.answer(
            f"Mavzu nomi o'zgartirildi!\n\n"
            f"<b>{old_name}</b> -> <b>{new_name}</b>\n"
            f"ID: <code>{day_id}</code>",
            parse_mode="HTML"
        )
