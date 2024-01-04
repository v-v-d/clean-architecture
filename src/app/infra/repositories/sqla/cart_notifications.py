from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cart_notifications.entities import CartNotification
from app.domain.interfaces.repositories.cart_notifications import (
    ICartNotificationsRepository,
)
from app.infra.repositories.sqla import models


class CartsNotificationsRepository(ICartNotificationsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, cart_notification: CartNotification) -> CartNotification:
        stmt = insert(models.CartNotification).values(
            id=cart_notification.id,
            cart_id=cart_notification.cart_id,
            type=cart_notification.type,
            text=cart_notification.text,
            sent_at=cart_notification.sent_at,
        )
        await self._session.execute(stmt)

        return cart_notification
