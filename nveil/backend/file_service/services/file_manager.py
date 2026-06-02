# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Business logic for user file management (data store + room linking).

Migrated from server_service/database/services/file_service.py.
This is the single owner of user_files + room_data_refs tables.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger as _logger
from shared.workspace import (
    link_data_file,
    unlink_data_file,
    user_file_path,
)

from db.models.room_data_ref import RoomDataRef
from db.models.user_file import UserFile
from db.repository.base import BaseRepository
from db.repository.room_data_ref_repository import RoomDataRefRepository
from db.repository.user_file_repository import UserFileRepository

log = _logger()

# Companion file pairings: primary extension -> companion extensions
COMPANION_MAP = {
    ".mhd": [".zraw"],
}

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".ods", ".xlsm"}


# Extensions whose companion outputs replace the primary in the workspace
_PREPROCESSED_EXTENSIONS = EXCEL_EXTENSIONS | {".xml"}


def temporal_subdir(uf: "UserFile") -> str:
    """Return subdirectory name for a temporal collection UserFile."""
    stem = os.path.splitext(uf.original_name)[0]
    return f"_temporal_{stem}"


def linkable_filenames(uf: "UserFile") -> list[str]:
    """Return filenames that should appear in the room workspace.

    For preprocessed files (Excel → parquet, connector XML → CSV):
    only the generated companions are linked.
    For DICOM series (connector upload): a single `<stem>.dicom` directory
    entry that will be symlinked as a directory to the store.
    For everything else: primary + companions (e.g., MHD + ZRAW).
    """
    ext = os.path.splitext(uf.original_name)[1].lower()
    companions = []
    if uf.companion_files:
        try:
            companions = json.loads(uf.companion_files)
        except (json.JSONDecodeError, TypeError):
            # Fallback: handle Python repr format (single-quoted strings)
            import ast
            try:
                companions = ast.literal_eval(uf.companion_files)
            except (ValueError, SyntaxError):
                pass

    # Connector/Excel uploads produce CSVs/parquets — only link those
    csv_companions = [c for c in companions if c.endswith(".csv")]
    pq_companions = [c for c in companions if c.endswith(".parquet")]
    if ext in _PREPROCESSED_EXTENSIONS and (csv_companions or pq_companions):
        return csv_companions + pq_companions

    # DICOM series: all companions are .dcm → link store dir as a directory
    dcm_companions = [c for c in companions if c.lower().endswith(".dcm")]
    if ext == ".dcm" and dcm_companions:
        stem = os.path.splitext(uf.original_name)[0]
        return [f"{stem}.dicom"]

    filenames = [uf.original_name]
    filenames.extend(companions)
    return filenames


