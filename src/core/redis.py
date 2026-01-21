"""
Redis client for state management and caching
Handles quiz sessions, rate limiting, and temporary data
Falls back to in-memory storage if Redis is unavailable
"""
import json
import time
import threading
from datetime import timedelta
from typing import Any, Optional, Dict, Tuple

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Redis client instance
_redis: Optional[Any] = None
_use_memory_fallback: bool = False

# In-memory fallback storage with TTL support
# Format: {key: (value, expire_timestamp or None)}
_memory_store: Dict[str, Tuple[Any, Optional[float]]] = {}
_memory_lock = threading.Lock()

# Memory cleanup settings
MEMORY_CLEANUP_INTERVAL = 60  # Har daqiqada cleanup
MAX_MEMORY_ITEMS = 10000  # Maksimum item soni
_last_cleanup = 0


def _cleanup_expired_memory():
    """Muddati tugagan itemlarni tozalash"""
    global _last_cleanup

    now = time.time()
    if now - _last_cleanup < MEMORY_CLEANUP_INTERVAL:
        return

    _last_cleanup = now
    expired_keys = []

    with _memory_lock:
        for key, (value, expire_at) in list(_memory_store.items()):
            if expire_at and expire_at < now:
                expired_keys.append(key)

        for key in expired_keys:
            del _memory_store[key]

        # Agar juda ko'p item bo'lsa, eng eskilarini o'chirish
        if len(_memory_store) > MAX_MEMORY_ITEMS:
            # Expiry vaqti bo'yicha sort qilib eskilarini o'chirish
            items_to_remove = len(_memory_store) - MAX_MEMORY_ITEMS
            sorted_keys = sorted(
                _memory_store.keys(),
                key=lambda k: _memory_store[k][1] or float('inf')
            )
            for key in sorted_keys[:items_to_remove]:
                del _memory_store[key]

    if expired_keys:
        logger.debug(f"Memory cleanup: {len(expired_keys)} expired items removed")


class MemoryFallback:
    """In-memory fallback when Redis is unavailable - TTL supported"""

    async def get(self, key: str) -> Optional[str]:
        _cleanup_expired_memory()
        with _memory_lock:
            if key not in _memory_store:
                return None
            value, expire_at = _memory_store[key]
            # TTL tekshirish
            if expire_at and expire_at < time.time():
                del _memory_store[key]
                return None
            return value

    async def set(self, key: str, value: str, ex: int = None) -> None:
        _cleanup_expired_memory()
        with _memory_lock:
            expire_at = time.time() + ex if ex else None
            _memory_store[key] = (value, expire_at)

    async def setex(self, key: str, seconds: int, value: str) -> None:
        """Set with expiration"""
        _cleanup_expired_memory()
        with _memory_lock:
            expire_at = time.time() + seconds
            _memory_store[key] = (value, expire_at)

    async def delete(self, key: str) -> None:
        with _memory_lock:
            _memory_store.pop(key, None)

    async def exists(self, key: str) -> bool:
        with _memory_lock:
            if key not in _memory_store:
                return False
            value, expire_at = _memory_store[key]
            if expire_at and expire_at < time.time():
                del _memory_store[key]
                return False
            return True

    async def incr(self, key: str) -> int:
        with _memory_lock:
            if key in _memory_store:
                old_val, expire_at = _memory_store[key]
                val = int(old_val) + 1
                _memory_store[key] = (str(val), expire_at)
            else:
                val = 1
                _memory_store[key] = (str(val), None)
            return val

    async def expire(self, key: str, seconds: int) -> None:
        with _memory_lock:
            if key in _memory_store:
                value, _ = _memory_store[key]
                _memory_store[key] = (value, time.time() + seconds)

    async def ttl(self, key: str) -> int:
        with _memory_lock:
            if key not in _memory_store:
                return -2  # Key mavjud emas
            value, expire_at = _memory_store[key]
            if expire_at is None:
                return -1  # TTL yo'q
            remaining = int(expire_at - time.time())
            return max(0, remaining)

    async def sadd(self, key: str, *values) -> int:
        """Add to set (for duel matching)"""
        _cleanup_expired_memory()
        with _memory_lock:
            if key not in _memory_store:
                _memory_store[key] = (set(), None)
            current_val, expire_at = _memory_store[key]
            if not isinstance(current_val, set):
                current_val = set()
            for v in values:
                current_val.add(v)
            _memory_store[key] = (current_val, expire_at)
            return len(values)

    async def smembers(self, key: str) -> set:
        """Get set members"""
        with _memory_lock:
            if key not in _memory_store:
                return set()
            value, expire_at = _memory_store[key]
            if expire_at and expire_at < time.time():
                del _memory_store[key]
                return set()
            return value if isinstance(value, set) else set()

    async def srem(self, key: str, *values) -> int:
        """Remove from set"""
        with _memory_lock:
            if key in _memory_store:
                current_val, expire_at = _memory_store[key]
                if isinstance(current_val, set):
                    for v in values:
                        current_val.discard(v)
                    _memory_store[key] = (current_val, expire_at)
                    return len(values)
            return 0

    async def close(self) -> None:
        pass


