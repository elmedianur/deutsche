"""
Audio service - Text-to-Speech for pronunciation
Supports multiple providers: gTTS, Azure, local files
"""
import os
import hashlib
from pathlib import Path
from typing import Optional, BinaryIO
from io import BytesIO

from src.config import settings
from src.core.logging import get_logger, LoggerMixin
from src.core.exceptions import AudioServiceError

logger = get_logger(__name__)

# Audio cache directory
AUDIO_CACHE_DIR = Path("audio/cache")
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class AudioService(LoggerMixin):
    """Text-to-Speech audio service"""
    
    # Language codes for TTS
    LANGUAGE_CODES = {
        "de": "de",      # German
        "en": "en",      # English
        "fr": "fr",      # French
        "es": "es",      # Spanish
        "it": "it",      # Italian
        "ru": "ru",      # Russian
        "uz": "uz",      # Uzbek (may not be supported by all providers)
    }
    
    def __init__(self):
        self.provider = settings.AUDIO_PROVIDER
        self.enabled = settings.AUDIO_ENABLED
    
    def _get_cache_path(self, text: str, lang: str) -> Path:
        """Get cache file path for text"""
        # Create hash of text for filename
        text_hash = hashlib.md5(f"{text}:{lang}".encode()).hexdigest()
        return AUDIO_CACHE_DIR / f"{text_hash}.mp3"
    
    async def _generate_gtts(self, text: str, lang: str) -> bytes:
        """Generate audio using Google TTS"""
        try:
            from gtts import gTTS
            import asyncio
            
            # gTTS is synchronous, run in executor
            loop = asyncio.get_event_loop()
            
            def generate():
                tts = gTTS(text=text, lang=lang, slow=False)
                fp = BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                return fp.read()
            
            return await loop.run_in_executor(None, generate)
            
        except Exception as e:
            self.logger.error("gTTS error", error=str(e))
            raise AudioServiceError(f"gTTS failed: {e}", "gtts")
    
    async def _generate_azure(self, text: str, lang: str) -> bytes:
        """Generate audio using Azure Cognitive Services"""
        try:
            import azure.cognitiveservices.speech as speechsdk
            import asyncio
            
            if not settings.AZURE_SPEECH_KEY:
                raise AudioServiceError("Azure Speech key not configured", "azure")
            
            speech_config = speechsdk.SpeechConfig(
                subscription=settings.AZURE_SPEECH_KEY.get_secret_value(),
                region=settings.AZURE_SPEECH_REGION
            )
            
            # Voice mapping
            voices = {
                "de": "de-DE-ConradNeural",
                "en": "en-US-JennyNeural",
                "fr": "fr-FR-DeniseNeural",
                "es": "es-ES-ElviraNeural",
                "it": "it-IT-ElsaNeural",
                "ru": "ru-RU-SvetlanaNeural",
            }
            
            speech_config.speech_synthesis_voice_name = voices.get(lang, voices["en"])
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
            )
            
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=None
            )
            
            loop = asyncio.get_event_loop()
            
            def generate():
                result = synthesizer.speak_text_async(text).get()
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    return result.audio_data
                else:
                    raise AudioServiceError(
                        f"Azure synthesis failed: {result.reason}",
                        "azure"
                    )
            
            return await loop.run_in_executor(None, generate)
            
        except ImportError:
            raise AudioServiceError("Azure SDK not installed", "azure")
        except Exception as e:
            self.logger.error("Azure TTS error", error=str(e))
            raise AudioServiceError(f"Azure TTS failed: {e}", "azure")
    
    async def generate_audio(
        self,
        text: str,
        lang: str = "de",
        use_cache: bool = True
    ) -> Optional[bytes]:
        """
        Generate audio for text.
        
        Args:
            text: Text to convert to speech
            lang: Language code (de, en, etc.)
            use_cache: Whether to use cached audio
        
        Returns:
            Audio bytes (MP3) or None if disabled
        """
        if not self.enabled:
            return None
        
        # Normalize language code
        lang = self.LANGUAGE_CODES.get(lang, "de")
        
        # Check cache
        cache_path = self._get_cache_path(text, lang)
        
        if use_cache and cache_path.exists():
            self.logger.debug("Using cached audio", text=text[:20])
            return cache_path.read_bytes()
        
        # Generate based on provider
        try:
            if self.provider == "gtts":
                audio_data = await self._generate_gtts(text, lang)
            elif self.provider == "azure":
                audio_data = await self._generate_azure(text, lang)
            elif self.provider == "local":
                # Local files not supported for dynamic generation
                return None
            else:
                self.logger.warning(f"Unknown provider: {self.provider}")
                return None
            
            # Cache the result
            if use_cache and audio_data:
                cache_path.write_bytes(audio_data)
                self.logger.debug("Cached audio", text=text[:20])
            
            return audio_data
            
        except AudioServiceError:
            raise
        except Exception as e:
            self.logger.error("Audio generation failed", error=str(e))
            return None
    
    async def get_audio_file(
        self,
        text: str,
        lang: str = "de"
    ) -> Optional[BinaryIO]:
        """Get audio as file-like object for Telegram"""
        audio_data = await self.generate_audio(text, lang)
        
        if audio_data:
            fp = BytesIO(audio_data)
            fp.name = "pronunciation.mp3"
            return fp
        
        return None
    
    def get_local_audio(self, audio_path: str) -> Optional[bytes]:
        """Get pre-recorded audio file"""
        path = Path(audio_path)
        
        if not path.exists():
            # Try in audio directory
            path = Path("audio") / audio_path
        
        if path.exists():
            return path.read_bytes()
        
        return None
    
    def clear_cache(self) -> int:
        """Clear audio cache"""
        count = 0
        for file in AUDIO_CACHE_DIR.glob("*.mp3"):
            file.unlink()
            count += 1
        
        self.logger.info(f"Cleared {count} cached audio files")
        return count
    
    def get_cache_size(self) -> tuple[int, int]:
        """Get cache statistics (files, bytes)"""
        files = list(AUDIO_CACHE_DIR.glob("*.mp3"))
        total_size = sum(f.stat().st_size for f in files)
        return len(files), total_size


# Global service instance
audio_service = AudioService()
