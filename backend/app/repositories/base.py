"""Generic base repository with reusable CRUD operations."""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Thin data-access layer over SQLAlchemy.

    Subclasses add domain-specific queries.
    All mutations go through the session so the caller controls commits.
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
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def create_many(self, objs: List[T]) -> List[T]:
        self.db.add_all(objs)
        self.db.commit()
        for obj in objs:
            self.db.refresh(obj)
        return objs

    def update(self, obj: T) -> T:
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, id: int) -> bool:
        obj = self.get(id)
        if obj:
            self.db.delete(obj)
            self.db.commit()
            return True
        return False
