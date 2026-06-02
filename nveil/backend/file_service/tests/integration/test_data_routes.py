# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for file_service data routes (/file/data/*)."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from testing.factories import insert_user

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_user_file(db_session, file_manager, owner_id, tmp_path, filename="test.csv", data=b"a,b\n1,2\n"):
    """Insert a UserFile record via FileManager (bypasses route bugs)."""
    # Ensure the store directory exists
    store_dir = tmp_path / str(owner_id) / "data"
    store_dir.mkdir(parents=True, exist_ok=True)

    uf = await file_manager.upload_to_store(
        owner_id=str(owner_id),
        filename=filename,
        data=data,
    )
    return uf


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
    monkeypatch.setattr("routes.data.user_file_path", _user_file_path)
    # Symlink operations: no-op (would create real symlinks)
    monkeypatch.setattr("services.file_manager.link_data_file", lambda *a, **kw: None)
    monkeypatch.setattr("services.file_manager.unlink_data_file", lambda *a, **kw: None)
    # Background task boundary: _compute_file_stats runs chardet + pandas analysis
    monkeypatch.setattr("routes.data._compute_file_stats", lambda *a, **kw: None)


@pytest.fixture
def file_manager(db_session):
    from services.file_manager import FileManager
    return FileManager(db_session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestListFiles:
    async def test_list_files_empty(self, client, db_session):
        user = await insert_user(db_session, email="listfiles@test.com")
        owner_id = str(user.id)
        resp = await client.get(
            f"/file/data/list/{owner_id}",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"] == []

    async def test_list_files_returns_uploaded(self, client, db_session, file_manager, tmp_path):
        user = await insert_user(db_session, email="listfiles2@test.com")
        owner_id = str(user.id)
        await _create_user_file(db_session, file_manager, owner_id, tmp_path, "mydata.csv")

        resp = await client.get(
            f"/file/data/list/{owner_id}",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert len(files) == 1
        assert files[0]["original_name"] == "mydata.csv"
        assert files[0]["format"] == "csv"


class TestListExtensions:
    async def test_list_extensions_returns_list(self, client, monkeypatch):
        # Mock the connectors registry since the module may not exist
        monkeypatch.setattr(
            "routes.data.NATIVE_EXTENSIONS",
            frozenset({".csv", ".json", ".parquet"}),
        )
        # Patch the lazy import inside the endpoint
        fake_registry = {}
        import types
        fake_connectors = types.ModuleType("connectors")
        fake_connectors.CONNECTOR_REGISTRY = fake_registry
        monkeypatch.setitem(__import__("sys").modules, "connectors", fake_connectors)

        resp = await client.get("/file/extensions")
        assert resp.status_code == 200
        data = resp.json()
        assert "extensions" in data
        assert isinstance(data["extensions"], list)
        assert ".csv" in data["extensions"]


class TestUploadFile:
    async def test_upload_single_csv(self, client, db_session, tmp_path):
        user = await insert_user(db_session, email="upload@test.com")
        owner_id = str(user.id)
        csv_content = b"name,value\nalice,42\n"

        resp = await client.post(
            "/file/data/upload",
            headers={"X-Owner-Id": owner_id},
            files=[("files", ("sample.csv", io.BytesIO(csv_content), "text/csv"))],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["files"]) == 1
        assert data["files"][0]["original_name"] == "sample.csv"

    async def test_upload_no_owner_header_422(self, client):
        csv_content = b"x,y\n1,2\n"
        resp = await client.post(
            "/file/data/upload",
            files=[("files", ("test.csv", io.BytesIO(csv_content), "text/csv"))],
        )
        # FastAPI returns 422 when a required header is missing
        assert resp.status_code == 422

    async def test_upload_duplicate_name_409(self, client, db_session, file_manager, tmp_path):
        user = await insert_user(db_session, email="dup@test.com")
        owner_id = str(user.id)
        # Pre-create a file with the same name
        await _create_user_file(db_session, file_manager, owner_id, tmp_path, "dup.csv")

        resp = await client.post(
            "/file/data/upload",
            headers={"X-Owner-Id": owner_id},
            files=[("files", ("dup.csv", io.BytesIO(b"a,b\n"), "text/csv"))],
        )
        assert resp.status_code == 409


class TestDeleteFile:
    async def test_delete_existing_file(self, client, db_session, file_manager, tmp_path):
        user = await insert_user(db_session, email="delete@test.com")
        owner_id = str(user.id)
        uf = await _create_user_file(db_session, file_manager, owner_id, tmp_path, "todelete.csv")

        resp = await client.delete(
            f"/file/data/{uf.id}",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["deleted"] is True

    async def test_delete_nonexistent_404(self, client, db_session):
        user = await insert_user(db_session, email="del404@test.com")
        owner_id = str(user.id)
        fake_id = "00000000-0000-0000-0000-000000000000"

        resp = await client.delete(
            f"/file/data/{fake_id}",
            headers={"X-Owner-Id": owner_id},
        )
        assert resp.status_code == 404

    async def test_delete_wrong_owner_404(self, client, db_session, file_manager, tmp_path):
        owner = await insert_user(db_session, email="realowner@test.com")
        other = await insert_user(db_session, email="otheruser@test.com")
        uf = await _create_user_file(db_session, file_manager, str(owner.id), tmp_path, "owned.csv")

        resp = await client.delete(
            f"/file/data/{uf.id}",
            headers={"X-Owner-Id": str(other.id)},
        )
        assert resp.status_code == 404


class TestRenameFile:
    async def test_rename_file(self, client, db_session, file_manager, tmp_path):
        user = await insert_user(db_session, email="rename@test.com")
        owner_id = str(user.id)
        uf = await _create_user_file(db_session, file_manager, owner_id, tmp_path, "old_name.csv")

        resp = await client.put(
            f"/file/data/{uf.id}/rename",
            headers={"X-Owner-Id": owner_id},
            json={"display_name": "My Better Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_rename_nonexistent_404(self, client, db_session):
        user = await insert_user(db_session, email="rename404@test.com")
        owner_id = str(user.id)
        fake_id = "00000000-0000-0000-0000-000000000000"

        resp = await client.put(
            f"/file/data/{fake_id}/rename",
            headers={"X-Owner-Id": owner_id},
            json={"display_name": "whatever"},
        )
        assert resp.status_code == 404


class TestUploadUrl:
    async def test_upload_from_url(self, client, db_session, monkeypatch, tmp_path):
        user = await insert_user(db_session, email="urlupload@test.com")
        owner_id = str(user.id)

        # Mock the module-level shared httpx client to return fake CSV data
        fake_resp = MagicMock()
        fake_resp.content = b"col1,col2\nfoo,bar\n"
        fake_resp.headers = {"content-type": "text/csv"}
        fake_resp.raise_for_status = MagicMock()

        fake_client = AsyncMock()
        fake_client.get = AsyncMock(return_value=fake_resp)

        monkeypatch.setattr("routes.data.httpx_client", fake_client)

        resp = await client.post(
            "/file/data/upload-url",
            headers={"X-Owner-Id": owner_id},
            json={"urls": [{"url": "https://example.com/data.csv", "label": "remote_data"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["files"]) == 1
        assert data["files"][0]["original_name"] == "remote_data.csv"

    async def test_upload_url_no_owner_422(self, client):
        resp = await client.post(
            "/file/data/upload-url",
            json={"urls": [{"url": "https://example.com/data.csv"}]},
        )
        assert resp.status_code == 422

    async def test_upload_url_too_many_413(self, client, db_session):
        user = await insert_user(db_session, email="urlmany@test.com")
        owner_id = str(user.id)

        urls = [{"url": f"https://example.com/data{i}.csv"} for i in range(6)]
        resp = await client.post(
            "/file/data/upload-url",
            headers={"X-Owner-Id": owner_id},
            json={"urls": urls},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Reupload
# ---------------------------------------------------------------------------


class TestReuploadFile:
    async def test_reupload_replaces_content(self, client, db_session, file_manager, tmp_path):
        user = await insert_user(db_session, email="reupload@test.com")
        owner_id = str(user.id)
        uf = await _create_user_file(db_session, file_manager, owner_id, tmp_path, "target.csv", b"old,data\n1,2\n")
        old_size = uf.size_bytes

        resp = await client.post(
            f"/file/data/{uf.id}/reupload",
            headers={"X-Owner-Id": owner_id},
            files=[("file", ("target.csv", io.BytesIO(b"new,bigger,data\n1,2,3\n4,5,6\n"), "text/csv"))],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "size_bytes" in data

    async def test_reupload_nonexistent_404(self, client, db_session):
        user = await insert_user(db_session, email="reup404@test.com")
        owner_id = str(user.id)
        fake_id = "00000000-0000-0000-0000-000000000000"

        resp = await client.post(
            f"/file/data/{fake_id}/reupload",
            headers={"X-Owner-Id": owner_id},
            files=[("file", ("x.csv", io.BytesIO(b"a\n1\n"), "text/csv"))],
        )
        assert resp.status_code == 404

    async def test_reupload_wrong_owner_404(self, client, db_session, file_manager, tmp_path):
        owner = await insert_user(db_session, email="reupowner@test.com")
        other = await insert_user(db_session, email="reupother@test.com")
        uf = await _create_user_file(db_session, file_manager, str(owner.id), tmp_path, "owned.csv")

        resp = await client.post(
            f"/file/data/{uf.id}/reupload",
            headers={"X-Owner-Id": str(other.id)},
            files=[("file", ("owned.csv", io.BytesIO(b"x\n1\n"), "text/csv"))],
        )
        assert resp.status_code == 404


