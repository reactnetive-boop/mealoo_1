from fastapi import HTTPException

from app.models.menu_package_item_model import (
    MenuPackageItem
)

from app.repositories.package_item_repository import (
    PackageItemRepository
)

from app.repositories.menu_repository import (
    MenuRepository
)


class PackageItemService:

    @staticmethod
    def add_package_item(
        db,
        request
    ):

        package = MenuRepository.get_package_by_id(
            db,
            request.package_id
        )

        if not package:

            raise HTTPException(
                status_code=404,
                detail="Package not found"
            )

        package_item = MenuPackageItem(
            package_reference_id=request.package_id,
            item_name=request.item_name,
            quantity=request.quantity,
            item_order=request.item_order
        )

        package_item = (
            PackageItemRepository.create_package_item(
                db,
                package_item
            )
        )

        return {
            "success": True,
            "message": "Package item added successfully",
            "item_id": package_item.item_id
        }


    @staticmethod
    def update_package_item(
        db,
        item_id,
        request
    ):

        package_item = (
            PackageItemRepository.get_item_by_id(
                db,
                item_id
            )
        )

        if not package_item:

            raise HTTPException(
                status_code=404,
                detail="Package item not found"
            )

        if request.item_name is not None:
            package_item.item_name = request.item_name

        if request.quantity is not None:
            package_item.quantity = request.quantity

        if request.item_order is not None:
            package_item.item_order = request.item_order

        db.commit()

        db.refresh(package_item)

        return {
            "success": True,
            "message": "Package item updated successfully"
        }


    @staticmethod
    def delete_package_item(
        db,
        item_id
    ):

        package_item = (
            PackageItemRepository.get_item_by_id(
                db,
                item_id
            )
        )

        if not package_item:

            raise HTTPException(
                status_code=404,
                detail="Package item not found"
            )

        PackageItemRepository.delete_package_item(
            db,
            package_item
        )

        return {
            "success": True,
            "message": "Package item deleted successfully"
        }