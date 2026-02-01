"""
Create flashcards for words that don't have them.
"""
import asyncio
import re
import sys
sys.path.insert(0, '/app')

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:quiz_secure_2024@postgres:5432/quiz_bot"


def clean_word(question_text: str) -> str:
    """
    Clean question text to extract just the word.
    Examples:
    - "'hello' so'zining tarjimasi nima?" -> "hello"
    - "der Hund" -> "der Hund"
    - "'die Katze, -n' so'zining..." -> "die Katze, -n"
    """
    # Remove "so'zining tarjimasi nima?" pattern
    patterns = [
        r"['\"](.+?)['\"] so'zining tarjimasi nima\?",
        r"(.+?) so'zining tarjimasi nima\?",
        r"['\"](.+?)['\"]",
    ]

    for pattern in patterns:
        match = re.search(pattern, question_text)
        if match:
            return match.group(1).strip()

    return question_text.strip()


async def create_flashcards():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("=" * 50)
        print("CREATING MISSING FLASHCARDS")
        print("=" * 50)

        # Create decks for each level if they don't exist
        levels = {
            1: "A1",
            2: "A2",
            3: "B1",
            4: "B2",
            5: "C1",
            6: "C2",
            7: "PREMIUM"
        }

        deck_ids = {}

        for level_id, level_name in levels.items():
            deck_name = f"📚 {level_name} - Quiz so'zlari"

            # Check if deck exists
            result = await session.execute(text("""
                SELECT id FROM flashcard_decks
                WHERE name = :name AND level_id = :level_id
                LIMIT 1
            """), {"name": deck_name, "level_id": level_id})
            existing = result.scalar()

            if existing:
                deck_ids[level_id] = existing
                print(f"Deck exists: {deck_name} (id={existing})")
            else:
                # Create deck with all required fields
                result = await session.execute(text("""
                    INSERT INTO flashcard_decks
                    (name, level_id, is_public, is_premium, icon, price, cards_count, users_studying, display_order, is_active)
                    VALUES (:name, :level_id, true, false, '📚', 0, 0, 0, 0, true)
                    RETURNING id
                """), {"name": deck_name, "level_id": level_id})
                deck_id = result.scalar()
                deck_ids[level_id] = deck_id
                print(f"Created deck: {deck_name} (id={deck_id})")

        await session.commit()

        # Get words without flashcards
        print("\nFetching words without flashcards...")
        result = await session.execute(text("""
            SELECT v.id, v.word, v.translation, v.level_id, v.audio_url, v.example_de
            FROM vocabulary v
            WHERE NOT EXISTS (
                SELECT 1 FROM flashcards f WHERE f.vocabulary_id = v.id
            )
            ORDER BY v.level_id, v.id
        """))
        words = result.fetchall()
        print(f"Found {len(words)} words without flashcards")

        # Create flashcards
        created = 0
        for word_row in words:
            vocab_id, word_text, translation, level_id, audio_url, example = word_row

            # Clean the word
            clean = clean_word(word_text)

            # Get deck for this level (default to A1 if level unknown)
            deck_id = deck_ids.get(level_id, deck_ids[1])

            # Create flashcard with all required fields
            result = await session.execute(text("""
                INSERT INTO flashcards (
                    deck_id, vocabulary_id, front_text, back_text,
                    front_audio_url, example_sentence, display_order,
                    times_shown, times_known, is_active
                )
                VALUES (
                    :deck_id, :vocab_id, :front_text, :back_text,
                    :audio_url, :example, :order,
                    0, 0, true
                )
                RETURNING id
            """), {
                "deck_id": deck_id,
                "vocab_id": vocab_id,
                "front_text": clean,
                "back_text": translation,
                "audio_url": audio_url,
                "example": example,
                "order": created
            })

            created += 1
            if created % 100 == 0:
                print(f"  Created {created} flashcards...")
                await session.commit()

        await session.commit()
        print(f"\nTotal created: {created} flashcards")

        # Update deck card counts
        print("\nUpdating deck card counts...")
        await session.execute(text("""
            UPDATE flashcard_decks fd
            SET cards_count = (
                SELECT COUNT(*) FROM flashcards f WHERE f.deck_id = fd.id
            )
        """))
        await session.commit()

        # Final stats
        print("\n" + "=" * 50)
        print("COMPLETE!")
        print("=" * 50)

        result = await session.execute(text("""
            SELECT fd.name, fd.cards_count
            FROM flashcard_decks fd
            WHERE fd.name LIKE '%Quiz so''zlari%'
            ORDER BY fd.level_id
        """))
        for row in result.fetchall():
            print(f"  {row[0]}: {row[1]} cards")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_flashcards())
