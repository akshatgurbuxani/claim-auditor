"""Generic base repository with reusable CRUD operations."""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Thin data-access layer over SQLAlchemy.

    Subclasses add domain-specific queries.
    Repositories only modify the session (add/delete/flush) - the caller
    controls when to commit or rollback, enabling multi-step transactions.
    """

    def __init__(self, db: Session, model: Type[T]):
        self.db = db
        self.model = model

    # ── reads ────────────────────────────────────────────────────────

    def get(self, id: int) -> Optional[T]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, *, skip: int = 0, limit: int = 100) -> List[T]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def count(self) -> int:
        return self.db.query(self.model).count()

    # ── writes ───────────────────────────────────────────────────────

    def create(self, obj: T) -> T:
        """Add object to session (caller must commit)."""
        self.db.add(obj)
        self.db.flush()  # Assigns ID without committing
        return obj

    def create_many(self, objs: List[T]) -> List[T]:
        """Add multiple objects to session (caller must commit)."""
        self.db.add_all(objs)
        self.db.flush()  # Assigns IDs without committing
        return objs

    def update(self, obj: T) -> T:
        """Mark object as modified (caller must commit).

        SQLAlchemy's session already tracks changes to attached objects,
        so this method just flushes to validate constraints.
        """
        self.db.flush()
        return obj

    def delete(self, id: int) -> bool:
        """Mark object for deletion (caller must commit)."""
        obj = self.get(id)
        if obj:
            self.db.delete(obj)
            self.db.flush()
            return True
        return False
