from decimal import Decimal

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.menu_repository import MenuRepository
from app.repositories.user_address_repository import UserAddressRepository
from app.repositories.wallet_repository import WalletRepository
from app.repositories.extra_order_repository import ExtraOrderRepository
from app.repositories.package_capacity_repository import PackageCapacityRepository
from app.repositories.cart_repository import CartRepository


class ExtraOrderService:

    @staticmethod
    def place_order(
        db: Session,
        user_id: str,
        payload
    ):
        # 1. Validate delivery address belongs to user
        address = UserAddressRepository.get_by_id(
            db,
            payload.address_id
        )

        if not address or str(address.user_reference_id) != user_id:

            raise HTTPException(
                status_code=400,
                detail="Invalid delivery address"
            )

        # 2. Validate every package — active, available, belongs to vendor
        resolved_items = []

        for item in payload.items:

            package = MenuRepository.get_active_package_by_id(
                db,
                item.package_id
            )

            if not package:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Package {item.package_id} "
                        f"not found or unavailable"
                    )
                )

            if str(package.provider_id) != str(payload.vendor_id):

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Package {item.package_id} "
                        f"does not belong to the selected provider. "
                        f"All packages must be from the same provider."
                    )
                )

            # Check provider daily capacity for this package on the delivery date
            PackageCapacityRepository.check_and_raise_extra_order(
                db=db,
                vendor_id=payload.vendor_id,
                package_id=item.package_id,
                package_name=package.package_name,
                requested_qty=item.quantity,
                delivery_date=payload.delivery_date,
                meal_slot=payload.meal_slot.value,
            )

            unit_price = (
                package.price - package.discounted_price
                if package.discounted_price
                else package.price
            )

            resolved_items.append({
                "package_id": package.package_id,
                "unit_price": unit_price,
                "quantity": item.quantity,
                "total_price": unit_price * item.quantity
            })

        # 3. Check the provider's overall daily quota — all packages in this
        # order count against the same per-slot limit
        PackageCapacityRepository.check_and_raise_provider_extra_order(
            db=db,
            vendor_id=payload.vendor_id,
            requested_qty=sum(i["quantity"] for i in resolved_items),
            delivery_date=payload.delivery_date,
            meal_slot=payload.meal_slot.value,
        )

        # 4. Calculate grand total
        grand_total = sum(
            Decimal(str(i["total_price"]))
            for i in resolved_items
        )

        # 5. Check wallet balance
        wallet = WalletRepository.get_by_user_id(
            db,
            user_id
        )

        if not wallet:

            raise HTTPException(
                status_code=400,
                detail="Wallet not found. Please add balance to your wallet."
            )

        if Decimal(str(wallet.balance)) < grand_total:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient wallet balance. "
                    f"Required: {grand_total}, "
                    f"Available: {wallet.balance}"
                )
            )

        # 6. Place all orders, deduct wallet, record transaction — all in one transaction
        try:

            created_orders = []

            first_order_id = None

            for item in resolved_items:

                order_data = {
                    "user_reference_id": user_id,
                    "vendor_reference_id": str(payload.vendor_id),
                    "address_reference_id": str(payload.address_id),
                    "package_reference_id": str(item["package_id"]),
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "total_price": item["total_price"],
                    "delivery_date": payload.delivery_date,
                    "meal_slot": payload.meal_slot.value,
                    "status": "pending"
                }

                order = ExtraOrderRepository.create_order(
                    db,
                    order_data
                )

                created_orders.append(order)

                if first_order_id is None:

                    first_order_id = order.extra_order_id

            balance_before = Decimal(str(wallet.balance))

            WalletRepository.deduct_balance(
                db,
                wallet,
                grand_total
            )

            balance_after = Decimal(str(wallet.balance))

            txn_data = {
                "wallet_reference_id": str(wallet.wallet_id),
                "user_reference_id": user_id,
                "type": "debit",
                "reason": "order_placed",
                "amount": grand_total,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "reference_id": first_order_id,
                "reference_type": "extra_order"
            }

            WalletRepository.create_transaction(
                db,
                txn_data
            )

            # Remove ordered packages from cart
            ordered_package_ids = [str(i["package_id"]) for i in resolved_items]
            CartRepository.delete_by_package_ids(db, user_id, ordered_package_ids)

            db.commit()

            for order in created_orders:

                db.refresh(order)

            return {
                "success": True,
                "message": "Order placed successfully",
                "total_amount": grand_total,
                "wallet_balance_after": balance_after,
                "orders": created_orders
            }

        except HTTPException:

            db.rollback()

            raise

        except Exception as e:

            db.rollback()

            raise HTTPException(
                status_code=500,
                detail=f"Order placement failed: {str(e)}"
            )

    @staticmethod
    def get_order_list(
        db: Session,
        user_id: str
    ):

        orders = ExtraOrderRepository.get_all_by_user(
            db,
            user_id
        )

        return {
            "success": True,
            "total": len(orders),
            "orders": orders
        }

    @staticmethod
    def get_order(
        db: Session,
        user_id: str,
        order_id: str
    ):

        order = ExtraOrderRepository.get_by_id(
            db,
            order_id
        )

        if not order:

            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        if str(order.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return order