def get_memory_stats() -> dict:
    """Memory fallback statistikasi"""
    with _memory_lock:
        now = time.time()
        total = len(_memory_store)
        expired = sum(1 for _, (_, exp) in _memory_store.items() if exp and exp < now)
        with_ttl = sum(1 for _, (_, exp) in _memory_store.items() if exp is not None)

        return {
            "total_items": total,
            "expired_pending": expired,
            "with_ttl": with_ttl,
            "without_ttl": total - with_ttl,
            "max_allowed": MAX_MEMORY_ITEMS
        }


async def get_redis() -> Any:
    """Get Redis connection or memory fallback"""
    global _redis, _use_memory_fallback
    
    if _use_memory_fallback:
        return _redis
    
    if _redis is None:
        try:
            from redis import asyncio as aioredis
            _redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_keepalive=True,
            )
            # Test connection
            await _redis.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis unavailable, using memory fallback: {e}")
            _redis = MemoryFallback()
            _use_memory_fallback = True
    
    return _redis


async def close_redis() -> None:
    """Close Redis connection"""
    global _redis, _use_memory_fallback
    
    if _redis:
        await _redis.close()
        _redis = None
        _use_memory_fallback = False
        logger.info("Redis connection closed")


def _key(name: str) -> str:
    """Generate prefixed key"""
    return f"{settings.REDIS_PREFIX}{name}"


# ============================================================
# BASIC OPERATIONS
# ============================================================

async def set_value(
    key: str,
    value: Any,
    expire: Optional[int] = None
) -> bool:
    """Set a value with optional expiration (seconds)"""
    redis = await get_redis()
    
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    
    try:
        if expire:
            await redis.setex(_key(key), expire, value)
        else:
            await redis.set(_key(key), value)
        return True
    except Exception as e:
        logger.error("Redis set error", key=key, error=str(e))
        return False


async def get_value(key: str) -> Optional[str]:
    """Get a string value"""
    redis = await get_redis()
    try:
        return await redis.get(_key(key))
    except Exception as e:
        logger.error("Redis get error", key=key, error=str(e))
        return None


async def get_json(key: str) -> Optional[Any]:
    """Get and parse JSON value"""
    value = await get_value(key)
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return None


async def delete_key(key: str) -> bool:
    """Delete a key"""
    redis = await get_redis()
    try:
        await redis.delete(_key(key))
        return True
    except Exception as e:
        logger.error("Redis delete error", key=key, error=str(e))
        return False


async def exists(key: str) -> bool:
    """Check if key exists"""
    redis = await get_redis()
    try:
        return await redis.exists(_key(key)) > 0
    except Exception as e:
        logger.error("Redis exists error", key=key, error=str(e))
        return False


async def expire(key: str, seconds: int) -> bool:
    """Set expiration on existing key"""
    redis = await get_redis()
    try:
        return await redis.expire(_key(key), seconds)
    except Exception as e:
        logger.error("Redis expire error", key=key, error=str(e))
        return False


async def ttl(key: str) -> int:
    """Get time to live for key"""
    redis = await get_redis()
    try:
        return await redis.ttl(_key(key))
    except Exception as e:
        logger.error("Redis ttl error", key=key, error=str(e))
        return -1


# ============================================================
# QUIZ SESSION MANAGEMENT
# ============================================================

