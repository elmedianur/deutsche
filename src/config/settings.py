"""
Configuration management with Pydantic Settings
Environment validation and type safety
"""
from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Bot settings
    BOT_TOKEN: SecretStr = Field(..., description="Telegram Bot Token")
    BOT_USERNAME: str = Field(default="quiz_bot", description="Bot username without @")
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/quiz_bot",
        description="Async database URL"
    )
    DATABASE_ECHO: bool = Field(default=False, description="Echo SQL queries")
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    
    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    REDIS_PREFIX: str = Field(default="quiz:", description="Redis key prefix")
    
    # Admin settings
    SUPER_ADMIN_IDS: List[int] = Field(default_factory=list)
    ADMIN_IDS: List[int] = Field(default_factory=list)
    
    @field_validator("SUPER_ADMIN_IDS", "ADMIN_IDS", mode="before")
    @classmethod
    def parse_int_list(cls, v):
        """Parse comma-separated string to list of ints"""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v or []
    
    # Quiz settings
    DEFAULT_TIME_PER_QUESTION: int = Field(default=15, ge=5, le=120)
    MAX_QUESTIONS_PER_QUIZ: int = Field(default=200, ge=1, le=1000)
    STREAK_RESET_HOURS: int = Field(default=36, ge=24, le=72)
    
    # Payment settings (Telegram Stars)
    STARS_ENABLED: bool = Field(default=True)
    PREMIUM_MONTHLY_STARS: int = Field(default=100, description="Stars for 1 month premium")
    PREMIUM_YEARLY_STARS: int = Field(default=1000, description="Stars for 1 year premium")
    PREMIUM_LIFETIME_STARS: int = Field(default=5000, description="Stars for lifetime premium")

    # Quiz session settings
    QUIZ_QUESTION_TIME: int = Field(default=15, ge=5, le=60, description="Seconds per question")
    QUIZ_SESSION_CLEANUP_INTERVAL: int = Field(default=300, description="Session cleanup interval in seconds")
    QUIZ_MAX_SESSION_AGE: int = Field(default=1800, description="Max session age in seconds")
    
    # Audio settings
    AUDIO_ENABLED: bool = Field(default=True)
    AUDIO_PROVIDER: str = Field(default="gtts", description="gtts, azure, or local")
    AZURE_SPEECH_KEY: Optional[SecretStr] = Field(default=None)
    AZURE_SPEECH_REGION: str = Field(default="westeurope")
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = Field(default=30, ge=1, le=100)
    RATE_LIMIT_COMMANDS_PER_MINUTE: int = Field(default=10, ge=1, le=50)
    
    # Webhook settings
    WEBHOOK_ENABLED: bool = Field(default=False)
    WEBHOOK_URL: Optional[str] = Field(default=None)
    WEBHOOK_SECRET: Optional[SecretStr] = Field(default=None)
    WEBHOOK_HOST: str = Field(default="0.0.0.0")
    WEBHOOK_PORT: int = Field(default=8080, ge=1, le=65535)
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json", description="json or text")
    LOG_FILE: Optional[str] = Field(default="logs/bot.log")
    
    # Referral settings
    REFERRAL_BONUS_DAYS: int = Field(default=3, description="Premium days for referral")
    REFERRAL_MIN_QUIZZES: int = Field(default=5, description="Min quizzes for referral reward")
    
    # Tournament settings
    TOURNAMENT_ENABLED: bool = Field(default=True)
    WEEKLY_TOURNAMENT_DAY: int = Field(default=0, ge=0, le=6, description="0=Monday")
    WEEKLY_TOURNAMENT_HOUR: int = Field(default=10, ge=0, le=23)
    

    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()
    
    @property
    def all_admin_ids(self) -> List[int]:
        """Combined list of all admin IDs"""
        return list(set(self.SUPER_ADMIN_IDS + self.ADMIN_IDS))
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.all_admin_ids
    
    def is_super_admin(self, user_id: int) -> bool:
        """Check if user is super admin"""
        return user_id in self.SUPER_ADMIN_IDS


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience alias
settings = get_settings()
