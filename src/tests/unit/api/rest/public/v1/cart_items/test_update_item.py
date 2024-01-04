from decimal import Decimal
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from _pytest.fixtures import SubRequest
from fastapi import FastAPI
from httpx import AsyncClient
from pytest_mock import MockerFixture

from app.app_layer.interfaces.auth_system.exceptions import InvalidAuthDataError
from app.app_layer.interfaces.use_cases.cart_items.add_item import IAddCartItemUseCase
from app.app_layer.interfaces.use_cases.carts.dto import CartOutputDTO, ItemOutputDTO
from app.domain.cart_items.exceptions import MinQtyLimitExceededError
from app.domain.carts.exceptions import (
    CartItemDoesNotExistError,
    MaxItemsQtyLimitExceeded,
    NotOwnedByUserError,
    OperationForbiddenError,
    SpecificItemQtyLimitExceeded,
)
from app.domain.carts.value_objects import CartStatusEnum
from app.domain.interfaces.repositories.carts.exceptions import CartNotFoundError
from tests.utils import fake


@pytest.fixture()
def item_id() -> int:
    return fake.numeric.integer_number(start=1)


@pytest.fixture()
def url_path(cart_id: UUID, item_id: int) -> str:
    return f"api/v1/carts/{cart_id}/items/{item_id}"


@pytest.fixture()
def use_case(request: SubRequest, mocker: MockerFixture) -> AsyncMock:
    mock = mocker.AsyncMock(spec=IAddCartItemUseCase)

    if "returns" in request.param:
        mock.execute.return_value = request.param["returns"]
    elif "raises" in request.param:
        mock.execute.side_effect = request.param["raises"]

    return mock


@pytest.fixture()
def application(application: FastAPI, use_case: AsyncMock) -> FastAPI:
    with application.container.update_cart_item_use_case.override(use_case):
        yield application


@pytest.mark.parametrize(
    "use_case",
    [
        {
            "returns": CartOutputDTO(
                created_at=fake.datetime.datetime(),
                id=fake.cryptographic.uuid_object(),
                user_id=fake.numeric.integer_number(start=1),
                status=CartStatusEnum.OPENED,
                items=[
                    ItemOutputDTO(
                        id=fake.numeric.integer_number(start=1),
                        name=fake.text.word(),
                        qty=fake.numeric.integer_number(start=1),
                        price=fake.numeric.integer_number(start=1),
                        cost=fake.numeric.integer_number(start=1),
                        is_weight=fake.random.choice([False, True]),
                    ),
                ],
                items_qty=0,
                cost=0,
                checkout_enabled=False,
                coupon=None,
            ),
        }
    ],
    indirect=True,
)
async def test_ok(http_client: AsyncClient, use_case: AsyncMock, url_path: str) -> None:
    response = await http_client.patch(
        url=url_path,
        json=fake.numeric.integer_number(start=1),
    )

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == {
        "id": str(use_case.execute.return_value.id),
        "user_id": use_case.execute.return_value.user_id,
        "status": use_case.execute.return_value.status.value,
        "items": [
            {
                "id": use_case.execute.return_value.items[0].id,
                "title": use_case.execute.return_value.items[0].name,
                "quantity": float(use_case.execute.return_value.items[0].qty),
                "price": float(use_case.execute.return_value.items[0].price),
                "cost": float(use_case.execute.return_value.items[0].cost),
                "is_weight": use_case.execute.return_value.items[0].is_weight,
            },
        ],
        "items_quantity": float(use_case.execute.return_value.items_qty),
        "cost": float(use_case.execute.return_value.cost),
        "checkout_enabled": use_case.execute.return_value.checkout_enabled,
        "coupon": use_case.execute.return_value.coupon,
    }


@pytest.mark.parametrize(
    ("use_case", "expected_code", "expected_error"),
    [
        pytest.param(
            {"raises": InvalidAuthDataError},
            HTTPStatus.UNAUTHORIZED,
            {"detail": {"code": 1000, "message": "Authorization failed."}},
            id="UNAUTHORIZED",
        ),
        pytest.param(
            {"raises": CartNotFoundError},
            HTTPStatus.BAD_REQUEST,
            {"detail": {"code": 2000, "message": "Cart not found."}},
            id="CART_NOT_FOUND",
        ),
        pytest.param(
            {"raises": NotOwnedByUserError},
            HTTPStatus.BAD_REQUEST,
            {"detail": {"code": 1001, "message": "Forbidden."}},
            id="FORBIDDEN",
        ),
        pytest.param(
            {"raises": OperationForbiddenError},
            HTTPStatus.BAD_REQUEST,
            {"detail": {"code": 2003, "message": "The cart can't be modified."}},
            id="OPERATION_FORBIDDEN",
        ),
        pytest.param(
            {"raises": CartItemDoesNotExistError},
            HTTPStatus.BAD_REQUEST,
            {"detail": {"code": 3002, "message": "Failed to update cart item."}},
            id="ITEM_NOT_FOUND",
        ),
        pytest.param(
            {"raises": MinQtyLimitExceededError},
            HTTPStatus.BAD_REQUEST,
            {"detail": {"code": 3002, "message": "Failed to update cart item."}},
            id="MIN_QTY_LIMIT_EXCEEDED",
        ),
        pytest.param(
            {"raises": SpecificItemQtyLimitExceeded(limit=Decimal(5), actual=Decimal(6))},
            HTTPStatus.BAD_REQUEST,
            {
                "detail": {
                    "code": 2004,
                    "message": "Item qty limit exceeded. Limit: 5, got: 6.",
                }
            },
            id="ITEM_QTY_LIMIT_EXCEEDED",
        ),
        pytest.param(
            {"raises": MaxItemsQtyLimitExceeded},
            HTTPStatus.BAD_REQUEST,
            {"detail": {"code": 3001, "message": "Max cart items qty limit exceeded."}},
            id="MAX_ITEMS_QTY_LIMIT_EXCEEDED",
        ),
    ],
    indirect=["use_case"],
)
async def test_failed(
    http_client: AsyncClient,
    use_case: AsyncMock,
    url_path: str,
    expected_code: int,
    expected_error: dict[str, Any],
) -> None:
    response = await http_client.patch(
        url=url_path,
        json=fake.numeric.integer_number(start=1),
    )

    assert response.status_code == expected_code, response.text
    assert response.json() == expected_error