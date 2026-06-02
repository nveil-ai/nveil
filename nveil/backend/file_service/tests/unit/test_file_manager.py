# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for FileManager — file upload, linking, deletion."""

import json
import pytest

from services.file_manager import FileManager, linkable_filenames
from testing.factories import insert_user, insert_room

pytestmark = pytest.mark.db


@pytest.fixture
def file_manager(db_session, tmp_path, monkeypatch):
    """FileManager with workspace rooted at tmp_path."""
    monkeypatch.setattr(
        "services.file_manager.user_file_path",
        lambda owner_id, file_id: tmp_path / owner_id / file_id,
    )
    monkeypatch.setattr(
        "services.file_manager.link_data_file",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "services.file_manager.unlink_data_file",
        lambda *a, **kw: None,
    )
    return FileManager(db_session)


class TestUploadToStore:
    async def test_creates_record_and_dir(self, file_manager, db_session, tmp_path):
        user = await insert_user(db_session, email="upload@test.com")
        uf = await file_manager.upload_to_store(
            str(user.id), "data.csv", b"col1,col2\n1,2\n"
        )
        assert uf is not None
        assert uf.original_name == "data.csv"
        assert uf.format == "csv"
        assert uf.size_bytes == len(b"col1,col2\n1,2\n")
        # File written to disk
        store = tmp_path / str(user.id) / str(uf.file_id)
        assert (store / "data.csv").exists()

    async def test_reupload_replaces(self, file_manager, db_session):
        user = await insert_user(db_session, email="reup@test.com")
        uf1 = await file_manager.upload_to_store(str(user.id), "data.csv", b"v1")
        uf2 = await file_manager.upload_to_store(str(user.id), "data.csv", b"version2")
        assert str(uf1.id) == str(uf2.id)  # same record reused
        assert uf2.size_bytes == len(b"version2")

    async def test_with_companions(self, file_manager, db_session):
        user = await insert_user(db_session, email="comp@test.com")
        uf = await file_manager.upload_to_store(
            str(user.id), "scan.mhd", b"mhd-header",
            companions={"scan.zraw": b"zraw-data"},
        )
        companions = json.loads(uf.companion_files)
        assert "scan.zraw" in companions


class TestGetFiles:
    async def test_empty(self, file_manager, db_session):
        user = await insert_user(db_session, email="empty@test.com")
        files = await file_manager.get_user_files(str(user.id))
        assert files == []

    async def test_returns_owned(self, file_manager, db_session):
        user = await insert_user(db_session, email="owned@test.com")
        await file_manager.upload_to_store(str(user.id), "a.csv", b"data")
        await file_manager.upload_to_store(str(user.id), "b.csv", b"data")
        files = await file_manager.get_user_files(str(user.id))
        assert len(files) == 2

    async def test_get_by_id(self, file_manager, db_session):
        user = await insert_user(db_session, email="byid@test.com")
        uf = await file_manager.upload_to_store(str(user.id), "x.csv", b"data")
        found = await file_manager.get_file_by_id(str(uf.id))
        assert found is not None
        assert found.original_name == "x.csv"

    async def test_get_by_id_not_found(self, file_manager):
        from uuid import uuid4
        found = await file_manager.get_file_by_id(str(uuid4()))
        assert found is None


class TestLinkUnlink:
    async def test_link_creates_ref(self, file_manager, db_session):
        user = await insert_user(db_session, email="link@test.com")
        room = await insert_room(db_session, str(user.id))
        uf = await file_manager.upload_to_store(str(user.id), "d.csv", b"data")
        ref = await file_manager.link_to_room(str(user.id), str(room.id), str(uf.id))
        assert ref is not None

    async def test_link_duplicate_skips(self, file_manager, db_session):
        user = await insert_user(db_session, email="dup_link@test.com")
        room = await insert_room(db_session, str(user.id))
        uf = await file_manager.upload_to_store(str(user.id), "d.csv", b"data")
        ref1 = await file_manager.link_to_room(str(user.id), str(room.id), str(uf.id))
        ref2 = await file_manager.link_to_room(str(user.id), str(room.id), str(uf.id))
        assert str(ref1.id) == str(ref2.id)

    async def test_unlink_deletes_ref(self, file_manager, db_session):
        user = await insert_user(db_session, email="unlink@test.com")
        room = await insert_room(db_session, str(user.id))
        uf = await file_manager.upload_to_store(str(user.id), "d.csv", b"data")
        await file_manager.link_to_room(str(user.id), str(room.id), str(uf.id))
        deleted = await file_manager.unlink_from_room(str(user.id), str(room.id), str(uf.id))
        assert deleted is True

    async def test_get_files_for_room(self, file_manager, db_session):
        user = await insert_user(db_session, email="room_files@test.com")
        room = await insert_room(db_session, str(user.id))
        uf = await file_manager.upload_to_store(str(user.id), "d.csv", b"data")
        await file_manager.link_to_room(str(user.id), str(room.id), str(uf.id))
        refs = await file_manager.get_files_for_room(str(room.id))
        assert len(refs) == 1

    async def test_get_rooms_for_file(self, file_manager, db_session):
        user = await insert_user(db_session, email="file_rooms@test.com")
        room = await insert_room(db_session, str(user.id))
        uf = await file_manager.upload_to_store(str(user.id), "d.csv", b"data")
        await file_manager.link_to_room(str(user.id), str(room.id), str(uf.id))
        refs = await file_manager.get_rooms_for_file(str(uf.id))
        assert len(refs) == 1


class TestRenameDelete:
    async def test_rename(self, file_manager, db_session):
        user = await insert_user(db_session, email="rename@test.com")
        uf = await file_manager.upload_to_store(str(user.id), "old.csv", b"data")
        result = await file_manager.rename_file(str(uf.id), "New Display Name")
        assert result is True

    async def test_delete(self, file_manager, db_session):
        user = await insert_user(db_session, email="delete@test.com")
        uf = await file_manager.upload_to_store(str(user.id), "del.csv", b"data")
        result = await file_manager.delete_file(str(user.id), str(uf.id))
        assert result is True
        assert await file_manager.get_file_by_id(str(uf.id)) is None


class TestProcessingStatus:
    async def test_update_status(self, file_manager, db_session):
        user = await insert_user(db_session, email="status@test.com")
        uf = await file_manager.upload_to_store(str(user.id), "data.xlsx", b"excel")
        assert uf.processing_status == "processing"
        await file_manager.update_processing_status(
            str(uf.id), "ready", companion_files=["sheet1.parquet"]
        )
        # Force fresh read from DB (UPDATE + commit doesn't refresh ORM cache)
        await db_session.refresh(uf)
        assert uf.processing_status == "ready"
        assert "sheet1.parquet" in uf.companion_files
