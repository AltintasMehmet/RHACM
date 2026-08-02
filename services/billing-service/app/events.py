import json
import logging

import aio_pika

from app.config import settings

logger = logging.getLogger(__name__)

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_exchange: aio_pika.abc.AbstractExchange | None = None


async def connect_rabbitmq() -> None:
    """Connect to RabbitMQ and declare the exchange. Logs a warning if unavailable."""
    global _connection, _channel, _exchange
    try:
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        _channel = await _connection.channel()
        _exchange = await _channel.declare_exchange(
            "teleportal.events",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info("Connected to RabbitMQ")
    except Exception:
        logger.warning(
            "Could not connect to RabbitMQ — events will not be published",
            exc_info=True,
        )
        _connection = None
        _channel = None
        _exchange = None


async def publish_event(event_type: str, data: dict) -> None:
    """Publish a JSON event to the teleportal.events exchange.

    Silently logs a warning if RabbitMQ is not available.
    """
    if _exchange is None:
        logger.warning(
            "RabbitMQ not connected — skipping event: %s", event_type
        )
        return
    try:
        message = aio_pika.Message(
            body=json.dumps(data, default=str).encode(),
            content_type="application/json",
        )
        await _exchange.publish(message, routing_key=event_type)
        logger.info("Published event: %s", event_type)
    except Exception:
        logger.warning(
            "Failed to publish event %s", event_type, exc_info=True
        )


async def close_rabbitmq() -> None:
    """Close the RabbitMQ connection gracefully."""
    global _connection, _channel, _exchange
    try:
        if _connection and not _connection.is_closed:
            await _connection.close()
            logger.info("RabbitMQ connection closed")
    except Exception:
        logger.warning("Error closing RabbitMQ connection", exc_info=True)
    finally:
        _connection = None
        _channel = None
        _exchange = None


async def rabbitmq_healthy() -> bool:
    """Return True if the RabbitMQ connection is alive."""
    return _connection is not None and not _connection.is_closed
