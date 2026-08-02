import json
import logging
from datetime import datetime, timezone

import aio_pika

from app.config import settings
from app.database import async_session_factory
from app.models import Notification

logger = logging.getLogger(__name__)

_connection: aio_pika.abc.AbstractRobustConnection | None = None


async def _save_notification(
    subscriber_id: str,
    notification_type: str,
    channel: str,
    subject: str,
    body: str,
) -> None:
    """Persist a notification and mark it as sent (demo mode)."""
    async with async_session_factory() as session:
        notification = Notification(
            subscriber_id=subscriber_id,
            notification_type=notification_type,
            channel=channel,
            subject=subject,
            body=body,
            status="sent",
            sent_at=datetime.now(timezone.utc),
        )
        session.add(notification)
        await session.commit()
        logger.info(
            "[DEMO SEND] %s notification via %s to subscriber %s: %s",
            notification_type,
            channel,
            subscriber_id,
            subject,
        )


async def consume_subscriber_events() -> None:
    """Listen for subscriber.created and subscriber.status_changed events."""
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            "teleportal.events",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            "notification.subscriber", durable=True
        )
        await queue.bind(exchange, routing_key="subscriber.created")
        await queue.bind(exchange, routing_key="subscriber.status_changed")

        logger.info("Subscriber event consumer started")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body)
                        routing_key = message.routing_key

                        subscriber_id = data.get("subscriber_id", "unknown")

                        if routing_key == "subscriber.created":
                            await _save_notification(
                                subscriber_id=subscriber_id,
                                notification_type="welcome",
                                channel="email",
                                subject="Welcome to TelePortal!",
                                body=(
                                    f"Welcome aboard! Your account has been "
                                    f"created successfully. Subscriber ID: "
                                    f"{subscriber_id}"
                                ),
                            )
                        elif routing_key == "subscriber.status_changed":
                            old_status = data.get("old_status", "unknown")
                            new_status = data.get("new_status", "unknown")
                            await _save_notification(
                                subscriber_id=subscriber_id,
                                notification_type="status_change",
                                channel="email",
                                subject="Account Status Changed",
                                body=(
                                    f"Your account status has changed from "
                                    f"{old_status} to {new_status}."
                                ),
                            )
                    except Exception:
                        logger.exception(
                            "Error processing subscriber event"
                        )
    except Exception:
        logger.warning(
            "Subscriber event consumer failed to start — "
            "RabbitMQ may be unavailable",
            exc_info=True,
        )


async def consume_usage_events() -> None:
    """Listen for usage.threshold_reached events."""
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            "teleportal.events",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            "notification.usage", durable=True
        )
        await queue.bind(exchange, routing_key="usage.threshold_reached")

        logger.info("Usage event consumer started")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body)
                        subscriber_id = data.get("subscriber_id", "unknown")
                        usage_pct = data.get("usage_percent", "N/A")

                        await _save_notification(
                            subscriber_id=subscriber_id,
                            notification_type="usage_warning",
                            channel="sms",
                            subject="Data Usage Warning",
                            body=(
                                f"You have used {usage_pct}% of your data "
                                f"allowance. Consider upgrading your plan to "
                                f"avoid extra charges."
                            ),
                        )
                    except Exception:
                        logger.exception("Error processing usage event")
    except Exception:
        logger.warning(
            "Usage event consumer failed to start — "
            "RabbitMQ may be unavailable",
            exc_info=True,
        )


async def consume_billing_events() -> None:
    """Listen for invoice.issued events."""
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            "teleportal.events",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            "notification.billing", durable=True
        )
        await queue.bind(exchange, routing_key="invoice.issued")

        logger.info("Billing event consumer started")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body)
                        subscriber_id = data.get("subscriber_id", "unknown")
                        amount = data.get("total_amount_eur", "0.00")
                        invoice_id = data.get("invoice_id", "unknown")

                        await _save_notification(
                            subscriber_id=subscriber_id,
                            notification_type="invoice",
                            channel="email",
                            subject=f"New Invoice #{invoice_id}",
                            body=(
                                f"Your invoice #{invoice_id} for EUR "
                                f"{amount} has been issued. Please review "
                                f"and pay before the due date."
                            ),
                        )
                    except Exception:
                        logger.exception("Error processing billing event")
    except Exception:
        logger.warning(
            "Billing event consumer failed to start — "
            "RabbitMQ may be unavailable",
            exc_info=True,
        )


async def connect_rabbitmq() -> None:
    """Open a shared connection for health checks."""
    global _connection
    try:
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        logger.info("Connected to RabbitMQ (health-check connection)")
    except Exception:
        logger.warning(
            "Could not connect to RabbitMQ — consumers will not run",
            exc_info=True,
        )
        _connection = None


async def close_rabbitmq() -> None:
    """Close the shared RabbitMQ connection."""
    global _connection
    try:
        if _connection and not _connection.is_closed:
            await _connection.close()
            logger.info("RabbitMQ connection closed")
    except Exception:
        logger.warning("Error closing RabbitMQ connection", exc_info=True)
    finally:
        _connection = None


async def rabbitmq_healthy() -> bool:
    """Return True if the RabbitMQ connection is alive."""
    return _connection is not None and not _connection.is_closed
