"""
Audio service - Text-to-Speech for pronunciation
Supports gTTS and Azure Cognitive Services
"""
import io
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Union
from functools import lru_cache

from src.config import settings
from src.core.logging import get_logger, LoggerMixin
from src.core.exceptions import AudioServiceError

logger = get_logger(__name__)

# Audio cache directory
AUDIO_CACHE_DIR = Path("audio/cache")
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class AudioService(LoggerMixin):
    """
    Audio service for text-to-speech.
    
    Providers:
    - gtts: Google Text-to-Speech (free, basic)
    - azure: Azure Cognitive Services (professional, accurate)
    - local: Pre-recorded audio files
    """
    
    def __init__(self):
        self.provider = settings.AUDIO_PROVIDER
        self._azure_client = None
    
    def _get_cache_path(self, text: str, lang: str) -> Path:
        """Generate cache file path"""
        text_hash = hashlib.md5(f"{text}:{lang}".encode()).hexdigest()
        return AUDIO_CACHE_DIR / f"{lang}_{text_hash}.mp3"
    
    async def get_audio(
        self,
        text: str,
        lang: str = "de",
        slow: bool = False
    ) -> Optional[bytes]:
        """
        Get audio for text.
        
        Args:
            text: Text to convert to speech
            lang: Language code (de, en, ru, etc.)
            slow: Slow speech mode (for learning)
        
        Returns:
            Audio bytes (MP3) or None
        """
        if not settings.AUDIO_ENABLED:
            return None
        
        # Check cache
        cache_key = f"{text}:{lang}:{'slow' if slow else 'normal'}"
        cache_path = self._get_cache_path(cache_key, lang)
        
        if cache_path.exists():
            self.logger.debug("Audio cache hit", text=text[:20], lang=lang)
            return cache_path.read_bytes()
        
        # Generate audio
        try:
            if self.provider == "azure":
                audio = await self._generate_azure(text, lang, slow)
            elif self.provider == "gtts":
                audio = await self._generate_gtts(text, lang, slow)
            else:
                # Local files
                audio = self._get_local_audio(text, lang)
            
            if audio:
                # Save to cache
                cache_path.write_bytes(audio)
                self.logger.debug("Audio generated and cached", text=text[:20], lang=lang)
            
            return audio
            
        except Exception as e:
            self.logger.error("Audio generation failed", error=str(e), text=text[:20])
            raise AudioServiceError(str(e), self.provider)
    
    async def _generate_gtts(
        self,
        text: str,
        lang: str,
        slow: bool
    ) -> bytes:
        """Generate audio using gTTS"""
        # Run in executor to not block event loop
        loop = asyncio.get_event_loop()
        
        def _generate():
            from gtts import gTTS
            
            tts = gTTS(text=text, lang=lang, slow=slow)
            buffer = io.BytesIO()
            tts.write_to_fp(buffer)
            return buffer.getvalue()
        
        return await loop.run_in_executor(None, _generate)
    
    async def _generate_azure(
        self,
        text: str,
        lang: str,
        slow: bool
    ) -> bytes:
        """Generate audio using Azure Cognitive Services"""
        if not settings.AZURE_SPEECH_KEY:
            raise AudioServiceError("Azure Speech key not configured", "azure")
        
        # Voice mapping
        voices = {
            "de": "de-DE-KatjaNeural",
            "en": "en-US-JennyNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "uz": "uz-UZ-MadinaNeural",
        }
        
        voice = voices.get(lang, voices["en"])
        
        # SSML with rate control
        rate = "slow" if slow else "medium"
        ssml = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">
            <voice name="{voice}">
                <prosody rate="{rate}">
                    {text}
                </prosody>
            </voice>
        </speak>
        """
        
        # Make request
        loop = asyncio.get_event_loop()
        
        def _generate():
            import requests
            
            url = f"https://{settings.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
            headers = {
                "Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY.get_secret_value(),
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3"
            }
            
            response = requests.post(url, headers=headers, data=ssml.encode("utf-8"))
            response.raise_for_status()
            
            return response.content
        
        return await loop.run_in_executor(None, _generate)
    
    def _get_local_audio(self, text: str, lang: str) -> Optional[bytes]:
        """Get pre-recorded audio file"""
        # Check for exact match
        text_hash = hashlib.md5(text.encode()).hexdigest()
        audio_path = Path(f"audio/prerecorded/{lang}/{text_hash}.mp3")
        
        if audio_path.exists():
            return audio_path.read_bytes()
        
        return None
    
    async def get_question_audio(
        self,
        question_text: str,
        lang: str = "de"
    ) -> Optional[bytes]:
        """Get audio for quiz question"""
        # Extract the word/phrase to pronounce (usually the quoted part)
        import re
        
        # Find text in quotes
        match = re.search(r'"([^"]+)"', question_text)
        if match:
            text = match.group(1)
        else:
            # Use full question
            text = question_text
        
        return await self.get_audio(text, lang)
    
    def clear_cache(self) -> int:
        """Clear audio cache, returns number of files deleted"""
        count = 0
        for file in AUDIO_CACHE_DIR.glob("*.mp3"):
            file.unlink()
            count += 1
        
        self.logger.info("Audio cache cleared", files_deleted=count)
        return count
    
    def get_cache_size(self) -> dict:
        """Get cache statistics"""
        files = list(AUDIO_CACHE_DIR.glob("*.mp3"))
        total_size = sum(f.stat().st_size for f in files)
        
        return {
            "files_count": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }


# Singleton instance
_audio_service: Optional[AudioService] = None


def get_audio_service() -> AudioService:
    """Get audio service instance"""
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioService()
    return _audio_service
