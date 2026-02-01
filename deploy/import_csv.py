"""
CSV Import Script - Unified Vocabulary System

CSV formatidan ma'lumotlarni import qiladi:
1. Vocabulary jadvaliga so'zni qo'shadi
2. Questions jadvaliga savolni qo'shadi (vocabulary_id bilan)
3. Flashcards jadvaliga kartani qo'shadi (vocabulary_id bilan)

CSV format:
savol,javob,izoh,variant_a,variant_b,variant_c,variant_d,togri_javob,daraja,kun,gender,turi,audio_url
"""
import asyncio
import csv
import sys
sys.path.insert(0, '/app')

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:quiz_secure_2024@postgres:5432/quiz_bot"

# CSV fayl nomi (argument sifatida beriladi yoki default)
CSV_FILE = sys.argv[1] if len(sys.argv) > 1 else "/app/data/import.csv"


async def get_or_create_day(session, level_id: int, day_number: int) -> int:
    """Day ID ni olish yoki yaratish"""
    result = await session.execute(text("""
        SELECT id FROM days
        WHERE level_id = :level_id AND day_number = :day_number
        LIMIT 1
    """), {"level_id": level_id, "day_number": day_number})
    day_id = result.scalar()

    if day_id:
        return day_id

    # Yaratish
    result = await session.execute(text("""
        INSERT INTO days (level_id, day_number, title, is_active)
        VALUES (:level_id, :day_number, :title, true)
        RETURNING id
    """), {
        "level_id": level_id,
        "day_number": day_number,
        "title": f"{day_number}-kun"
    })
    return result.scalar()


