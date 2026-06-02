# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import os
import shutil
import sys
from pathlib import Path

from database.core.database import db
from database.services.room_service import RoomService
from database.services.user_service import UserService
from logger import ERROR, INFO, logger
from shared.workspace import workspace_path, DIVE_PATH
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")
DATABASE_URL = get_secret("DATABASE_URL")

from room.room import stop_viz

def print_table(title, headers, data):
    if not data:
        logger().logp(INFO, f"No data for {title}")
        return
    
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in data:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
    
    # Format line
    row_fmt = " | ".join([f"{{:<{w}}}" for w in widths])
    sep = "-+-".join(["-" * w for w in widths])
    
    logger().logp(INFO, f"\n=== {title} ===")
    logger().logp(INFO, row_fmt.format(*headers))
    logger().logp(INFO, sep)
    for row in data:
        logger().logp(INFO, row_fmt.format(*[str(val) for val in row]))
    logger().logp(INFO, "")

async def cleanup_all_rooms():
    try:
        db.initialize(url=DATABASE_URL, echo=False)
        from server_service.database.models.base import Base

        async with db.engine.begin() as conn:
            await conn.execute(CreateSchema(DB_SCHEMA, if_not_exists=True))
            await conn.run_sync(Base.metadata.create_all)
        logger().logp(INFO, "✅ Database tables initialized")
    except Exception as e:
        logger().logp(ERROR, f"❌ Database initialization failed: {e}")
        return

    # Create session manually instead of using Depends
    async with db.session() as session:
        user_service = UserService(session)
        room_service = RoomService(session)

        # Collect all users
        all_users = await user_service.user_repo.get_many(limit=10000)
        
        rooms_data = []
        room_headers = ["Room ID", "Room Name", "Owner ID", "Owner Email", "Messages"]
        
        rooms_to_delete = []

        for user in all_users:
            rooms = await room_service.room_repo.get_user_rooms(user.id)
            for room in rooms:
                messages = await room_service.message_repo.get_room_messages(room.id)
                rooms_data.append([
                    str(room.id)[:8], room.name, str(user.id)[:8], user.email, len(messages)
                ])
                rooms_to_delete.append((user, room))

        # Print all gathered data
        if rooms_data:
            print_table(f"ALL ROOMS TO BE DELETED ({len(rooms_data)})", room_headers, rooms_data)
        else:
            logger().logp(INFO, "No rooms found to delete.")
            return

        logger().logp(INFO, f"Found {len(rooms_to_delete)} rooms across {len(all_users)} users.")
        logger().logp(INFO, "WARNING: This will delete ALL rooms, messages, and linked folders for ALL users.")
        logger().logp(INFO, "Do you want to proceed? (yes/no)")
        
        line = sys.stdin.readline().rstrip()
        if line.lower() == 'yes':
            for user, room in rooms_to_delete:
                try:
                    # 1. Stop Viz
                    await stop_viz(room)
                    
                    # 2. Delete Folder
                    room_data_path = workspace_path(str(user.id), str(room.id))
                    if room_data_path.exists():
                        shutil.rmtree(room_data_path, ignore_errors=True)
                        logger().logp(INFO, f"Deleted folder: {room_data_path}")
                    
                    # Redundant with CASCADE — room deletion cascades to messages/members
                    # await room_service.message_repo.delete_room_messages(room.id)
                    # await room_service.room_member_repo.delete_by_room_id(room.id)

                    # Delete Room — CASCADE handles messages, members, panels, data_refs
                    await room_service.room_repo.delete_by_id(room.id)
                    
                except Exception as e:
                    logger().logp(ERROR, f"Error deleting room {room.id}: {e}")
            
            await session.commit()
            logger().logp(INFO, "✅ All rooms cleanup completed successfully")
        else:
            logger().logp(INFO, "❌ Cleanup cancelled")

    await db.close()

if __name__ == "__main__":
    asyncio.run(cleanup_all_rooms())
