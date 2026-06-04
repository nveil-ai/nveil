# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

import docker
import httpx
from utils import get_secret
from logger import ERROR, INFO, SUCCESS, WARNING, logger
from . import viz_pool_config as cfg

CONTAINER_LABEL = "nveil.viz-pool"


@dataclass
class DockerPooledContainer:
    """Container in the Docker pool."""
    name: str
    pool_id: str
    image: str = ""  # image tag used to create this container
    service_dns: str = ""  # cert-valid alias (*.viz-service.svc.cluster.local)
    status: str = "pending"  # pending, available, user-assigned, deleting
    room_id: Optional[str] = None
    room_token: Optional[str] = None
    owner_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    idle_since: Optional[datetime] = None  # when room was released (idle tracking)


class DockerVizPoolManager:
    """
    Docker-based pool manager for local development via Docker Compose.

    Mirrors the VizPoolManager (K8s) interface but uses the Docker API.
    Container names serve as DNS hostnames on the Docker network.
    """

    def __init__(self):
        self.client = docker.from_env()
        self._running = False

        # Detect WSL2 from the Docker daemon's kernel version
        try:
            kernel = self.client.info().get("KernelVersion", "")
            self._is_wsl2 = "microsoft" in kernel.lower()
        except Exception:
            self._is_wsl2 = False

        self.viz_image = cfg.get("VIZ_IMAGE", "nveil_visualization:latest")
        self.docker_network = cfg.get("DOCKER_NETWORK", "nveil_default")
        # Docker Desktop groups containers by com.docker.compose.project.
        # Spawned viz containers must share the *running* compose project
        # (derived from the default network <project>_default) rather than
        # the project baked into the image at build time.
        self.compose_project = self.docker_network.removesuffix("_default")
        self.server_host = cfg.get("SERVER_INTERNAL_HOST", "server")
        self.dive_volume = cfg.get("DIVE_VOLUME", "nveil_nveil-data")
        self.cert_volume = cfg.get("CERT_VOLUME", "")
        self.cert_host_dir = cfg.get("CERT_HOST_DIR", "")
        self.repo_host_dir = cfg.get("REPO_HOST_DIR", "")

        self.pool_min_size = cfg.get_int("VIZ_POOL_MIN_SIZE", 1)
        self.room_idle_timeout = cfg.get_int("VIZ_IDLE_TIMEOUT_MINUTES", 15)
        self.user_idle_timeout = cfg.get_int("VIZ_USER_IDLE_TIMEOUT_MINUTES", 30)

        # Callbacks — set by room.py at startup
        self._on_room_idle_callback = None   # async def(room_id: str)
        self._on_user_idle_callback = None   # async def(owner_id: str)

        # In-memory pool state
        self._pool: Dict[str, DockerPooledContainer] = {}

        # Per-owner asyncio locks for acquire() — prevents concurrent
        # acquire calls for the SAME user from racing on _get_user_entry
        # and double-assigning a pod. Different users never block each
        # other (each gets its own lock). See _user_lock().
        self._user_locks: Dict[str, asyncio.Lock] = {}

        # Long-lived pool for intra-docker-network viz-container calls.
        # Created in start() (requires a running event loop), closed in stop().
        self._http: Optional[httpx.AsyncClient] = None

    def start(self):
        self._cleanup_stale_containers()
        self._running = True
        self._http = httpx.AsyncClient(
            verify=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )
        asyncio.create_task(self._reconcile_loop())
        logger().logp(INFO, f"DockerVizPoolManager started (min_size={self.pool_min_size})")

    def stop(self):
        self._running = False
        if self._http is not None:
            try:
                asyncio.create_task(self._http.aclose())
            except RuntimeError:
                pass
            self._http = None
        self._kill_all_viz_containers()

    async def reload_pool(self) -> list[dict]:
        """Kill all viz containers and immediately respawn the pool.

        Returns a list of dicts with owner_id/room_id for each user-assigned
        container so the caller can clean up DB fields and notify frontends.
        """
        logger().logp(INFO, "Reloading viz pool — killing all containers...")
        affected = [
            {"owner_id": e.owner_id, "room_id": e.room_id}
            for e in self._pool.values()
            if e.status == "user-assigned" and e.owner_id
        ]
        self._kill_all_viz_containers()
        await self._fill_pool()
        logger().logp(SUCCESS, f"Viz pool reloaded ({len(affected)} sessions displaced)")
        return affected

    def _cleanup_stale_containers(self):
        """Remove any viz-pool containers left over from a previous run."""
        try:
            # Find by label (new containers) and by name prefix (legacy containers)
            by_label = self.client.containers.list(
                all=True, filters={"label": CONTAINER_LABEL}
            )
            by_name = self.client.containers.list(
                all=True, filters={"name": "viz-pool-"}
            )
            seen = set()
            for c in by_label + by_name:
                if c.id in seen:
                    continue
                seen.add(c.id)
                try:
                    c.remove(force=True)
                    logger().logp(INFO, f"Removed stale viz container: {c.name}")
                except Exception as e:
                    logger().logp(WARNING, f"Failed to remove stale container {c.name}: {e}")
        except Exception as e:
            logger().logp(ERROR, f"Error listing stale containers: {e}")

    def _kill_all_viz_containers(self):
        """Force-remove ALL viz-pool containers (shutdown path)."""
        try:
            by_label = self.client.containers.list(
                all=True, filters={"label": CONTAINER_LABEL}
            )
            by_name = self.client.containers.list(
                all=True, filters={"name": "viz-pool-"}
            )
            seen = set()
            for c in by_label + by_name:
                if c.id in seen:
                    continue
                seen.add(c.id)
                try:
                    c.remove(force=True)
                    logger().logp(INFO, f"Shutdown: removed {c.name}")
                except Exception:
                    pass
        except Exception:
            pass
        self._pool.clear()

    async def _reconcile_loop(self):
        await self._fill_pool()
        while self._running:
            await asyncio.sleep(30)
            await self._cleanup_dead_containers()
            await self._cleanup_stale_version_containers()
            await self._cleanup_orphan_containers()
            await self._check_pod_idle()
            await self._fill_pool()

    async def _fill_pool(self):
        available_or_pending = sum(
            1 for e in self._pool.values() if e.status in ("available", "pending")
        )
        needed = self.pool_min_size - available_or_pending
        for _ in range(max(0, needed)):
            await self._create_pooled_container()

    async def _cleanup_dead_containers(self):
        for pool_id, entry in list(self._pool.items()):
            if entry.status == "deleting":
                continue
            try:
                container = self.client.containers.get(entry.name)
                if container.status in ("exited", "dead"):
                    logger().logp(WARNING, f"Cleaning dead container {entry.name}")
                    self._delete_container(pool_id)
            except docker.errors.NotFound:
                logger().logp(WARNING, f"Container {entry.name} vanished, removing from pool")
                del self._pool[pool_id]
            except Exception as e:
                logger().logp(ERROR, f"Error checking container {entry.name}: {e}")

    async def _cleanup_stale_version_containers(self):
        """Delete available/pending containers running an old image version."""
        for pool_id, entry in list(self._pool.items()):
            if entry.status not in ("available", "pending"):
                continue
            if entry.image and entry.image != self.viz_image:
                logger().logp(WARNING,
                    f"Draining stale-version container {entry.name} "
                    f"(has={entry.image}, want={self.viz_image})")
                self._delete_container(pool_id)

    async def _cleanup_orphan_containers(self):
        """Force-remove viz-pool containers that aren't tracked in self._pool.

        Acts as the safety net for the inverse of _cleanup_dead_containers
        (which only scans tracked entries). Orphans accumulate when a delete
        partially fails, when entries get popped from self._pool but the
        Docker container survives, or after a server restart that doesn't
        clean up perfectly. Without this reconciliation, _fill_pool keeps
        spawning new "spares" thinking the pool is below min_size while
        ghost containers pile up in the background.
        """
        try:
            tracked_names = {e.name for e in self._pool.values()}
            all_containers = self.client.containers.list(
                all=True, filters={"label": CONTAINER_LABEL}
            )
            for c in all_containers:
                if c.name in tracked_names:
                    continue
                logger().logp(WARNING, f"Orphan viz container detected: {c.name} — removing")
                try:
                    c.remove(force=True)
                except Exception as e:
                    logger().logp(WARNING, f"Failed to remove orphan {c.name}: {e}")
        except Exception as e:
            logger().logp(ERROR, f"Orphan reconcile failed: {e}")

    async def _check_pod_idle(self):
        """Poll user-assigned pods via /viz/status and handle idle timeouts.

        Tier 1: Room idle → release room context, keep pod alive.
        Tier 2: No room for too long → kill pod entirely.
        """
        room_idle_secs = self.room_idle_timeout * 60
        user_idle_secs = self.user_idle_timeout * 60

        for pool_id, entry in list(self._pool.items()):
            if entry.status != "user-assigned":
                continue
            try:
                resp = await self._http.get(f"https://{entry.service_dns}:1024/viz/status", timeout=5.0)
                data = resp.json()
                pod_room_id = data.get("room_id")
                idle = data.get("idle_seconds", 0)

                # Tier 1: Room idle → release room context, keep pod
                if pod_room_id and idle > room_idle_secs:
                    logger().logp(INFO,
                        f"Room idle timeout ({self.room_idle_timeout}min) on pod {entry.name}")
                    await self._release_room_from_pod(entry, pod_room_id)

                # Tier 2: No room for too long → kill pod
                elif not pod_room_id and entry.idle_since:
                    if (datetime.utcnow() - entry.idle_since).total_seconds() > user_idle_secs:
                        logger().logp(INFO,
                            f"User idle timeout ({self.user_idle_timeout}min) on pod {entry.name}")
                        if self._on_user_idle_callback and entry.owner_id:
                            try:
                                await self._on_user_idle_callback(entry.owner_id)
                            except Exception as e:
                                logger().logp(WARNING, f"User idle callback failed: {e}")
                        self._delete_container(pool_id)
            except Exception:
                pass  # Pod unreachable — next cycle will retry or cleanup_dead handles it

    async def _release_room_from_pod(self, entry: DockerPooledContainer, room_id: str):
        """Release a room from its pod (server-side idle decision)."""
        try:
            await self._http.post(f"https://{entry.service_dns}:1024/viz/release_room", timeout=10.0)
        except Exception as e:
            logger().logp(WARNING, f"Failed to notify pod of room release: {e}")
        entry.room_id = None
        entry.idle_since = datetime.utcnow()
        if self._on_room_idle_callback:
            try:
                await self._on_room_idle_callback(room_id)
            except Exception as e:
                logger().logp(WARNING, f"Room idle callback failed: {e}")

    async def _create_pooled_container(self) -> Optional[DockerPooledContainer]:
        pool_id = f"pool-{uuid.uuid4().hex[:8]}"
        container_name = f"viz-pool-{pool_id}"
        # DNS alias matching the cert wildcard *.viz-service.svc.cluster.local
        service_dns = f"viz-pool-{pool_id}.viz-service.svc.cluster.local"

        env = {
            "SERVER_HOST": self.server_host,
            "POOL_MODE": "1",
            "POOL_ID": pool_id,
            "GCP": "0",
            "TEST": "0",
            # TODO(team): viz runs choregraph LLM-assisted nodes, so it needs the
            # CONFIGURED LLM provider key. Forwarding only GOOGLE_API_KEY is
            # arbitrary — unify the ai<->viz LLM env (no duplication) or drop LLM from viz.
            "GOOGLE_API_KEY": get_secret("GOOGLE_API_KEY", ""),
            "SSL_KEYFILE": "/certs/ma_cle_privee.key",
            "SSL_CERTFILE": "/certs/mon_certificat.crt",
        }
        # When repo source is bind-mounted, set PYTHONPATH so imports
        # resolve from the mounted dirs instead of the baked-in site-packages.
        if self.repo_host_dir:
            env["PYTHONPATH"] = "/nveil/backend:/nveil/backend/tools/logger:/choregraph/src:/dive/src"

        # WSL2: D3D12 driver libs for GPU rendering via DirectX translation
        if self._is_wsl2:
            env["LD_LIBRARY_PATH"] = "/usr/lib/wsl/lib"

        volumes = {
            self.dive_volume: {"bind": "/root/DIVE", "mode": "rw"},
        }

        # Network config with alias so the container is reachable via a cert-valid hostname
        networking_config = self.client.api.create_networking_config({
            self.docker_network: self.client.api.create_endpoint_config(
                aliases=[service_dns]
            )
        })

        try:
            # Use the low-level API to set network aliases at creation time
            binds = {self.dive_volume: {"bind": "/root/DIVE", "mode": "rw"}}
            container_volumes = ["/root/DIVE"]

            # Mount certs into viz containers — prefer named volume, fall back to host path
            if self.cert_volume:
                binds[self.cert_volume] = {"bind": "/certs", "mode": "ro"}
                container_volumes.append("/certs")
            elif self.cert_host_dir:
                binds[f"{self.cert_host_dir}/mon_certificat.crt"] = {"bind": "/certs/mon_certificat.crt", "mode": "ro"}
                binds[f"{self.cert_host_dir}/ma_cle_privee.key"] = {"bind": "/certs/ma_cle_privee.key", "mode": "ro"}
                container_volumes.append("/certs")

            # Bind-mount source directories for local dev hot-reload
            if self.repo_host_dir:
                src_mounts = {
                    "nveil/backend/viz_service/viz_renderer": "/nveil/backend/viz_service/viz_renderer",
                    "nveil/backend/shared": "/nveil/backend/shared",
                    "nveil/backend/tools": "/nveil/backend/tools",
                    "choregraph": "/choregraph",
                    "dive/src": "/dive/src",
                }
                for host_rel, container_path in src_mounts.items():
                    binds[f"{self.repo_host_dir}/{host_rel}"] = {"bind": container_path, "mode": "rw"}
                    container_volumes.append(container_path)

            # Detect GPU availability at runtime
            gpu_device_requests = []
            gpu_devices = []
            gpu_binds = {}
            gpu_volumes = []
            try:
                gpu_device_requests = [
                    docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
                ]
                if self._is_wsl2:
                    gpu_devices.append("/dev/dxg:/dev/dxg:rwm")
                    gpu_binds["/usr/lib/wsl"] = {"bind": "/usr/lib/wsl", "mode": "ro"}
                    gpu_volumes.append("/usr/lib/wsl")
            except Exception:
                pass

            def _create_and_start(use_gpu: bool):
                all_binds = {**binds, **(gpu_binds if use_gpu else {})}
                all_volumes = container_volumes + (gpu_volumes if use_gpu else [])
                ctr = self.client.api.create_container(
                    self.viz_image,
                    name=container_name,
                    detach=True,
                    environment=env,
                    volumes=all_volumes,
                    host_config=self.client.api.create_host_config(
                        binds=all_binds,
                        device_requests=gpu_device_requests if use_gpu else [],
                        devices=gpu_devices if use_gpu else None,
                    ),
                    networking_config=networking_config,
                    labels={CONTAINER_LABEL: "true",
                            "com.docker.compose.project": self.compose_project,
                            "com.docker.compose.service": "viz"},
                )
                self.client.api.start(ctr["Id"])
                return ctr

            # Try with GPU first, fall back to CPU-only
            try:
                container_dict = _create_and_start(use_gpu=True)
                logger().logp(INFO, f"Container {container_name} started with GPU")
            except docker.errors.APIError as gpu_err:
                logger().logp(WARNING, f"GPU start failed ({gpu_err}), retrying without GPU")
                try:
                    self.client.api.remove_container(container_name, force=True)
                except Exception:
                    pass
                container_dict = _create_and_start(use_gpu=False)
                logger().logp(INFO, f"Container {container_name} started without GPU (CPU fallback)")
            entry = DockerPooledContainer(
                name=container_name,
                pool_id=pool_id,
                image=self.viz_image,
                service_dns=service_dns,
                status="pending",
            )
            self._pool[pool_id] = entry
            logger().logp(INFO, f"Pool container created: {container_name} dns={service_dns} (status=pending)")
            return entry
        except Exception as e:
            logger().logp(ERROR, f"Failed to create pool container: {e}")
            return None

    def mark_pod_available(self, pool_id: str) -> bool:
        entry = self._pool.get(pool_id)
        if not entry:
            logger().logp(WARNING, f"No pool entry for pool_id={pool_id}")
            return False
        entry.status = "available"
        logger().logp(SUCCESS, f"Container {entry.name} marked available")
        return True

    async def acquire(self, room_id: str, room_token: str, owner_id: str, timeout: int = 120, assign_extra: dict = None) -> Optional[str]:
        """Acquire a pod for a room.

        Returns:
            "already_serving" — pod already serving this exact room (no action).
            "switched"        — existing user pod context-switched to new room.
            "assigned"        — fresh pod assigned from pool.
            None              — acquisition failed.

        Serialized per owner_id via self._user_lock(owner_id) so concurrent
        calls for the same user can't both observe "no user_entry" and both
        try to assign a fresh pod.
        """
        async with self._user_lock(owner_id):
            return await self._acquire_unlocked(room_id, room_token, owner_id, timeout, assign_extra)

    async def _acquire_unlocked(self, room_id: str, room_token: str, owner_id: str, timeout: int, assign_extra: dict) -> Optional[str]:
        # Check if user already has a pod serving this exact room
        user_entry = self._get_user_entry(owner_id)
        if user_entry and user_entry.room_id == room_id:
            logger().logp(INFO, f"Container already assigned to room {room_id[:8]}")
            return "already_serving"

        # Check if user already has a pod (pod-per-user reuse)
        if user_entry:
            logger().logp(INFO, f"Reusing user pod {user_entry.name} for room {room_id[:8]}")
            try:
                payload = {"room_id": room_id, "room_token": room_token, "owner_id": owner_id}
                if assign_extra:
                    payload.update(assign_extra)
                resp = await self._http.post(
                    f"https://{user_entry.service_dns}:1024/viz/assign",
                    json=payload,
                    timeout=120.0,
                )
                if resp.status_code == 200:
                    resp_data = resp.json()
                    if resp_data.get("status") == "error":
                        logger().logp(WARNING, f"Pod {user_entry.name} assign returned error: {resp_data.get('message')}")
                    else:
                        user_entry.room_id = room_id
                        user_entry.room_token = room_token
                        user_entry.status = "user-assigned"
                        user_entry.idle_since = None
                        logger().logp(SUCCESS, f"User pod {user_entry.name} switched to room {room_id[:8]}")
                        return "switched"
            except Exception as e:
                logger().logp(WARNING, f"Failed to reuse user pod {user_entry.name}: {e}")
                # Fall through to acquire a new one

        start_time = asyncio.get_event_loop().time()
        attempted = set()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger().logp(ERROR, f"Timeout acquiring container: room_id={room_id[:8]}")
                return None

            # Find an available container
            found = None
            for pool_id, entry in self._pool.items():
                if entry.status == "available" and pool_id not in attempted:
                    found = (pool_id, entry)
                    break

            if not found:
                pending = sum(1 for e in self._pool.values() if e.status == "pending")
                if pending > 0:
                    logger().logp(INFO, f"No available container, {pending} pending: room={room_id[:8]}")
                else:
                    logger().logp(WARNING, f"No containers, triggering fill: room={room_id[:8]}")
                    asyncio.create_task(self._fill_pool())
                await asyncio.sleep(2)
                continue

            pool_id, entry = found
            attempted.add(pool_id)

            # Assign the container
            try:
                payload = {"room_id": room_id, "room_token": room_token, "owner_id": owner_id}
                if assign_extra:
                    payload.update(assign_extra)
                resp = await self._http.post(
                    f"https://{entry.service_dns}:1024/viz/assign",
                    json=payload,
                    timeout=120.0,
                )
                if resp.status_code == 200:
                    resp_data = resp.json()
                    if resp_data.get("status") == "error":
                        logger().logp(WARNING, f"Container {entry.name} assign error: {resp_data.get('message')}")
                        await asyncio.sleep(1)
                    else:
                        entry.status = "user-assigned"
                        entry.room_id = room_id
                        entry.room_token = room_token
                        entry.owner_id = owner_id
                        entry.idle_since = None
                        logger().logp(SUCCESS, f"Container {entry.name} assigned to room {room_id[:8]}")
                        asyncio.create_task(self._fill_pool())
                        return "assigned"
                else:
                    logger().logp(WARNING, f"Container {entry.name} returned {resp.status_code}, trying next")
                    await asyncio.sleep(1)
            except Exception as e:
                logger().logp(WARNING, f"Failed to assign {entry.name}: {e}")
                await asyncio.sleep(1)

        return None

    async def release(self, room_id: str):
        """Release a room from its container. Pod stays alive (user-assigned, idle)."""
        for pool_id, entry in list(self._pool.items()):
            if entry.room_id == room_id:
                logger().logp(INFO, f"Releasing room {room_id[:8]} from container {entry.name} (pod stays alive)")
                # POST /viz/release_room to clear room context
                try:
                    await self._http.post(f"https://{entry.service_dns}:1024/viz/release_room", timeout=10.0)
                except Exception as e:
                    logger().logp(WARNING, f"Failed to notify pod of room release: {e}")
                entry.room_id = None
                entry.idle_since = datetime.utcnow()
                # Keep status as user-assigned (pod still belongs to user)
                return
        logger().logp(WARNING, f"No container found for room {room_id[:8]}")

    async def release_user(self, owner_id: str):
        """Kill EVERY pod whose owner_id matches `owner_id`, regardless of status.

        Previously this only matched `status == "user-assigned"`, but pods
        in transient states ("deleting", "pending" mid-reassign) with the
        same owner could survive — leading to per-test-run leaks where
        each iteration left exactly one orphan with a deleted user's id.
        Available/spare pods have owner_id == None so they're never
        affected by this sweep.
        """
        killed = 0
        for pool_id, entry in list(self._pool.items()):
            if entry.owner_id == owner_id:
                logger().logp(INFO, f"Releasing user pod {entry.name} for owner {owner_id[:8]} (status was {entry.status})")
                self._delete_container(pool_id)
                killed += 1
        if killed == 0:
            logger().logp(WARNING, f"No pod found for owner {owner_id[:8]}")
        else:
            asyncio.create_task(self._fill_pool())

    def _delete_container(self, pool_id: str):
        entry = self._pool.get(pool_id)
        if not entry:
            return
        entry.status = "deleting"
        try:
            container = self.client.containers.get(entry.name)
            container.remove(force=True)
            logger().logp(SUCCESS, f"Container {entry.name} removed")
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger().logp(WARNING, f"Error removing container {entry.name}: {e}")
        self._pool.pop(pool_id, None)

    def get_pod_dns_for_token(self, room_token: str) -> Optional[str]:
        """Return the pod DNS for a room token, or None if not assigned."""
        for entry in self._pool.values():
            if entry.room_token == room_token and entry.status == "user-assigned":
                return entry.service_dns
        return None

    def get_room_info_for_token(self, room_token: str) -> Optional[dict]:
        """Return full routing info {dns, room_id, owner_id} for a room token."""
        for entry in self._pool.values():
            if entry.room_token == room_token and entry.status == "user-assigned":
                return {"dns": entry.service_dns, "room_id": entry.room_id, "owner_id": entry.owner_id}
        return None

    def get_room_info_for_room_id(self, room_id: str) -> Optional[dict]:
        """Return full routing info {dns, room_id, owner_id} for a room_id."""
        for entry in self._pool.values():
            if entry.room_id == room_id and entry.status == "user-assigned":
                return {"dns": entry.service_dns, "room_id": entry.room_id, "owner_id": entry.owner_id}
        return None

    def get_user_pod_info(self, owner_id: str) -> Optional[dict]:
        """Return pod info for the user's assigned pod."""
        entry = self._get_user_entry(owner_id)
        if not entry:
            return None
        is_ready = False
        try:
            container = self.client.containers.get(entry.name)
            is_ready = container.status == "running"
        except Exception:
            pass
        return {"ready": is_ready, "dns": entry.service_dns, "pool_id": entry.pool_id, "room_id": entry.room_id}

    def _get_user_entry(self, owner_id: str) -> Optional[DockerPooledContainer]:
        """Find the pool entry for a user's assigned pod."""
        for entry in self._pool.values():
            if entry.owner_id == owner_id and entry.status == "user-assigned":
                return entry
        return None

    def _user_lock(self, owner_id: str) -> asyncio.Lock:
        """Per-owner lock for serializing acquire() calls.

        Without this, two concurrent /server/room/start calls for the same
        user can both pass the _get_user_entry check together and both POST
        /viz/assign — leaving the entry's room_id flipping under our feet.
        Locks are scoped per owner_id so different users never block each
        other. Locks are kept in a dict; we never explicitly clean them up
        because they're cheap and the dict lives only for the process.
        """
        lock = self._user_locks.get(owner_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[owner_id] = lock
        return lock


# Singleton
_docker_pool_instance: Optional[DockerVizPoolManager] = None


def get_docker_pool() -> DockerVizPoolManager:
    global _docker_pool_instance
    if _docker_pool_instance is None:
        _docker_pool_instance = DockerVizPoolManager()
    return _docker_pool_instance
