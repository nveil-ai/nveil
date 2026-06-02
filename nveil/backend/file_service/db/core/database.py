# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool


class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.url: Optional[str] = None
        self.echo: Optional[bool] = None
        self._engine = None
        self._session_local = None

    def initialize(self, url: str, echo: bool):
        self.url = url
        self.echo = echo

    @property
    def engine(self):
        if self._engine is None:
            self._engine = create_async_engine(
                self.url,
                future=True,
                poolclass=NullPool,
                echo=self.echo,
                connect_args={
                    "server_settings": {"jit": "off"},
                    "timeout": 10,
                    "command_timeout": 10,
                },
            )
        return self._engine

    @property
    def session_local(self) -> sessionmaker:
        if self._session_local is None:
            self._session_local = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
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
