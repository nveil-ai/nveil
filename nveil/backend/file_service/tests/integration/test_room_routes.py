# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for file_service room routes (/file/rooms/*)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from testing.factories import insert_user, insert_room

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_user_and_room(db_session, email="test@test.com"):
    """Create a user + room and return (owner_id, room_id)."""
    user = await insert_user(db_session, email=email)
    room = await insert_room(db_session, str(user.id))
    return str(user.id), str(room.id)


async def _create_user_file(file_manager, owner_id, filename="test.csv", data=b"a,b\n1,2\n"):
    """Upload a file to the store (no room link)."""
    return await file_manager.upload_to_store(
        owner_id=owner_id, filename=filename, data=data,
    )


async def _create_and_link(db_session, file_manager, owner_id, room_id, tmp_path,
                           filename="test.csv", data=b"a,b\n1,2\n"):
    """Upload a file and link it to a room. Returns (UserFile, RoomDataRef)."""
    uf = await _create_user_file(file_manager, owner_id, filename, data)
    ref = await file_manager.link_to_room(owner_id, room_id, str(uf.id))
    return uf, ref


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch, tmp_path):
    """Mock filesystem and choregraph dependencies at the boundary."""
    _user_file_path = lambda owner_id, file_id: tmp_path / str(owner_id) / "data" / str(file_id)

    # Filesystem boundary: redirect all paths to tmp_path
    monkeypatch.setattr("shared.workspace.user_file_path", _user_file_path)
    monkeypatch.setattr("services.file_manager.user_file_path", _user_file_path)
    monkeypatch.setattr("routes.rooms._workspace_path",
                        lambda owner_id, room_id: tmp_path / str(owner_id) / str(room_id))
    monkeypatch.setattr("routes.rooms.user_file_path", _user_file_path)
    # Symlink operations: no-op (would create real symlinks to nonexistent store paths)
    monkeypatch.setattr("services.file_manager.link_data_file", lambda *a, **kw: None)
    monkeypatch.setattr("services.file_manager.unlink_data_file", lambda *a, **kw: None)
    # Choregraph library boundary: these parse/generate domain-specific XML
    monkeypatch.setattr("routes.rooms.build_choregraph_inputs", lambda **kw: None)
    monkeypatch.setattr("routes.rooms.create_specifications_xml", lambda *a, **kw: None)
    # Pipeline cleanup: no-op (would delete real dirs)
    monkeypatch.setattr("routes.rooms.clean_pipeline_outputs", lambda *a, **kw: None)
    # XML path rewriting: mocked because test XML is dummy content
    monkeypatch.setattr("routes.rooms.retarget_xml_paths", lambda *a, **kw: None)


@pytest.fixture
def file_manager(db_session):
    from services.file_manager import FileManager
    return FileManager(db_session)


# ---------------------------------------------------------------------------
# Tests — Link
# ---------------------------------------------------------------------------