async def get_deck_id(session, level_id: int) -> int:
    """Level uchun deck ID ni olish"""
    level_names = {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1", 6: "C2", 7: "PREMIUM"}
    deck_name = f"📚 {level_names.get(level_id, 'A1')} - Quiz so'zlari"

    result = await session.execute(text("""
        SELECT id FROM flashcard_decks
        WHERE name = :name AND level_id = :level_id
        LIMIT 1
    """), {"name": deck_name, "level_id": level_id})
    deck_id = result.scalar()

    if deck_id:
        return deck_id

    # Yaratish
    result = await session.execute(text("""
        INSERT INTO flashcard_decks
        (name, level_id, is_public, is_premium, icon, price, cards_count, users_studying, display_order, is_active)
        VALUES (:name, :level_id, true, false, '📚', 0, 0, 0, :level_id, true)
        RETURNING id
    """), {"name": deck_name, "level_id": level_id})
    return result.scalar()


async def import_csv():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("=" * 60)
        print("CSV IMPORT - UNIFIED VOCABULARY SYSTEM")
        print("=" * 60)
        print(f"CSV fayl: {CSV_FILE}")

        # CSV ni o'qish
        try:
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            print(f"XATO: {CSV_FILE} fayl topilmadi!")
            return
        except Exception as e:
            print(f"XATO: CSV o'qishda xatolik: {e}")
            return

        print(f"Topilgan qatorlar: {len(rows)}")

        # Statistika
        stats = {
            "vocabulary_added": 0,
            "vocabulary_exists": 0,
            "questions_added": 0,
            "flashcards_added": 0,
            "errors": 0
        }

        for i, row in enumerate(rows, 1):
            try:
                # CSV ustunlarini olish
                savol = row.get('savol', '').strip()
                javob = row.get('javob', '').strip()
                izoh = row.get('izoh', '').strip()
                variant_a = row.get('variant_a', '').strip()
                variant_b = row.get('variant_b', '').strip()
                variant_c = row.get('variant_c', '').strip()
                variant_d = row.get('variant_d', '').strip()
                togri_javob = row.get('togri_javob', 'A').strip().upper()
                daraja = int(row.get('daraja', 1) or 1)
                kun = int(row.get('kun', 1) or 1)
                gender = row.get('gender', '-').strip()
                turi = row.get('turi', 'noun').strip()
                audio_url = row.get('audio_url', '').strip() or None

                if not savol or not javob:
                    print(f"  [{i}] SKIP: Bo'sh savol yoki javob")
                    continue

                # Gender ni tozalash
                if gender in ['-', '', 'none', 'None']:
                    gender = None

                # 1. Day ID olish
                day_id = await get_or_create_day(session, daraja, kun)

                # 2. Vocabulary ga qo'shish (agar mavjud bo'lmasa)
                result = await session.execute(text("""
                    SELECT id FROM vocabulary
                    WHERE word = :word AND level_id = :level_id
                    LIMIT 1
                """), {"word": savol, "level_id": daraja})
                vocab_id = result.scalar()

                if vocab_id:
                    stats["vocabulary_exists"] += 1
                else:
                    # Yangi so'z qo'shish
                    result = await session.execute(text("""
                        INSERT INTO vocabulary
                        (word, translation, gender, part_of_speech, example_de, example_uz,
                         level_id, day_id, difficulty, audio_url, is_active)
                        VALUES
                        (:word, :translation, :gender, :part_of_speech, :example_de, :example_uz,
                         :level_id, :day_id, :difficulty, :audio_url, true)
                        RETURNING id
                    """), {
                        "word": savol,
                        "translation": javob,
                        "gender": gender,
                        "part_of_speech": turi,
                        "example_de": izoh,
                        "example_uz": None,
                        "level_id": daraja,
                        "day_id": day_id,
                        "difficulty": 3,
                        "audio_url": audio_url
                    })
                    vocab_id = result.scalar()
                    stats["vocabulary_added"] += 1

                # 3. Questions ga qo'shish (agar mavjud bo'lmasa)
                result = await session.execute(text("""
                    SELECT id FROM questions
                    WHERE vocabulary_id = :vocab_id
                    LIMIT 1
                """), {"vocab_id": vocab_id})
                question_exists = result.scalar()

                if not question_exists:
                    await session.execute(text("""
                        INSERT INTO questions
                        (question_text, option_a, option_b, option_c, option_d, correct_option,
                         explanation, day_id, vocabulary_id, audio_url, is_active)
                        VALUES
                        (:question_text, :option_a, :option_b, :option_c, :option_d, :correct_option,
                         :explanation, :day_id, :vocabulary_id, :audio_url, true)
                    """), {
                        "question_text": savol,
                        "option_a": variant_a,
                        "option_b": variant_b,
                        "option_c": variant_c,
                        "option_d": variant_d,
                        "correct_option": togri_javob,
                        "explanation": izoh,
                        "day_id": day_id,
                        "vocabulary_id": vocab_id,
                        "audio_url": audio_url
                    })
                    stats["questions_added"] += 1

                # 4. Flashcards ga qo'shish (agar mavjud bo'lmasa)
                result = await session.execute(text("""
                    SELECT id FROM flashcards
                    WHERE vocabulary_id = :vocab_id
                    LIMIT 1
                """), {"vocab_id": vocab_id})
                flashcard_exists = result.scalar()

                if not flashcard_exists:
                    deck_id = await get_deck_id(session, daraja)

                    await session.execute(text("""
                        INSERT INTO flashcards
                        (deck_id, vocabulary_id, front_text, back_text, front_audio_url,
                         example_sentence, display_order, times_shown, times_known, is_active)
                        VALUES
                        (:deck_id, :vocabulary_id, :front_text, :back_text, :audio_url,
                         :example, 0, 0, 0, true)
                    """), {
                        "deck_id": deck_id,
                        "vocabulary_id": vocab_id,
                        "front_text": savol,
                        "back_text": javob,
                        "audio_url": audio_url,
                        "example": izoh
                    })
                    stats["flashcards_added"] += 1

                # Har 50 ta qatordan keyin commit
                if i % 50 == 0:
                    await session.commit()
                    print(f"  [{i}/{len(rows)}] Jarayonda...")

            except Exception as e:
                print(f"  [{i}] XATO: {e}")
                stats["errors"] += 1
                continue

        # Oxirgi commit
        await session.commit()

        # Deck card_count ni yangilash
        print("\nDeck statistikalarini yangilash...")
        await session.execute(text("""
            UPDATE flashcard_decks fd
            SET cards_count = (
                SELECT COUNT(*) FROM flashcards f WHERE f.deck_id = fd.id
            )
        """))
        await session.commit()

        # Natijalar
        print("\n" + "=" * 60)
        print("IMPORT YAKUNLANDI!")
        print("=" * 60)
        print(f"  Vocabulary:")
        print(f"    - Yangi qo'shildi: {stats['vocabulary_added']}")
        print(f"    - Mavjud edi: {stats['vocabulary_exists']}")
        print(f"  Questions qo'shildi: {stats['questions_added']}")
        print(f"  Flashcards qo'shildi: {stats['flashcards_added']}")
        print(f"  Xatolar: {stats['errors']}")

        # Umumiy statistika
        print("\n" + "-" * 60)
        print("UMUMIY BAZADAGI MA'LUMOTLAR:")

        result = await session.execute(text("SELECT COUNT(*) FROM vocabulary"))
        print(f"  Vocabulary: {result.scalar()}")

        result = await session.execute(text("SELECT COUNT(*) FROM questions"))
        print(f"  Questions: {result.scalar()}")

        result = await session.execute(text("SELECT COUNT(*) FROM flashcards"))
        print(f"  Flashcards: {result.scalar()}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(import_csv())
