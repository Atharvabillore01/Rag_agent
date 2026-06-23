"""FastAPI dependency injection — shared resources (§15)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.storage.cache import CacheClient, get_cache
from src.storage.object import ObjectStore, get_object_store
from src.storage.vector import VectorStore, get_vector_store


def get_vector_store_dep() -> VectorStore:
    return get_vector_store()


def get_object_store_dep() -> ObjectStore:
    return get_object_store()


def get_cache_dep() -> CacheClient:
    return get_cache()
