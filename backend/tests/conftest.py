"""Pytest fixtures shared across test modules."""
import io
import os
import pytest
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Hermetic tests: force Demo Mode via real environment variables, which take
# precedence over the .env file. Tests must never call the real LLM and must
# not depend on (or leak) any API key configured in .env.
os.environ["LLM_PROVIDER"] = "demo"
os.environ["LLM_API_KEY"] = ""

from app.core.database import Base, get_db
from app.main import app

# ---- File-based SQLite test DB (avoids in-memory multi-connection issues) ----
TEST_DATABASE_URL = "sqlite:///./test_copilot.db"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Create all tables BEFORE any test runs
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    import app.core.config as cfg
    cfg.settings.UPLOAD_DIR = "test_uploads"
    os.makedirs("test_uploads", exist_ok=True)
    # Use TestClient without lifespan to avoid re-creating tables
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module")
def sample_df():
    """Small in-memory DataFrame with known issues."""
    data = {
        "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 2],   # last row is duplicate of row index 1
        "age": [25, None, 30, None, 22, 45, 60, None, 33, 28, None],
        "country": ["France", "france", "FRANCE", "Germany", "germany", "Spain", "SPAIN", "Italy", "Italy", "UK", "france"],
        "revenue": [100.0, 200.0, 9999.0, 150.0, 175.0, 50.0, 210.0, 80.0, 90.0, 130.0, 200.0],
        "purchase_date": ["2023-01-15"] * 11,
    }
    return pd.DataFrame(data)


@pytest.fixture(scope="module")
def sample_csv_bytes():
    df = pd.DataFrame({
        "customer_id": [f"C{i}" for i in range(50)],
        "age": [20 + i % 40 if i % 7 != 0 else None for i in range(50)],
        "country": ["France" if i % 3 == 0 else ("france" if i % 3 == 1 else "FRANCE") for i in range(50)],
        "revenue": [100 + i * 5 if i % 10 != 0 else None for i in range(50)],
        "score": [float(i) for i in range(50)],
    })
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


@pytest.fixture(scope="module")
def sample_xlsx_bytes():
    """Generate a small XLSX file in memory for upload tests."""
    df = pd.DataFrame({
        "product": [f"Product_{i}" for i in range(30)],
        "sales": [100.0 + i * 10 if i % 8 != 0 else None for i in range(30)],
        "region": ["North" if i % 2 == 0 else "south" for i in range(30)],
        "quantity": [i + 1 for i in range(30)],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.getvalue()
