"""Text-to-Speech service using gTTS"""
import os
import tempfile
from gtts import gTTS
from src.core.logging import get_logger

logger = get_logger(__name__)

# Audio fayllar uchun papka
AUDIO_DIR = "/tmp/quiz_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)


async def generate_audio(text: str, lang: str = "de") -> str | None:
    """
    Matn uchun audio fayl yaratish
    
    Args:
        text: O'qilishi kerak bo'lgan matn
        lang: Til kodi (de=nemis, uz=o'zbek, en=ingliz)
    
    Returns:
        Audio fayl yo'li yoki None
    """
    try:
        # Faylnomi yaratish
        safe_text = "".join(c for c in text[:30] if c.isalnum() or c == " ").strip()
        filename = f"{safe_text}_{lang}.mp3".replace(" ", "_")
        filepath = os.path.join(AUDIO_DIR, filename)
        
        # Agar mavjud bo'lsa, qayta yaratmaslik
        if os.path.exists(filepath):
            return filepath
        
        # Audio yaratish
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(filepath)
        
        logger.info(f"Audio generated: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None


async def generate_audio_slow(text: str, lang: str = "de") -> str | None:
    """Sekin tezlikda audio (o'rganish uchun)"""
    try:
        safe_text = "".join(c for c in text[:30] if c.isalnum() or c == " ").strip()
        filename = f"{safe_text}_{lang}_slow.mp3".replace(" ", "_")
        filepath = os.path.join(AUDIO_DIR, filename)
        
        if os.path.exists(filepath):
            return filepath
        
        tts = gTTS(text=text, lang=lang, slow=True)
        tts.save(filepath)
        
        return filepath
        
    except Exception as e:
        logger.error(f"TTS slow error: {e}")
        return None


def cleanup_old_audio(max_age_hours: int = 24):
    """Eski audio fayllarni o'chirish"""
    import time
    
    now = time.time()
    count = 0
    
    for filename in os.listdir(AUDIO_DIR):
        filepath = os.path.join(AUDIO_DIR, filename)
        if os.path.isfile(filepath):
            age = now - os.path.getmtime(filepath)
            if age > max_age_hours * 3600:
                os.remove(filepath)
                count += 1
    
    if count:
        logger.info(f"Cleaned up {count} old audio files")
