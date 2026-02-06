"""
Core utilities - Secure random functions and helpers
"""
import secrets
import random as _random
from datetime import datetime, date, timezone
from typing import List, TypeVar, Sequence


def utc_today() -> date:
    """UTC timezone bo'yicha bugungi sanani qaytaradi.

    Server timezone'dan qat'i nazar doim UTC vaqtini ishlatadi.
    date.today() o'rniga hamma joyda shu funksiyani ishlating.
    """
    return datetime.now(timezone.utc).date()

T = TypeVar('T')


def utc_now() -> datetime:
    """UTC timezone-aware hozirgi vaqtni qaytaradi."""
    return datetime.now(timezone.utc)


def safe_parse_int(data: str, index: int, delimiter: str = ":") -> int | None:
    """Callback data dan xavfsiz int parse qilish.

    IndexError va ValueError dan himoya qiladi.
    None qaytarsa — callback.answer("Xatolik") qilish kerak.
    Manfiy index ham qo'llab-quvvatlanadi (masalan -1 = oxirgi element).
    """
    parts = data.split(delimiter)
    try:
        return int(parts[index])
    except (ValueError, TypeError, IndexError):
        return None


def safe_parse_str(data: str, index: int, delimiter: str = ":") -> str | None:
    """Callback data dan xavfsiz string parse qilish."""
    parts = data.split(delimiter)
    if index >= len(parts):
        return None
    return parts[index]


def secure_shuffle(items: Sequence[T]) -> List[T]:
    """
    Xavfsiz shuffle - secrets bilan seed qilingan.

    Oddiy random.shuffle() o'rniga kriptografik xavfsiz random ishlatadi.
    Bu quiz savollarini aralashtirish uchun muhim - bashorat qilinmasligi kerak.

    Args:
        items: Aralashtiriladigan ro'yxat

    Returns:
        Aralashtirilgan yangi ro'yxat (original o'zgarmaydi)
    """
    items_list = list(items)
    # Kriptografik xavfsiz seed bilan Random yaratish
    rng = _random.Random(secrets.token_bytes(32))
    rng.shuffle(items_list)
    return items_list


def secure_randint(a: int, b: int) -> int:
    """
    Xavfsiz random integer [a, b] oralig'ida (ikkala uchi ham kiradi).

    Args:
        a: Minimal qiymat (kiradi)
        b: Maksimal qiymat (kiradi)

    Returns:
        Tasodifiy son
    """
    if a > b:
        a, b = b, a
    return secrets.randbelow(b - a + 1) + a


def secure_choice(items: Sequence[T]) -> T:
    """
    Ro'yxatdan xavfsiz tasodifiy element tanlash.

    Args:
        items: Tanlanadigan ro'yxat

    Returns:
        Tasodifiy element

    Raises:
        IndexError: Agar ro'yxat bo'sh bo'lsa
    """
    if not items:
        raise IndexError("Cannot choose from empty sequence")
    index = secrets.randbelow(len(items))
    return items[index]


def secure_sample(items: Sequence[T], k: int) -> List[T]:
    """
    Ro'yxatdan k ta takrorlanmas element tanlash.

    Args:
        items: Tanlanadigan ro'yxat
        k: Tanlanadigan elementlar soni

    Returns:
        k ta tasodifiy element ro'yxati

    Raises:
        ValueError: Agar k > len(items)
    """
    items_list = list(items)
    if k > len(items_list):
        raise ValueError(f"Sample size {k} exceeds population size {len(items_list)}")

    # Fisher-Yates shuffle ning birinchi k elementini olish
    rng = _random.Random(secrets.token_bytes(32))
    result = []
    for i in range(k):
        j = rng.randint(i, len(items_list) - 1)
        items_list[i], items_list[j] = items_list[j], items_list[i]
        result.append(items_list[i])

    return result
