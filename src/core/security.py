"""
Security module - Rate limiting, input validation, sanitization
"""
import re
import html
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from functools import wraps

from src.config import settings
from src.core.exceptions import RateLimitException, ValidationException, InvalidInputError
from src.core.logging import get_logger, audit_logger

logger = get_logger(__name__)


# ============================================================
# INPUT VALIDATION
# ============================================================

class InputValidator:
    """Input validation utilities"""
    
    # Patterns
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{1,32}$')
    SAFE_TEXT_PATTERN = re.compile(r'^[\w\s\-.,!?()\'\"]+$', re.UNICODE)
    URL_PATTERN = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$',
        re.IGNORECASE
    )
    
    @classmethod
    def sanitize_html(cls, text: str) -> str:
        """Sanitize HTML to prevent XSS"""
        return html.escape(text)
    
    @classmethod
    def sanitize_text(cls, text: str, max_length: int = 1000) -> str:
        """Sanitize and truncate text"""
        if not text:
            return ""
        # Remove null bytes and control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # Normalize whitespace
        text = ' '.join(text.split())
        # Truncate
        if len(text) > max_length:
            text = text[:max_length]
        return text
    
    @classmethod
    def validate_username(cls, username: str) -> bool:
        """Validate Telegram username format"""
        if not username:
            return True  # Username is optional
        return bool(cls.USERNAME_PATTERN.match(username))
    
    @classmethod
    def validate_url(cls, url: str) -> bool:
        """Validate URL format"""
        return bool(cls.URL_PATTERN.match(url))
    
    @classmethod
    def validate_chat_id(cls, chat_id: Any) -> int:
        """Validate and convert chat ID"""
        try:
            chat_id = int(chat_id)
            return chat_id
        except (ValueError, TypeError):
            raise InvalidInputError("chat_id", "Must be a valid integer")
    
    @classmethod
    def validate_positive_int(cls, value: Any, field_name: str, max_value: int = 10000) -> int:
        """Validate positive integer"""
        try:
            value = int(value)
            if value <= 0:
                raise ValueError("Must be positive")
            if value > max_value:
                raise ValueError(f"Must be <= {max_value}")
            return value
        except ValueError as e:
            raise InvalidInputError(field_name, str(e))
    
    @classmethod
    def validate_option(cls, value: str) -> str:
        """Validate quiz option (A, B, C, D)"""
        value = value.upper().strip()
        if value not in ['A', 'B', 'C', 'D']:
            raise InvalidInputError("option", "Must be A, B, C, or D")
        return value
    
    @classmethod
    def validate_language_code(cls, code: str) -> str:
        """Validate language code"""
        code = code.lower().strip()
        if not re.match(r'^[a-z]{2,3}$', code):
            raise InvalidInputError("language_code", "Must be 2-3 letter code")
        return code
    
    @classmethod
    def validate_question_text(cls, text: str) -> str:
        """Validate question text"""
        text = cls.sanitize_text(text, max_length=500)
        if len(text) < 3:
            raise InvalidInputError("question", "Too short (min 3 chars)")
        return text
    
    @classmethod
    def validate_option_text(cls, text: str) -> str:
        """Validate option text"""
        text = cls.sanitize_text(text, max_length=200)
        if len(text) < 1:
            raise InvalidInputError("option", "Cannot be empty")
        return text


