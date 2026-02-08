"""Unit tests for DiscrepancyPatternModel and DiscrepancyPatternRepository."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.database import Base
from app.models.company import CompanyModel
from app.models.discrepancy_pattern import DiscrepancyPatternModel
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def company(db):
    c = CompanyModel(ticker="AAPL", name="Apple Inc.", sector="Technology")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture()
def company2(db):
    c = CompanyModel(ticker="MSFT", name="Microsoft Corporation", sector="Technology")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


class TestDiscrepancyPatternModel:
    """Test the ORM model itself."""

    def test_create_pattern(self, db, company):
        pattern = DiscrepancyPatternModel(
            company_id=company.id,
            pattern_type="consistent_rounding_up",
            description="Management consistently rounds favorably.",
            affected_quarters=["Q1 2025", "Q2 2025"],
            severity=0.75,
            evidence=["3/4 favorable roundings"],
        )
        db.add(pattern)
        db.commit()
        db.refresh(pattern)

        assert pattern.id is not None
        assert pattern.company_id == company.id
        assert pattern.pattern_type == "consistent_rounding_up"
        assert pattern.severity == 0.75
        assert len(pattern.affected_quarters) == 2
        assert len(pattern.evidence) == 1

    def test_relationship_to_company(self, db, company):
        pattern = DiscrepancyPatternModel(
            company_id=company.id,
            pattern_type="metric_switching",
            description="Test",
            affected_quarters=[],
            severity=0.5,
            evidence=[],
        )
        db.add(pattern)
        db.commit()
        db.refresh(pattern)

        assert pattern.company is not None
        assert pattern.company.ticker == "AAPL"

    def test_repr(self, db, company):
        pattern = DiscrepancyPatternModel(
            company_id=company.id,
            pattern_type="selective_emphasis",
            description="Test",
            affected_quarters=[],
            severity=0.6,
            evidence=[],
        )
        db.add(pattern)
        db.commit()

        r = repr(pattern)
        assert "selective_emphasis" in r
        assert "0.6" in r


class TestDiscrepancyPatternRepository:
    """Test the repository methods."""

    def test_get_for_company(self, db, company, company2):
        repo = DiscrepancyPatternRepository(db)

        # Create patterns for two companies
        repo.create(DiscrepancyPatternModel(
            company_id=company.id, pattern_type="a", description="p1",
            affected_quarters=[], severity=0.5, evidence=[],
        ))
        repo.create(DiscrepancyPatternModel(
            company_id=company.id, pattern_type="b", description="p2",
            affected_quarters=[], severity=0.8, evidence=[],
        ))
        repo.create(DiscrepancyPatternModel(
            company_id=company2.id, pattern_type="c", description="p3",
            affected_quarters=[], severity=0.3, evidence=[],
        ))

        # Get for company 1 — should return 2, ordered by severity desc
        results = repo.get_for_company(company.id)
        assert len(results) == 2
        assert results[0].severity >= results[1].severity  # desc order

        # Get for company 2
        results2 = repo.get_for_company(company2.id)
        assert len(results2) == 1

    def test_delete_for_company(self, db, company, company2):
        repo = DiscrepancyPatternRepository(db)

        repo.create(DiscrepancyPatternModel(
            company_id=company.id, pattern_type="a", description="p1",
            affected_quarters=[], severity=0.5, evidence=[],
        ))
        repo.create(DiscrepancyPatternModel(
            company_id=company2.id, pattern_type="b", description="p2",
            affected_quarters=[], severity=0.3, evidence=[],
        ))

        # Delete for company 1 only
        deleted = repo.delete_for_company(company.id)
        assert deleted == 1
        assert len(repo.get_for_company(company.id)) == 0
        # Company 2 unaffected
        assert len(repo.get_for_company(company2.id)) == 1

    def test_get_all_grouped(self, db, company, company2):
        repo = DiscrepancyPatternRepository(db)

        repo.create(DiscrepancyPatternModel(
            company_id=company.id, pattern_type="a", description="p1",
            affected_quarters=[], severity=0.5, evidence=[],
        ))
        repo.create(DiscrepancyPatternModel(
            company_id=company2.id, pattern_type="b", description="p2",
            affected_quarters=[], severity=0.3, evidence=[],
        ))
        repo.create(DiscrepancyPatternModel(
            company_id=company2.id, pattern_type="c", description="p3",
            affected_quarters=[], severity=0.7, evidence=[],
        ))

        grouped = repo.get_all_grouped()
        assert company.id in grouped
        assert company2.id in grouped
        assert len(grouped[company.id]) == 1
        assert len(grouped[company2.id]) == 2

    def test_count(self, db, company):
        repo = DiscrepancyPatternRepository(db)

        assert repo.count() == 0

        repo.create(DiscrepancyPatternModel(
            company_id=company.id, pattern_type="a", description="p1",
            affected_quarters=[], severity=0.5, evidence=[],
        ))
        assert repo.count() == 1

    def test_empty_results(self, db, company):
        repo = DiscrepancyPatternRepository(db)
        assert repo.get_for_company(company.id) == []
        assert repo.get_all_grouped() == {}
        assert repo.delete_for_company(company.id) == 0
