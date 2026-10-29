"""
Payment service - starts payments, reads them and applies the provider's results.

Follows the flowcharts in docs/diagrams: 02 (start a payment), 03 (webhook)
and 04 (read the status). Every check raises an ApiError with its own code,
so every edge case is visible in the API response and in the logs.
"""

import uuid
from dataclasses import asdict
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.db.constants import CartStatus, PaymentStatus, ProviderResult
from app.db.models import Cart, Payment, Product, UserPaymentMethod
from app.db.repositories import (
    CartItemRepository,
    CartRepository,
    PaymentRepository,
    ProductRepository,
    UserPaymentMethodRepository,
    UserRepository,
)
from app.db.session import get_session
from app.log.action_logger import action_logger
from app.schemas import CartUpdate, PaymentCreate, PaymentUpdate, ProductUpdate
from app.schemas.payment import WebhookBody
from app.services.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    PaymentRefusedError,
    ProviderUnavailableError,
)
from app.services.payment_provider import (
    ChargeRefused,
    ChargeRequest,
    MockPaymentProvider,
    PaymentProvider,
)
from app.services.total_calculation import (
    LineItem,
    StubTotalCalculationService,
    TotalCalculationService,
)


class PaymentService:
    """
    Payment use cases. The external services are injected, so the real ones
    can replace the stub and the mock without changing this class.
    """

    def __init__(
        self,
        session: Session,
        total_calculation: TotalCalculationService,
        provider: PaymentProvider,
    ):
        self.session = session
        self.total_calculation = total_calculation
        self.provider = provider

    # ========================================================================
    # USE CASES
    # ========================================================================

    def start_payment(
        self, cart_id: uuid.UUID, user_id: uuid.UUID, payment_method_id: uuid.UUID
    ) -> Payment:
        """
        Start the payment of a cart (diagram 02).

        The pending payment and the stock reservation are committed before
        the provider is called, so the provider call never holds the locks.
        If the provider refuses or fails, a second transaction marks the
        payment as failed and gives the stock back.

        Args:
            cart_id: Cart to pay
            user_id: User making the request (User-Id header)
            payment_method_id: Payment method chosen by the user

        Returns:
            The pending payment, with the provider transaction id

        Raises:
            NotFoundError, ConflictError: a check failed (nothing changed)
            PaymentRefusedError: the provider refused the charge
            ProviderUnavailableError: the provider is unavailable
        """
        payment, provider_token = self._create_pending_payment(cart_id, user_id, payment_method_id)
        charge = ChargeRequest(payment.id, provider_token, payment.amount, payment.currency)

        try:
            transaction_id = self._start_charge(charge)
        except ChargeRefused as error:
            self._fail_payment(payment.id, str(error))
            raise PaymentRefusedError(
                ErrorCode.PAYMENT_REFUSED, f"The payment provider refused the charge: {error}."
            ) from error
        except Exception as error:
            # Any other provider failure: the payment must not stay pending
            # with the stock reserved.
            self._fail_payment(payment.id, str(error) or type(error).__name__)
            raise ProviderUnavailableError(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "The payment provider is unavailable. Please try again later.",
            ) from error

        with PaymentRepository(self.session) as payments:
            return payments.update(
                payment.id, PaymentUpdate(provider_transaction_id=transaction_id)
            )

    def get_payment(
        self, cart_id: uuid.UUID, user_id: uuid.UUID, payment_id: uuid.UUID
    ) -> Payment:
        """
        Read a payment of the user's cart (diagram 04).

        Raises:
            NotFoundError: the cart or the payment doesn't exist for this user
        """
        with CartRepository(self.session) as carts, PaymentRepository(self.session) as payments:
            self._get_user_cart(carts, cart_id, user_id)
            payment = payments.get_for_cart(payment_id, cart_id)

            if payment is None:
                raise NotFoundError(ErrorCode.PAYMENT_NOT_FOUND, "Payment not found for this cart.")

            return payment

    def apply_provider_result(self, result: WebhookBody) -> Payment:
        """
        Apply the result of a charge reported by the provider (diagram 03).

        The signature is checked by the API before this is called.

        Raises:
            NotFoundError: the payment doesn't exist
            ConflictError: the payment is not pending anymore
        """
        with (
            PaymentRepository(self.session) as payments,
            CartRepository(self.session) as carts,
            ProductRepository(self.session) as products,
        ):
            payment = payments.get_by_id(result.payment_id, for_update=True)

            if payment is None:
                raise NotFoundError(ErrorCode.PAYMENT_NOT_FOUND, "Payment not found.")

            if payment.status != PaymentStatus.PENDING.value:
                raise ConflictError(
                    ErrorCode.PAYMENT_NOT_PENDING, f"The payment is already {payment.status}."
                )

            if result.status is ProviderResult.FAILED:
                return self._mark_failed(
                    payments,
                    products,
                    payment,
                    result.failure_reason,
                    result.provider_transaction_id,
                )

            carts.update(payment.cart_id, CartUpdate(status=CartStatus.CHECKED_OUT))

            return payments.update(
                payment.id,
                PaymentUpdate(
                    status=PaymentStatus.SUCCEEDED,
                    provider_transaction_id=result.provider_transaction_id,
                ),
            )

    # ========================================================================
    # START PAYMENT STEPS
    # ========================================================================

    def _create_pending_payment(
        self, cart_id: uuid.UUID, user_id: uuid.UUID, payment_method_id: uuid.UUID
    ) -> tuple[Payment, str]:
        """
        Run every check of diagram 02, reserve the stock and save the pending payment.

        Returns:
            The pending payment and the card token to charge
        """
        with (
            UserRepository(self.session) as users,
            CartRepository(self.session) as carts,
            PaymentRepository(self.session) as payments,
            UserPaymentMethodRepository(self.session) as methods,
            ProductRepository(self.session) as products,
        ):
            if users.get_by_id(user_id) is None:
                raise NotFoundError(ErrorCode.USER_NOT_FOUND, "User not found.")

            cart = self._get_user_cart(carts, cart_id, user_id, for_update=True)

            if cart.status != CartStatus.ACTIVE.value:
                raise ConflictError(
                    ErrorCode.CART_NOT_ACTIVE, f"The cart is {cart.status} and can't be paid."
                )

            if payments.get_active_for_cart(cart.id) is not None:
                raise ConflictError(
                    ErrorCode.ACTIVE_PAYMENT_EXISTS,
                    "The cart already has a pending or succeeded payment.",
                )

            method = self._get_payment_method(methods, payment_method_id, user_id)

            line_items = self._get_line_items(cart.id)
            if not line_items:
                raise ConflictError(ErrorCode.CART_EMPTY, "The cart is empty.")

            quantities = quantities_by_product(line_items)
            locked_products = products.get_many_for_update(quantities)
            currency = self._check_products(quantities, locked_products)

            self._change_stock(products, locked_products, quantities, sign=-1)

            payment = payments.create(
                PaymentCreate(
                    cart_id=cart.id,
                    user_id=user_id,
                    payment_method_id=method.id,
                    payment_type=method.type,
                    amount=sum(item.quantity * item.unit_price for item in line_items),
                    currency=currency,
                )
            )

            return payment, method.provider_token

    def _get_payment_method(
        self,
        methods: UserPaymentMethodRepository,
        payment_method_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UserPaymentMethod:
        """The user's payment method, or 409 if the user has none or it isn't usable."""
        if not methods.has_any_for_user(user_id):
            raise ConflictError(ErrorCode.NO_PAYMENT_METHOD, "The user has no payment method.")

        method = methods.get_for_user(payment_method_id, user_id)

        if method is None:
            raise ConflictError(
                ErrorCode.PAYMENT_METHOD_NOT_FOUND,
                "The payment method doesn't exist or doesn't belong to the user.",
            )

        return method

    def _get_line_items(self, cart_id: uuid.UUID) -> list[LineItem]:
        """Line items from the total calculation service (logged external call)."""
        with action_logger.external_call(
            "total_calculation", "get_line_items", {"cart_id": cart_id}
        ) as call:
            line_items = self.total_calculation.get_line_items(cart_id)
            call.received = [asdict(item) for item in line_items]

        return line_items

    @staticmethod
    def _check_products(
        quantities: dict[uuid.UUID, int], locked_products: dict[uuid.UUID, Product]
    ) -> str:
        """
        Check that every product can be sold, in one currency and in stock.

        Returns:
            The currency of the payment
        """
        if any(
            product_id not in locked_products or locked_products[product_id].deleted
            for product_id in quantities
        ):
            raise ConflictError(
                ErrorCode.PRODUCT_UNAVAILABLE, "A product in the cart is no longer available."
            )

        currencies = {product.currency for product in locked_products.values()}
        if len(currencies) > 1:
            raise ConflictError(
                ErrorCode.MIXED_CURRENCIES,
                f"The cart has products in different currencies: {', '.join(sorted(currencies))}.",
            )

        short = [
            locked_products[product_id].name
            for product_id, quantity in quantities.items()
            if locked_products[product_id].stock_quantity < quantity
        ]
        if short:
            raise ConflictError(
                ErrorCode.INSUFFICIENT_STOCK, f"Not enough stock for: {', '.join(sorted(short))}."
            )

        return currencies.pop()

    def _start_charge(self, charge: ChargeRequest) -> str:
        """Start the charge at the provider (logged external call)."""
        with action_logger.external_call("payment_provider", "start_charge", asdict(charge)) as call:
            transaction_id = self.provider.start_charge(charge)
            call.received = {"transaction_id": transaction_id}

        return transaction_id

    def _fail_payment(self, payment_id: uuid.UUID, failure_reason: str) -> None:
        """Mark a payment that failed when the charge started, in its own transaction."""
        with PaymentRepository(self.session) as payments, ProductRepository(self.session) as products:
            payment = payments.get_by_id(payment_id, for_update=True)
            self._mark_failed(payments, products, payment, failure_reason)

    # ========================================================================
    # SHARED STEPS
    # ========================================================================

    @staticmethod
    def _get_user_cart(
        carts: CartRepository, cart_id: uuid.UUID, user_id: uuid.UUID, for_update: bool = False
    ) -> Cart:
        """The cart, or 404 if it doesn't exist, is deleted or belongs to another user."""
        cart = carts.get_by_id(cart_id, for_update=for_update)

        if cart is None or cart.user_id != user_id:
            raise NotFoundError(ErrorCode.CART_NOT_FOUND, "Cart not found for this user.")

        return cart

    def _mark_failed(
        self,
        payments: PaymentRepository,
        products: ProductRepository,
        payment: Payment,
        failure_reason: str,
        provider_transaction_id: Optional[str] = None,
    ) -> Payment:
        """
        Mark a payment as failed and give its reserved stock back.

        The cart stays active, so the user can retry.
        """
        update = {"status": PaymentStatus.FAILED, "failure_reason": failure_reason}
        if provider_transaction_id is not None:
            update["provider_transaction_id"] = provider_transaction_id

        failed = payments.update(payment.id, PaymentUpdate(**update))

        with CartItemRepository(self.session) as cart_items:
            quantities = quantities_by_product(cart_items.get_by_cart(payment.cart_id))

        self._change_stock(
            products, products.get_many_for_update(quantities), quantities, sign=+1
        )

        return failed

    @staticmethod
    def _change_stock(
        products: ProductRepository,
        locked_products: dict[uuid.UUID, Product],
        quantities: dict[uuid.UUID, int],
        sign: int,
    ) -> None:
        """
        Reserve (sign=-1) or give back (sign=+1) stock, through the repository
        so every change is logged.
        """
        for product_id, quantity in quantities.items():
            product = locked_products[product_id]
            products.update(
                product.id,
                ProductUpdate(stock_quantity=product.stock_quantity + sign * quantity),
            )


def quantities_by_product(items: Iterable) -> dict[uuid.UUID, int]:
    """
    Total quantity per product (a product may appear in more than one item).

    Args:
        items: Objects with product_id and quantity (line items or cart items)

    Returns:
        Quantity by product id
    """
    quantities: dict[uuid.UUID, int] = {}

    for item in items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    return quantities


def build_payment_service() -> PaymentService:
    """Payment service for the current request, with the stub and the mock provider."""
    session = get_session()

    return PaymentService(session, StubTotalCalculationService(session), MockPaymentProvider())
