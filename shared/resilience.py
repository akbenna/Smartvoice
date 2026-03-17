"""
Resilience Patronen
===================
Retry met exponential backoff en circuit breaker voor externe services.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Type

import structlog

logger = structlog.get_logger()


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normaal functionerend
    OPEN = "open"           # Service onbereikbaar, blokkeer calls
    HALF_OPEN = "half_open" # Test of service weer werkt


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5       # Aantal fouten voor OPEN
    recovery_timeout: float = 30.0   # Seconden wachten voor HALF_OPEN
    success_threshold: int = 2       # Successen nodig voor CLOSED vanuit HALF_OPEN


class CircuitBreaker:
    """
    Circuit breaker voor bescherming tegen cascade failures.

    Gebruik:
        cb = CircuitBreaker("ollama", CircuitBreakerConfig(failure_threshold=3))

        async with cb:
            result = await ollama_call()
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            # Check of recovery timeout verlopen is
            if time.monotonic() - self._last_failure_time >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("Circuit breaker HALF_OPEN", name=self.name)
        return self._state

    async def __aenter__(self):
        async with self._lock:
            if self.state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Wacht {self.config.recovery_timeout}s voor herstel."
                )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type is None:
                self._on_success()
            else:
                self._on_failure()
        return False  # Don't suppress exceptions

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("Circuit breaker CLOSED (hersteld)", name=self.name)
        else:
            self._failure_count = 0

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN (vanuit HALF_OPEN)", name=self.name)
        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN",
                         name=self.name,
                         failures=self._failure_count)

    def reset(self):
        """Handmatig resetten."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0


class CircuitOpenError(Exception):
    """Raised wanneer circuit breaker OPEN is."""
    pass


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0          # Seconden
    max_delay: float = 30.0          # Maximum wachttijd
    exponential_base: float = 2.0
    retryable_exceptions: tuple[Type[Exception], ...] = (
        ConnectionError, TimeoutError, OSError,
    )


async def retry_async(
    func: Callable,
    *args,
    config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs,
) -> Any:
    """
    Voer een async functie uit met retry en optioneel circuit breaker.

    Args:
        func: Async functie om uit te voeren
        config: Retry configuratie
        circuit_breaker: Optioneel circuit breaker

    Returns:
        Resultaat van de functie
    """
    config = config or RetryConfig()
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            if circuit_breaker:
                async with circuit_breaker:
                    return await func(*args, **kwargs)
            else:
                return await func(*args, **kwargs)

        except CircuitOpenError:
            raise  # Don't retry circuit open errors

        except config.retryable_exceptions as e:
            last_exception = e
            if attempt < config.max_retries:
                delay = min(
                    config.base_delay * (config.exponential_base ** attempt),
                    config.max_delay,
                )
                logger.warning(
                    "Retry poging",
                    attempt=attempt + 1,
                    max_retries=config.max_retries,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Alle retries mislukt",
                    attempts=config.max_retries + 1,
                    error=str(e),
                )
                raise

        except Exception:
            raise  # Non-retryable exceptions passeren direct

    raise last_exception


def with_retry(config: RetryConfig | None = None, circuit_breaker: CircuitBreaker | None = None):
    """
    Decorator voor retry met exponential backoff.

    Gebruik:
        @with_retry(RetryConfig(max_retries=3))
        async def call_ollama():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(func, *args, config=config, circuit_breaker=circuit_breaker, **kwargs)
        return wrapper
    return decorator
