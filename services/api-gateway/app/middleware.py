import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.3fs) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            request_id,
        )
        return response


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures: dict[str, int] = {}
        self._open_since: dict[str, float] = {}

    def is_open(self, service: str) -> bool:
        if service not in self._open_since:
            return False
        if time.time() - self._open_since[service] > self.reset_timeout:
            self._failures.pop(service, None)
            self._open_since.pop(service, None)
            return False
        return True

    def record_failure(self, service: str):
        self._failures[service] = self._failures.get(service, 0) + 1
        if self._failures[service] >= self.failure_threshold:
            self._open_since[service] = time.time()

    def record_success(self, service: str):
        self._failures.pop(service, None)
        self._open_since.pop(service, None)


circuit_breaker = CircuitBreaker()
