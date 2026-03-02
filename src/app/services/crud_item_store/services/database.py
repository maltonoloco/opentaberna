"""
Item Database Service

Database operations for the item-store service.
Uses the generic BaseRepository with item-specific queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.database import ItemDB


class ItemRepository(BaseRepository[ItemDB]):
    """
    Repository for Item database operations.

    Extends BaseRepository with item-specific queries like:
    - Get by SKU
    - Get by slug
    - Search by status
    - Category filtering
    """

    def __init__(self, session: AsyncSession):
        """Initialize item repository with session."""
        super().__init__(ItemDB, session)

    async def get_by_sku(self, sku: str) -> Optional[ItemDB]:
        """
        Get item by SKU (Stock Keeping Unit).

        Args:
            sku: Stock Keeping Unit

        Returns:
            Item or None if not found

        Example:
            >>> item = await repo.get_by_sku("CHAIR-RED-001")
        """
        return await self.get_by(sku=sku)

    async def get_by_slug(self, slug: str) -> Optional[ItemDB]:
        """
        Get item by URL slug.

        Args:
            slug: URL-friendly identifier

        Returns:
            Item or None if not found

        Example:
            >>> item = await repo.get_by_slug("red-wooden-chair")
        """
        return await self.get_by(slug=slug)

    async def get_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> list[ItemDB]:
        """
        Get items by status with pagination.

        Args:
            status: Item status (draft, active, archived)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of items

        Example:
            >>> active_items = await repo.get_by_status("active", skip=0, limit=20)
        """
        return await self.get_all(skip=skip, limit=limit, status=status)

    async def search_by_name(self, query: str, limit: int = 100) -> list[ItemDB]:
        """
        Search items by name (case-insensitive).

        Args:
            query: Search term
            limit: Maximum number of results

        Returns:
            List of matching items

        Example:
            >>> items = await repo.search_by_name("chair")
        """
        stmt = (
            select(self.model).where(self.model.name.ilike(f"%{query}%")).limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_category(
        self, category_uuid: UUID, skip: int = 0, limit: int = 100
    ) -> list[ItemDB]:
        """
        Get items in a specific category.

        Args:
            category_uuid: Category UUID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of items in category

        Example:
            >>> items = await repo.get_by_category(UUID("2f61e8db..."))
        """
        # Query JSONB array for category UUID
        stmt = (
            select(self.model)
            .where(self.model.categories.contains([str(category_uuid)]))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def sku_exists(self, sku: str, exclude_uuid: Optional[UUID] = None) -> bool:
        """
        Check if SKU already exists.

        Args:
            sku: SKU to check
            exclude_uuid: Optionally exclude an item UUID (for updates)

        Returns:
            True if SKU exists, False otherwise

        Example:
            >>> exists = await repo.sku_exists("CHAIR-RED-001")
        """
        stmt = select(self.model.uuid).where(self.model.sku == sku)
        if exclude_uuid:
            stmt = stmt.where(self.model.uuid != exclude_uuid)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def slug_exists(self, slug: str, exclude_uuid: Optional[UUID] = None) -> bool:
        """
        Check if slug already exists.

        Args:
            slug: Slug to check
            exclude_uuid: Optionally exclude an item UUID (for updates)

        Returns:
            True if slug exists, False otherwise

        Example:
            >>> exists = await repo.slug_exists("red-wooden-chair")
        """
        stmt = select(self.model.uuid).where(self.model.slug == slug)
        if exclude_uuid:
            stmt = stmt.where(self.model.uuid != exclude_uuid)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


def get_item_repository(session: AsyncSession) -> ItemRepository:
    """
    Dependency injection factory for ItemRepository.

    Args:
        session: Database session (typically from FastAPI dependency)

    Returns:
        ItemRepository instance

    Example:
        >>> # In FastAPI router
        >>> @router.get("/items/{uuid}")
        >>> async def get_item(
        ...     uuid: UUID,
        ...     session: AsyncSession = Depends(get_session),
        ... ):
        ...     repo = get_item_repository(session)
        ...     return await repo.get(uuid)
    """
    return ItemRepository(session)
