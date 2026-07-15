from __future__ import annotations

from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session

from discovery_lab.config import Settings
from discovery_lab.services.ingestion_runner import IngestionRunner
from discovery_lab.services.storage import BlobStore


def get_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_blob_store(request: Request) -> BlobStore:
    return cast(BlobStore, request.app.state.blob_store)


def get_ingestion_runner(request: Request) -> IngestionRunner:
    return cast(IngestionRunner, request.app.state.ingestion_runner)


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