class TestLinkFiles:
    async def test_link_single_file(self, client, db_session, file_manager, tmp_path):
        owner_id, room_id = await _setup_user_and_room(db_session, "link@test.com")
        uf = await _create_user_file(file_manager, owner_id)

        ws = tmp_path / owner_id / room_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / uf.original_name).write_text("fake")

        resp = await client.post(
            f"/file/rooms/{room_id}/link",
            headers={"X-Owner-Id": owner_id},
            json={"file_ids": [str(uf.id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["linked"]) == 1
        assert data["errors"] == []

    async def test_link_missing_owner_422(self, client):
        resp = await client.post(
            "/file/rooms/00000000-0000-0000-0000-000000000001/link",
            json={"file_ids": ["some-id"]},
        )
        assert resp.status_code == 422

    async def test_link_nonexistent_file_errors(self, client, db_session, file_manager):
        owner_id, room_id = await _setup_user_and_room(db_session, "linkbad@test.com")
        fake_id = "00000000-0000-0000-0000-000000000000"

        resp = await client.post(
            f"/file/rooms/{room_id}/link",
            headers={"X-Owner-Id": owner_id},
            json={"file_ids": [fake_id]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["errors"]) == 1


# ---------------------------------------------------------------------------
# Tests — Unlink
# ---------------------------------------------------------------------------


class TestUnlinkFile:
    async def test_unlink_linked_file(self, client, db_session, file_manager, tmp_path):
        owner_id, room_id = await _setup_user_and_room(db_session, "unlink@test.com")
        uf, ref = await _create_and_link(db_session, file_manager, owner_id, room_id, tmp_path)

        ws = tmp_path / owner_id / room_id
        ws.mkdir(parents=True, exist_ok=True)

        resp = await client.delete(
            f"/file/rooms/{room_id}/unlink/{uf.id}",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["unlinked"] is True
        assert data["no_sources_remaining"] is True


# ---------------------------------------------------------------------------
# Tests — Apply (batch link + unlink)
# ---------------------------------------------------------------------------


class TestApply:
    async def test_apply_link_and_unlink(self, client, db_session, file_manager, tmp_path):
        owner_id, room_id = await _setup_user_and_room(db_session, "apply@test.com")

        uf_a, _ = await _create_and_link(
            db_session, file_manager, owner_id, room_id, tmp_path, filename="a.csv",
        )
        uf_b = await _create_user_file(file_manager, owner_id, filename="b.csv")

        ws = tmp_path / owner_id / room_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "b.csv").write_text("fake")

        resp = await client.post(
            f"/file/rooms/{room_id}/apply",
            headers={"X-Owner-Id": owner_id},
            json={
                "link_file_ids": [str(uf_b.id)],
                "unlink_file_ids": [str(uf_a.id)],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["linked"]) == 1
        assert len(data["unlinked"]) == 1

    async def test_apply_empty_body(self, client, db_session):
        owner_id, room_id = await _setup_user_and_room(db_session, "applyempty@test.com")

        resp = await client.post(
            f"/file/rooms/{room_id}/apply",
            headers={"X-Owner-Id": owner_id},
            json={"link_file_ids": [], "unlink_file_ids": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] == []
        assert data["unlinked"] == []


# ---------------------------------------------------------------------------
# Tests — Provision Panel
# ---------------------------------------------------------------------------


class TestProvisionPanel:
    async def test_provision_panel_success(self, client, db_session, file_manager, tmp_path):
        owner_id, source_room_id = await _setup_user_and_room(db_session, "panel@test.com")
        target_room = await insert_room(db_session, owner_id)
        target_room_id = str(target_room.id)

        source_ws = tmp_path / owner_id / source_room_id
        source_ws.mkdir(parents=True, exist_ok=True)
        (source_ws / "choregraph.xml").write_text("<choregraph/>")
        (source_ws / "specifications.xml").write_text("<spec/>")

        uf, _ = await _create_and_link(
            db_session, file_manager, owner_id, source_room_id, tmp_path,
        )
        store_dir = tmp_path / owner_id / "data" / str(uf.file_id)
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / uf.original_name).write_text("data")

        target_ws = tmp_path / owner_id / "panel_target"

        resp = await client.post(
            f"/file/rooms/{target_room_id}/provision-panel",
            headers={"X-Owner-Id": owner_id},
            json={
                "source_room_id": source_room_id,
                "panel_id": "panel_1",
                "target_workspace": str(target_ws),
                "old_path_prefix": str(source_ws),
                "new_path_prefix": str(target_ws),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["refs_created"] >= 1
        assert (target_ws / "specifications.xml").exists()
        assert (target_ws / "choregraph.xml").exists()

    async def test_provision_panel_missing_source_400(self, client, db_session, tmp_path):
        owner_id, room_id = await _setup_user_and_room(db_session, "panelbad@test.com")

        resp = await client.post(
            f"/file/rooms/{room_id}/provision-panel",
            headers={"X-Owner-Id": owner_id},
            json={
                "source_room_id": "00000000-0000-0000-0000-000000000099",
                "panel_id": "p1",
                "target_workspace": str(tmp_path / "target"),
                "old_path_prefix": "/old",
                "new_path_prefix": "/new",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests — Delete Panel Refs
# ---------------------------------------------------------------------------


class TestDeletePanelRefs:
    async def test_delete_panel_refs(self, client, db_session, file_manager, tmp_path):
        owner_id, room_id = await _setup_user_and_room(db_session, "delpanel@test.com")

        uf, _ = await _create_and_link(
            db_session, file_manager, owner_id, room_id, tmp_path,
        )
        await file_manager.ref_repo.create(
            room_id=room_id, user_file_id=str(uf.id), panel_id="panel_x",
        )
        await db_session.commit()

        resp = await client.delete(
            f"/file/rooms/{room_id}/panels/panel_x",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["deleted"] >= 1

    async def test_delete_panel_refs_nonexistent_returns_zero(self, client, db_session):
        owner_id, room_id = await _setup_user_and_room(db_session, "delpanel2@test.com")

        resp = await client.delete(
            f"/file/rooms/{room_id}/panels/nopanel",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0
