from decimal import Decimal
from logging import getLogger

from app.app_layer.interfaces.auth_system.dto import UserDataOutputDTO
from app.app_layer.interfaces.auth_system.system import IAuthSystem
from app.app_layer.interfaces.clients.products.client import IProductsClient
from app.app_layer.interfaces.distributed_lock_system.system import IDistributedLockSystem
from app.app_layer.interfaces.unit_of_work.sql import IUnitOfWork
from app.app_layer.use_cases.cart_items.dto import AddItemToCartInputDTO
from app.app_layer.use_cases.carts.dto import CartOutputDTO
from app.domain.cart_items.dto import ItemDTO
from app.domain.cart_items.entities import CartItem
from app.domain.carts.entities import Cart
from app.domain.carts.exceptions import CartItemDoesNotExistError
from app.logging import update_context

logger = getLogger(__name__)


class AddCartItemUseCase:
    """
    Responsible for adding an item to a cart. It interacts with various dependencies
    such as the unit of work, products client, authentication system, and distributed
    lock system to perform this task.
    """

    def __init__(
        self,
        uow: IUnitOfWork,
        products_client: IProductsClient,
        auth_system: IAuthSystem,
        distributed_lock_system: IDistributedLockSystem,
    ) -> None:
        self._uow = uow
        self._products_client = products_client
        self._auth_system = auth_system
        self._distributed_lock_system = distributed_lock_system

    async def execute(self, data: AddItemToCartInputDTO) -> CartOutputDTO:
        """
        Executes the use case by adding an item to the cart. It acquires a distributed
        lock, retrieves user data, retrieves the cart, checks user ownership, updates
        the cart, commits the changes, and returns the updated cart.
        """

        await update_context(cart_id=data.cart_id)

        async with self._distributed_lock_system(name=f"cart-lock-{data.cart_id}"):
            return await self._add_item_to_cart(data=data)

    async def _add_item_to_cart(self, data: AddItemToCartInputDTO) -> CartOutputDTO:
        user = await self._auth_system.get_user_data(auth_data=data.auth_data)

        async with self._uow(autocommit=False):
            cart = await self._uow.carts.retrieve(cart_id=data.cart_id)
            await self._uow.commit()

            self._check_user_ownership(cart=cart, user=user)
            cart = await self._update_cart(cart=cart, data=data)

            await self._uow.commit()

        return CartOutputDTO.model_validate(cart)

    def _check_user_ownership(self, cart: Cart, user: UserDataOutputDTO) -> None:
        if user.is_admin:
            return

        cart.check_user_ownership(user_id=user.id)

    async def _update_cart(self, cart: Cart, data: AddItemToCartInputDTO) -> Cart:
        try:
            await self._increase_item_qty(cart=cart, item_id=data.id, qty=data.qty)
        except CartItemDoesNotExistError:
            cart = await self._try_to_add_new_item_to_cart(cart=cart, data=data)

        return cart

    async def _try_to_add_new_item_to_cart(
        self,
        cart: Cart,
        data: AddItemToCartInputDTO,
    ) -> Cart:
        item = await self._try_to_create_item(cart=cart, data=data)
        cart.add_new_item(item)
        await self._uow.items.add_item(item=item)

        logger.info(
            "Item %s successfully added to cart %s with qty %s",
            item.id,
            cart.id,
            data.qty,
        )

        return cart

    async def _try_to_create_item(
        self,
        cart: Cart,
        data: AddItemToCartInputDTO,
    ) -> CartItem:
        product = await self._products_client.get_product(item_id=data.id)

        return CartItem(
            data=ItemDTO(
                id=data.id,
                qty=data.qty,
                name=product.title,
                price=product.price,
                is_weight=False,  # hardcoded just for example
                cart_id=cart.id,
            ),
        )

    async def _increase_item_qty(self, cart: Cart, item_id: int, qty: Decimal) -> Cart:
        item = cart.increase_item_qty(item_id=item_id, qty=qty)
        await self._uow.items.update_item(item=item)

        logger.info(
            "Cart %s. Item %s qty successfully increased. Current item qty %s",
            cart.id,
            item_id,
            qty,
        )

        return cart