class QuizSessionManager:
    """Manage quiz sessions in Redis"""
    
    PREFIX = "quiz_session"
    DEFAULT_EXPIRE = 3600  # 1 hour
    
    @classmethod
    def _session_key(cls, user_id: int, chat_id: int = 0) -> str:
        """Generate session key"""
        return f"{cls.PREFIX}:{user_id}:{chat_id}"
    
    @classmethod
    async def create_session(
        cls,
        user_id: int,
        chat_id: int,
        data: Dict[str, Any],
        expire: int = DEFAULT_EXPIRE
    ) -> bool:
        """Create new quiz session"""
        key = cls._session_key(user_id, chat_id)
        data["created_at"] = str(datetime.utcnow())
        return await set_value(key, data, expire)
    
    @classmethod
    async def get_session(cls, user_id: int, chat_id: int = 0) -> Optional[Dict]:
        """Get quiz session"""
        key = cls._session_key(user_id, chat_id)
        return await get_json(key)
    
    @classmethod
    async def update_session(
        cls,
        user_id: int,
        chat_id: int,
        updates: Dict[str, Any]
    ) -> bool:
        """Update quiz session"""
        key = cls._session_key(user_id, chat_id)
        current = await get_json(key)
        
        if current is None:
            return False
        
        current.update(updates)
        return await set_value(key, current, cls.DEFAULT_EXPIRE)
    
    @classmethod
    async def delete_session(cls, user_id: int, chat_id: int = 0) -> bool:
        """Delete quiz session"""
        key = cls._session_key(user_id, chat_id)
        return await delete_key(key)
    
    @classmethod
    async def has_active_session(cls, user_id: int, chat_id: int = 0) -> bool:
        """Check if user has active session"""
        key = cls._session_key(user_id, chat_id)
        return await exists(key)


# ============================================================
# GROUP QUIZ MANAGEMENT
# ============================================================

class GroupQuizManager:
    """Manage group quiz state in Redis"""
    
    PREFIX = "group_quiz"
    DEFAULT_EXPIRE = 7200  # 2 hours
    
    @classmethod
    def _quiz_key(cls, chat_id: int) -> str:
        return f"{cls.PREFIX}:{chat_id}"
    
    @classmethod
    async def start_quiz(cls, chat_id: int, data: Dict[str, Any]) -> bool:
        """Start group quiz"""
        key = cls._quiz_key(chat_id)
        data["active"] = True
        data["started_at"] = str(datetime.utcnow())
        return await set_value(key, data, cls.DEFAULT_EXPIRE)
    
    @classmethod
    async def get_quiz(cls, chat_id: int) -> Optional[Dict]:
        """Get group quiz state"""
        key = cls._quiz_key(chat_id)
        return await get_json(key)
    
    @classmethod
    async def update_quiz(cls, chat_id: int, updates: Dict[str, Any]) -> bool:
        """Update group quiz state"""
        key = cls._quiz_key(chat_id)
        current = await get_json(key)
        if current is None:
            return False
        current.update(updates)
        return await set_value(key, current, cls.DEFAULT_EXPIRE)
    
    @classmethod
    async def end_quiz(cls, chat_id: int) -> bool:
        """End group quiz"""
        key = cls._quiz_key(chat_id)
        return await delete_key(key)
    
    @classmethod
    async def is_active(cls, chat_id: int) -> bool:
        """Check if quiz is active in chat"""
        data = await cls.get_quiz(chat_id)
        return data is not None and data.get("active", False)


# ============================================================
# POLL DATA MANAGEMENT
# ============================================================

class PollDataManager:
    """Manage poll data (question-answer mapping)"""
    
    PREFIX = "poll_data"
    DEFAULT_EXPIRE = 300  # 5 minutes
    
    @classmethod
    async def save_poll(
        cls,
        poll_id: str,
        chat_id: int,
        question_id: int,
        correct_index: int,
        **extra
    ) -> bool:
        """Save poll data"""
        key = f"{cls.PREFIX}:{poll_id}"
        data = {
            "chat_id": chat_id,
            "question_id": question_id,
            "correct_index": correct_index,
            **extra
        }
        return await set_value(key, data, cls.DEFAULT_EXPIRE)
    
    @classmethod
    async def get_poll(cls, poll_id: str) -> Optional[Dict]:
        """Get poll data"""
        key = f"{cls.PREFIX}:{poll_id}"
        return await get_json(key)
    
    @classmethod
    async def delete_poll(cls, poll_id: str) -> bool:
        """Delete poll data"""
        key = f"{cls.PREFIX}:{poll_id}"
        return await delete_key(key)