# ============================================================
# RATE LIMITING (In-Memory for single instance)
# ============================================================

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self._buckets: Dict[str, list] = {}
        self._last_cleanup = datetime.now()
    
    def _cleanup_old_entries(self) -> None:
        """Remove old entries periodically"""
        now = datetime.now()
        if now - self._last_cleanup < timedelta(minutes=5):
            return
        
        self._last_cleanup = now
        cutoff = now - timedelta(minutes=10)
        
        for key in list(self._buckets.keys()):
            self._buckets[key] = [
                ts for ts in self._buckets[key]
                if ts > cutoff
            ]
            if not self._buckets[key]:
                del self._buckets[key]
    
    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60
    ) -> bool:
        """
        Check if action is allowed under rate limit.
        Returns True if allowed, raises RateLimitException if exceeded.
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True
        
        self._cleanup_old_entries()
        
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        if key not in self._buckets:
            self._buckets[key] = []
        
        # Remove old entries for this key
        self._buckets[key] = [
            ts for ts in self._buckets[key]
            if ts > window_start
        ]
        
        # Check limit
        if len(self._buckets[key]) >= limit:
            retry_after = window_seconds - int((now - self._buckets[key][0]).total_seconds())
            raise RateLimitException(
                "Rate limit exceeded. Please wait.",
                retry_after=max(retry_after, 1)
            )
        
        # Add current request
        self._buckets[key].append(now)
        return True
    
    def get_remaining(self, key: str, limit: int, window_seconds: int = 60) -> int:
        """Get remaining requests for the key"""
        if key not in self._buckets:
            return limit
        
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        recent = [ts for ts in self._buckets[key] if ts > window_start]
        return max(0, limit - len(recent))


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(
    limit: int = 10,
    window_seconds: int = 60,
    key_func: Optional[callable] = None
):
    """
    Rate limit decorator for handlers.
    
    Usage:
        @rate_limit(limit=5, window_seconds=60)
        async def my_handler(message: Message):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user_id from message or callback
            user_id = None
            for arg in args:
                if hasattr(arg, 'from_user') and arg.from_user:
                    user_id = arg.from_user.id
                    break
            
            if user_id is None:
                # Fallback key - user_id topilmasa ham rate limiting qo'llaniladi
                # Bu xavfsizlik bypass'ini oldini oladi
                user_id = "unknown"
            
            # Generate key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"rate:{func.__name__}:{user_id}"
            
            # Check rate limit
            rate_limiter.check_rate_limit(key, limit, window_seconds)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# SECURITY UTILITIES
# ============================================================

def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token"""
    return secrets.token_urlsafe(length)


def hash_data(data: str) -> str:
    """Hash data using SHA-256"""
    return hashlib.sha256(data.encode()).hexdigest()


def verify_hash(data: str, expected_hash: str) -> bool:
    """Verify data against hash"""
    return secrets.compare_digest(hash_data(data), expected_hash)


def generate_referral_code(user_id: int) -> str:
    """Generate unique referral code for user using secure hashing"""
    # Token'ning hash'ini olish (asl qiymat oshkor bo'lmasin)
    token_hash = hashlib.sha256(settings.BOT_TOKEN.get_secret_value().encode()).hexdigest()[:16]
    # User ID va token hash'ini birlashtirish
    data = f"{user_id}:{token_hash}"
    # SHA256 ishlatish (MD5 dan xavfsizroq)
    return hashlib.sha256(data.encode()).hexdigest()[:8].upper()


def verify_referral_code(code: str, user_id: int) -> bool:
    """Verify referral code belongs to user"""
    expected = generate_referral_code(user_id)
    return secrets.compare_digest(code.upper(), expected)


# ============================================================
# PERMISSION CHECKS
# ============================================================

def is_admin(user_id: int) -> bool:
    """Check if user is admin (regular or super)"""
    return settings.is_admin(user_id)


def is_super_admin(user_id: int) -> bool:
    """Check if user is super admin"""
    return settings.is_super_admin(user_id)


def admin_required(func):
    """Decorator to require admin permission"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user_id = None
        event = None
        for arg in args:
            if hasattr(arg, 'from_user') and arg.from_user:
                user_id = arg.from_user.id
                event = arg
                break

        if user_id is None or not settings.is_admin(user_id):
            logger.warning("Unauthorized admin access attempt", user_id=user_id)
            audit_logger.log_security_event(
                "unauthorized_admin_access",
                user_id=user_id
            )
            # Foydalanuvchiga xabar berish (UX yaxshilash)
            if event:
                try:
                    if hasattr(event, 'answer'):
                        await event.answer("⛔ Sizda admin huquqlari yo'q!", show_alert=True)
                    elif hasattr(event, 'reply'):
                        await event.reply("⛔ Sizda admin huquqlari yo'q!")
                except Exception:
                    pass
            return None

        return await func(*args, **kwargs)
    return wrapper


def super_admin_required(func):
    """Decorator to require super admin permission"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user_id = None
        event = None
        for arg in args:
            if hasattr(arg, 'from_user') and arg.from_user:
                user_id = arg.from_user.id
                event = arg
                break

        if user_id is None or not settings.is_super_admin(user_id):
            logger.warning("Unauthorized super admin access attempt", user_id=user_id)
            audit_logger.log_security_event(
                "unauthorized_super_admin_access",
                user_id=user_id
            )
            # Foydalanuvchiga xabar berish (UX yaxshilash)
            if event:
                try:
                    if hasattr(event, 'answer'):
                        await event.answer("⛔ Sizda super admin huquqlari yo'q!", show_alert=True)
                    elif hasattr(event, 'reply'):
                        await event.reply("⛔ Sizda super admin huquqlari yo'q!")
                except Exception:
                    pass
            return None

        return await func(*args, **kwargs)
    return wrapper