class FileManager:

    def __init__(self, session: AsyncSession):
        self.session = session
        self._repos: Dict[type, BaseRepository] = {}

    def _get_repo(self, repo_class, model):
        if repo_class not in self._repos:
            self._repos[repo_class] = repo_class(model, self.session)
        return self._repos[repo_class]

    @property
    def file_repo(self) -> UserFileRepository:
        return self._get_repo(UserFileRepository, UserFile)

    @property
    def ref_repo(self) -> RoomDataRefRepository:
        return self._get_repo(RoomDataRefRepository, RoomDataRef)

    # ------------------------------------------------------------------
    # Upload to data store
    # ------------------------------------------------------------------

    async def upload_to_store(
        self,
        owner_id: str,
        filename: str,
        data: bytes,
        companions: Optional[dict[str, bytes]] = None,
        upload_source: str = "file",
        source_url: Optional[str] = None,
    ) -> UserFile:
        """Write files to {owner_id}/data/{file_uuid}/ and create DB record.

        If a file with the same name already exists for this owner, the
        old data directory is removed and the DB record is updated in place
        (re-upload / replace semantics).
        """
        existing = await self.file_repo.get_by_owner_and_name(owner_id, filename)

        if existing:
            # Re-upload: reuse the existing record, replace data on disk
            file_uuid = str(existing.file_id)
            store_dir = user_file_path(owner_id, file_uuid)
            if store_dir.exists():
                shutil.rmtree(store_dir)
            store_dir.mkdir(parents=True, exist_ok=True)

            primary_path = store_dir / filename
            primary_path.write_bytes(data)
            total_size = len(data)

            companion_names = []
            if companions:
                for comp_name, comp_data in companions.items():
                    (store_dir / comp_name).write_bytes(comp_data)
                    companion_names.append(comp_name)
                    total_size += len(comp_data)

            ext = os.path.splitext(filename)[1].lower()
            fmt = ext.lstrip(".")
            processing_status = "processing" if ext in EXCEL_EXTENSIONS else None

            await self.file_repo.update_by_id(
                str(existing.id),
                size_bytes=total_size,
                format=fmt,
                companion_files=json.dumps(companion_names) if companion_names else None,
                processing_status=processing_status,
                upload_source=upload_source,
                source_url=source_url,
                updated_at=datetime.now(timezone.utc),
            )
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        file_uuid = str(uuid4())
        store_dir = user_file_path(owner_id, file_uuid)
        store_dir.mkdir(parents=True, exist_ok=True)

        primary_path = store_dir / filename
        primary_path.write_bytes(data)
        total_size = len(data)

        companion_names = []
        if companions:
            for comp_name, comp_data in companions.items():
                (store_dir / comp_name).write_bytes(comp_data)
                companion_names.append(comp_name)
                total_size += len(comp_data)

        ext = os.path.splitext(filename)[1].lower()
        fmt = ext.lstrip(".")

        # Excel files need LLM pre-processing
        processing_status = "processing" if ext in EXCEL_EXTENSIONS else None

        record = await self.file_repo.create(
            owner_id=owner_id,
            file_id=file_uuid,
            original_name=filename,
            format=fmt,
            size_bytes=total_size,
            companion_files=json.dumps(companion_names) if companion_names else None,
            processing_status=processing_status,
            upload_source=upload_source,
            source_url=source_url,
        )
        await self.session.commit()
        return record

    async def register_uploaded_file(
        self,
        owner_id: str,
        file_id: str,
        filename: str,
        size_bytes: int,
        upload_source: str = "file",
        source_url: Optional[str] = None,
    ) -> UserFile:
        """Create DB record for a file already written to the data store."""
        ext = os.path.splitext(filename)[1].lstrip(".").lower()
        record = await self.file_repo.create(
            owner_id=owner_id,
            file_id=file_id,
            original_name=filename,
            format=ext,
            size_bytes=size_bytes,
            upload_source=upload_source,
            source_url=source_url,
        )
        await self.session.commit()
        return record

    # ------------------------------------------------------------------
    # Link / unlink files to rooms
    # ------------------------------------------------------------------

    async def link_to_room(
        self, owner_id: str, room_id: str, user_file_id: str
    ) -> RoomDataRef:
        """Create room_data_refs record + symlinks.

        If the file is still being preprocessed (e.g. Excel → parquet),
        waits until processing completes before creating symlinks so that
        companion files are available for the workspace.
        """
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            raise ValueError(f"UserFile {user_file_id} not found")

        if uf.processing_status == "processing":
            uf = await self._wait_for_processing(user_file_id)

        # Reject Excel files whose preprocessing failed or extracted 0 tables
        ext = os.path.splitext(uf.original_name)[1].lower()
        if ext in EXCEL_EXTENSIONS:
            if uf.processing_status == "error":
                raise ValueError(
                    f"File '{uf.original_name}' preprocessing failed — cannot link to room"
                )
            companions = []
            if uf.companion_files:
                try:
                    companions = json.loads(uf.companion_files)
                except (json.JSONDecodeError, TypeError):
                    pass
            if not companions:
                raise ValueError(
                    f"File '{uf.original_name}' produced no usable tables — cannot link to room"
                )

        existing = await self.ref_repo.get_ref(room_id, user_file_id)
        if not existing:
            existing = await self.ref_repo.create(
                room_id=room_id,
                user_file_id=user_file_id,
            )
            await self.session.commit()

        subdir = temporal_subdir(uf) if uf.collection_time_mode else ""
        try:
            link_data_file(owner_id, room_id, str(uf.file_id), linkable_filenames(uf), subdir=subdir)
        except OSError as e:
            log.warning(
                f"Symlink creation failed for file {uf.original_name} "
                f"in room {room_id}: {e}"
            )

        return existing

    async def _wait_for_processing(
        self, user_file_id: str, poll_interval: float = 2.0, timeout: float = 120.0
    ) -> "UserFile":
        """Block until a file's processing_status is no longer 'processing'.

        Polls the DB at *poll_interval* seconds.  Raises after *timeout*.
        Returns the refreshed UserFile record.
        """
        import asyncio
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            # Expire cached ORM state so we get a fresh DB read
            self.session.expire_all()
            uf = await self.file_repo.get_by_id(user_file_id)
            if not uf:
                raise ValueError(f"UserFile {user_file_id} disappeared during processing")
            if uf.processing_status != "processing":
                if uf.processing_status == "error":
                    log.warning(f"File '{uf.original_name}' preprocessing failed")
                return uf
        raise TimeoutError(
            f"File {user_file_id} still processing after {timeout}s"
        )

    async def unlink_from_room(
        self, owner_id: str, room_id: str, user_file_id: str
    ) -> bool:
        """Remove room_data_refs record + symlinks (best-effort)."""
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            return False

        deleted = await self.ref_repo.delete_ref(room_id, user_file_id)
        await self.session.commit()

        subdir = temporal_subdir(uf) if uf.collection_time_mode else ""
        try:
            unlink_data_file(owner_id, room_id, linkable_filenames(uf), subdir=subdir)
        except OSError as e:
            log.warning(
                f"Symlink removal failed for file {uf.original_name} "
                f"in room {room_id}: {e}"
            )

        return deleted

    async def sync_room_refs(
        self, owner_id: str, room_id: str, active_filenames: list[str]
    ) -> None:
        """Remove room_data_refs AND symlinks for files not in *active_filenames*."""
        refs = await self.ref_repo.get_files_for_room(room_id)
        for ref in refs:
            uf = await self.file_repo.get_by_id(str(ref.user_file_id))
            if uf and uf.original_name not in active_filenames:
                await self.unlink_from_room(owner_id, room_id, str(ref.user_file_id))

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    async def rename_file(self, user_file_id: str, display_name: str) -> bool:
        result = await self.file_repo.update_by_id(
            user_file_id, display_name=display_name
        )
        await self.session.commit()
        return result

    async def delete_file(self, owner_id: str, user_file_id: str) -> bool:
        """Delete a file from the data store and all room references."""
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            return False

        refs = await self.ref_repo.get_rooms_for_file(user_file_id)
        subdir = temporal_subdir(uf) if uf.collection_time_mode else ""
        for ref in refs:
            try:
                unlink_data_file(owner_id, str(ref.room_id), linkable_filenames(uf), subdir=subdir)
            except OSError as e:
                log.warning(
                    f"Symlink removal failed for file {uf.original_name} "
                    f"in room {ref.room_id}: {e}"
                )

        await self.file_repo.delete_by_id(user_file_id)
        await self.session.commit()

        store_dir = user_file_path(owner_id, str(uf.file_id))
        log.info(f"  delete_file: removing store_dir={store_dir} exists={store_dir.exists()}")
        if store_dir.exists():
            try:
                shutil.rmtree(store_dir)
                log.info(f"  delete_file: store_dir removed")
            except OSError as e:
                log.error(f"  delete_file: rmtree failed: {e}")

        return True

    async def reupload_file(
        self, owner_id: str, user_file_id: str, data: bytes
    ) -> UserFile:
        """Re-upload content, keeping file_id and all references."""
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            raise ValueError(f"UserFile {user_file_id} not found")

        store_dir = user_file_path(owner_id, str(uf.file_id))
        primary_path = store_dir / uf.original_name

        tmp_path = primary_path.with_suffix(".tmp")
        tmp_path.write_bytes(data)
        os.replace(str(tmp_path), str(primary_path))

        await self.file_repo.update_by_id(
            user_file_id,
            size_bytes=len(data),
            sha256=None,
            updated_at=datetime.now(timezone.utc),
        )
        await self.session.commit()
        return await self.file_repo.get_by_id(user_file_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_user_files(self, owner_id: str) -> List[UserFile]:
        return await self.file_repo.get_by_owner(owner_id)

    async def get_file_by_id(self, file_id: str) -> Optional[UserFile]:
        return await self.file_repo.get_by_id(file_id)

    async def get_rooms_for_file(self, user_file_id: str) -> List[RoomDataRef]:
        return await self.ref_repo.get_rooms_for_file(user_file_id)

    async def get_files_for_room(self, room_id: str) -> List[RoomDataRef]:
        return await self.ref_repo.get_files_for_room(room_id)

    async def update_processing_status(
        self, user_file_id: str, status: str, companion_files: Optional[List[str]] = None
    ) -> None:
        """Update processing_status and optionally companion_files."""
        kwargs = {"processing_status": status}
        if companion_files is not None:
            kwargs["companion_files"] = json.dumps(companion_files)
        await self.file_repo.update_by_id(user_file_id, **kwargs)
        await self.session.commit()