# ============================================================
# RATE LIMITING
# ============================================================

class RateLimitManager:
    """Redis-based rate limiting"""
    
    PREFIX = "ratelimit"
    
    @classmethod
    async def check_rate_limit(
        cls,
        key: str,
        limit: int,
        window_seconds: int = 60
    ) -> tuple[bool, int]:
        """
        Check rate limit.
        Returns (is_allowed, remaining_requests)
        """
        redis = await get_redis()
        full_key = _key(f"{cls.PREFIX}:{key}")
        
        try:
            # Increment counter
            current = await redis.incr(full_key)
            
            # Set expiration on first request
            if current == 1:
                await redis.expire(full_key, window_seconds)
            
            remaining = max(0, limit - current)
            is_allowed = current <= limit
            
            return is_allowed, remaining
        
        except Exception as e:
            logger.error("Rate limit check error", key=key, error=str(e))
            return True, limit  # Allow on error


# ============================================================
# DUEL MATCHING
# ============================================================

class DuelMatchingManager:
    """Manage duel waiting queue and matching"""
    
    PREFIX = "duel_queue"
    EXPIRE = 300  # 5 minutes
    
    @classmethod
    async def join_queue(
        cls,
        user_id: int,
        language_id: int,
        level_id: Optional[int] = None
    ) -> bool:
        """Add user to duel queue"""
        queue_key = f"{cls.PREFIX}:{language_id}:{level_id or 'any'}"
        redis = await get_redis()
        
        try:
            await redis.sadd(_key(queue_key), str(user_id))
            await redis.expire(_key(queue_key), cls.EXPIRE)
            return True
        except Exception as e:
            logger.error("Duel queue join error", error=str(e))
            return False
    
    @classmethod
    async def find_opponent(
        cls,
        user_id: int,
        language_id: int,
        level_id: Optional[int] = None
    ) -> Optional[int]:
        """Find opponent from queue"""
        queue_key = f"{cls.PREFIX}:{language_id}:{level_id or 'any'}"
        redis = await get_redis()
        
        try:
            # Get all users in queue
            users = await redis.smembers(_key(queue_key))
            
            for uid in users:
                if int(uid) != user_id:
                    # Found opponent - remove both from queue
                    await redis.srem(_key(queue_key), uid, str(user_id))
                    return int(uid)
            
            return None
        except Exception as e:
            logger.error("Find opponent error", error=str(e))
            return None
    
    @classmethod
    async def leave_queue(
        cls,
        user_id: int,
        language_id: int,
        level_id: Optional[int] = None
    ) -> bool:
        """Remove user from queue"""
        queue_key = f"{cls.PREFIX}:{language_id}:{level_id or 'any'}"
        redis = await get_redis()
        
        try:
            await redis.srem(_key(queue_key), str(user_id))
            return True
        except Exception as e:
            logger.error("Leave queue error", error=str(e))
            return False


# ============================================================
# CACHE
# ============================================================

class CacheManager:
    """Simple cache manager"""
    
    PREFIX = "cache"
    
    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """Get cached value"""
        return await get_json(f"{cls.PREFIX}:{key}")
    
    @classmethod
    async def set(cls, key: str, value: Any, expire: int = 300) -> bool:
        """Set cached value"""
        return await set_value(f"{cls.PREFIX}:{key}", value, expire)
    
    @classmethod
    async def delete(cls, key: str) -> bool:
        """Delete cached value"""
        return await delete_key(f"{cls.PREFIX}:{key}")
    
    @classmethod
    async def get_or_set(
        cls,
        key: str,
        factory,
        expire: int = 300
    ) -> Any:
        """Get from cache or compute and cache"""
        cached = await cls.get(key)
        if cached is not None:
            return cached
        
        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        # Cache and return
        await cls.set(key, value, expire)
        return value


from datetime import datetime
import asyncio
