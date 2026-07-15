from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from discovery_lab.config import Settings
from discovery_lab.db import models  # noqa: F401
from discovery_lab.db.base import Base
from discovery_lab.ingestion import DeterministicDemoExtractor
from discovery_lab.main import create_app
from discovery_lab.services.ingestion_runner import IngestionRunner
from discovery_lab.services.storage import LocalBlobStore


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory: sessionmaker[Session], tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        blob_root=tmp_path / "blobs",
        upload_max_bytes=1024 * 1024,
    )
    blob_store = LocalBlobStore(settings.blob_root)
    ingestion_runner = IngestionRunner(
        blob_store=blob_store,
        extractor=DeterministicDemoExtractor(),
    )
    app = create_app(
        settings=settings,
        session_factory=session_factory,
        blob_store=blob_store,
        ingestion_runner=ingestion_runner,
    )
    with TestClient(app) as test_client:
        yield test_client
