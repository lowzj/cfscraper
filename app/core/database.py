"""
Database configuration and utilities for CFScraper.

This module provides async database session management and utilities.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from app.database.connection import connection_manager

logger = logging.getLogger(__name__)

# Create base class for models
Base = declarative_base()


# Backward compatibility - expose async engine from connection manager
def async_engine():
    """Get the asynchronous database engine"""
    if not connection_manager._initialized:
        connection_manager.initialize()
    return connection_manager.async_engine


# Deprecated - for backward compatibility only
def engine():
    """Get the asynchronous database engine (deprecated: use async_engine)"""
    logger.warning("engine() is deprecated, use async_engine() instead")
    return async_engine()


# Deprecated - for backward compatibility only
def SessionLocal():
    """Deprecated: Use get_async_db_dependency() instead"""
    raise RuntimeError(
        "SessionLocal() is deprecated and has been removed. "
        "Use get_async_db_dependency() for FastAPI dependencies or "
        "connection_manager.get_async_session() for direct session access."
    )


# Deprecated - for backward compatibility only
def get_db():
    """Deprecated: Use get_async_db_dependency() instead"""
    raise RuntimeError(
        "get_db() is deprecated and has been removed. "
        "Use get_async_db_dependency() for async database sessions."
    )


@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions"""
    async with connection_manager.get_async_session() as session:
        yield session


async def get_async_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database sessions"""
    async with get_async_db() as session:
        yield session


async def init_db():
    """Initialize database tables asynchronously"""
    if not connection_manager._initialized:
        connection_manager.initialize()

    async with connection_manager.async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Deprecated - for backward compatibility only
def init_db_sync():
    """Deprecated: Use init_db() instead"""
    raise RuntimeError(
        "init_db_sync() is deprecated and has been removed. "
        "Use init_db() for async database initialization."
    )


def get_connection_pool_stats() -> dict:
    """Get current connection pool statistics"""
    return connection_manager.get_pool_stats()


async def close_db_connections():
    """Close all database connections"""
    await connection_manager.close_connections()


# Re-export commonly used items for backward compatibility
__all__ = [
    'Base',
    'get_async_db',
    'get_async_db_dependency',
    'init_db',
    'get_connection_pool_stats',
    'close_db_connections',
    'async_engine',
    # Deprecated but kept for transition
    'engine',
    'SessionLocal',
    'get_db',
]
