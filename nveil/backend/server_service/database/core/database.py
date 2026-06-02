# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

class	DatabaseManager:
    # Déclaration des variables
    url:			Optional[str] = None
    pool_size:		Optional[int] = None
    max_overflow:	Optional[int] = None
    pool_pre_ping:	Optional[bool] = None
    echo:			Optional[bool] = None
    # Singleton interne
    _instance:		Optional["DatabaseManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def	__init__(self):
        self._engine: Optional[create_async_engine] = None
        self._session_local: Optional[sessionmaker] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    def	initialize(self, url: str, echo: bool, pool_size: int = 5, max_overflow: int = 10, pool_pre_ping: bool = True):
        self.url = url
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_pre_ping = pool_pre_ping
        self.echo = echo

    @property
    def	engine(self):
        if self._engine is None:
            self._engine = create_async_engine(
                self.url,
                future=True,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_pre_ping=self.pool_pre_ping,
                pool_recycle=3600,
                echo=self.echo,
                connect_args={
                    "server_settings": {"jit": "off"},
                    "timeout": 10,
                    "command_timeout": 10
                }
            )
        return self._engine

    @property
    def	session_local(self) -> sessionmaker:
        if self._session_local is None:
            self._session_local = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False
            )
        return self._session_local

    async def close(self):
        if self.engine:
            await self.engine.dispose()
            self._engine = None
            self._session_local = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if self.url is None:
            raise RuntimeError("DatabaseManager not initialized")
        session = self.session_local()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            del session

db = DatabaseManager()
