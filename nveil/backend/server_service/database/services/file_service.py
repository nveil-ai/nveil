# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Business logic for user file management (data store + room linking)."""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from shared.workspace import (
    link_data_file,
    unlink_data_file,
    user_data_path,
    user_file_path,
)

from ..models.room_data_ref import RoomDataRef
from ..models.user_file import UserFile
from ..repository.room_data_ref_repository import RoomDataRefRepository
from ..repository.user_file_repository import UserFileRepository
from .base import BaseService

# Companion file pairings: primary extension -> companion extensions
COMPANION_MAP = {
    ".mhd": [".zraw"],
}


class FileService(BaseService):

    @property
    def file_repo(self) -> UserFileRepository:
        return self.get_repo(UserFileRepository, UserFile)

    @property
    def ref_repo(self) -> RoomDataRefRepository:
        return self.get_repo(RoomDataRefRepository, RoomDataRef)

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

        Args:
            owner_id: Owner UUID.
            filename: Primary file name.
            data: Primary file content.
            companions: Dict of companion filename -> bytes (e.g., {"vol.zraw": b"..."}).
            upload_source: 'file' or 'url'.
            source_url: Original URL if url source.

        Returns:
            Created UserFile record.
        """
        file_uuid = str(uuid4())
        store_dir = user_file_path(owner_id, file_uuid)
        store_dir.mkdir(parents=True, exist_ok=True)

        # Write primary file
        primary_path = store_dir / filename
        primary_path.write_bytes(data)
        total_size = len(data)

        # Write companion files
        companion_names = []
        if companions:
            for comp_name, comp_data in companions.items():
                (store_dir / comp_name).write_bytes(comp_data)
                companion_names.append(comp_name)
                total_size += len(comp_data)

        ext = os.path.splitext(filename)[1].lstrip(".").lower()

        record = await self.file_repo.create(
            owner_id=owner_id,
            file_id=file_uuid,
            original_name=filename,
            format=ext,
            size_bytes=total_size,
            companion_files=json.dumps(companion_names) if companion_names else None,
            upload_source=upload_source,
            source_url=source_url,
        )
        await self.session.commit()
        return record

    # ------------------------------------------------------------------
    # Link / unlink files to rooms
    # ------------------------------------------------------------------

    async def link_to_room(self, owner_id: str, room_id: str, user_file_id: str) -> RoomDataRef:
        """Create room_data_refs record + symlinks."""
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            raise ValueError(f"UserFile {user_file_id} not found")

        # Create DB record first (source of truth for the relationship)
        existing = await self.ref_repo.get_ref(room_id, user_file_id)
        if not existing:
            existing = await self.ref_repo.create(
                room_id=room_id,
                user_file_id=user_file_id,
            )
            await self.session.commit()

        # Then try symlinks (best-effort — can be recreated later)
        filenames = [uf.original_name]
        if uf.companion_files:
            try:
                filenames.extend(json.loads(uf.companion_files))
            except (json.JSONDecodeError, TypeError):
                pass

        try:
            link_data_file(owner_id, room_id, str(uf.file_id), filenames)
        except OSError as e:
            # Symlink failed but DB record is saved — log and continue
            logger.warning(
                f"Symlink creation failed for file {uf.original_name} "
                f"in room {room_id}: {e}"
            )

        return existing

    async def unlink_from_room(self, owner_id: str, room_id: str, user_file_id: str) -> bool:
        """Remove room_data_refs record + symlinks (best-effort)."""
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            return False

        # Delete DB record first (source of truth)
        deleted = await self.ref_repo.delete_ref(room_id, user_file_id)
        await self.session.commit()

        # Then try symlink removal (best-effort)
        filenames = [uf.original_name]
        if uf.companion_files:
            try:
                filenames.extend(json.loads(uf.companion_files))
            except (json.JSONDecodeError, TypeError):
                pass

        try:
            unlink_data_file(owner_id, room_id, filenames)
        except OSError as e:
            logger.warning(
                f"Symlink removal failed for file {uf.original_name} "
                f"in room {room_id}: {e}"
            )

        return deleted

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    async def rename_file(self, user_file_id: str, display_name: str) -> bool:
        result = await self.file_repo.update_by_id(user_file_id, display_name=display_name)
        await self.session.commit()
        return result

    async def delete_file(self, owner_id: str, user_file_id: str) -> bool:
        """Delete a file from the data store and all room references."""
        uf = await self.file_repo.get_by_id(user_file_id)
        if not uf:
            return False

        # Build filename list (defensive against bad companion_files JSON)
        filenames = [uf.original_name]
        if uf.companion_files:
            try:
                filenames.extend(json.loads(uf.companion_files))
            except (json.JSONDecodeError, TypeError):
                pass

        # Remove symlinks from all rooms (best-effort)
        refs = await self.ref_repo.get_rooms_for_file(user_file_id)
        for ref in refs:
            try:
                unlink_data_file(owner_id, str(ref.room_id), filenames)
            except OSError as e:
                logger.warning(
                    f"Symlink removal failed for file {uf.original_name} "
                    f"in room {ref.room_id}: {e}"
                )

        # Delete DB records first (cascade will handle room_data_refs)
        await self.file_repo.delete_by_id(user_file_id)
        await self.session.commit()

        # Delete physical files
        store_dir = user_file_path(owner_id, str(uf.file_id))
        if store_dir.exists():
            shutil.rmtree(store_dir, ignore_errors=True)

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

        # Atomic write: write to temp, then rename
        tmp_path = primary_path.with_suffix(".tmp")
        tmp_path.write_bytes(data)
        os.replace(str(tmp_path), str(primary_path))

        await self.file_repo.update_by_id(
            user_file_id, size_bytes=len(data), sha256=None
        )
        await self.session.commit()
        return await self.file_repo.get_by_id(user_file_id)

    # ------------------------------------------------------------------
    # Registration (for streaming uploads where data is already on disk)
    # ------------------------------------------------------------------

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
    # Room data ref synchronization
    # ------------------------------------------------------------------

    async def sync_room_refs(
        self, room_id: str, active_filenames: list[str]
    ) -> None:
        """Remove room_data_refs for files not in *active_filenames*.

        Call with an empty list to clear all refs for the room.
        """
        refs = await self.ref_repo.get_files_for_room(room_id)
        for ref in refs:
            uf = await self.file_repo.get_by_id(str(ref.user_file_id))
            if uf and uf.original_name not in active_filenames:
                await self.ref_repo.delete_ref(room_id, str(ref.user_file_id))
        await self.session.commit()

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
