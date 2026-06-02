# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared security utilities for path validation and sanitization."""
import os
from pathlib import Path
from typing import Union


def safe_path(base_dir: Union[str, Path], user_input: str) -> Path:
    """
    Validate and sanitize a user-provided path to prevent directory traversal attacks.
    
    Args:
        base_dir: The base directory to which the user input path should be relative.
        user_input: The user-provided path (relative or absolute).
    
    Returns:
        A safe Path object that is guaranteed to be within the base directory.
    
    Raises:
        ValueError: If the resulting path is outside the base directory.
    """
    base_dir = Path(base_dir).resolve()
    
    # Normalize the user input path
    user_path = Path(user_input)
    
    # If the user path is absolute, ensure it is within the base directory
    if user_path.is_absolute():
        full_path = user_path.resolve()
    else:
        full_path = (base_dir / user_path).resolve()
    
    # Check if the full path is within the base directory
    try:
        full_path.relative_to(base_dir)
    except ValueError as e:
        raise ValueError(f"Path {user_input} is outside the allowed directory {base_dir}") from e
    
    return full_path


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to remove potentially dangerous characters.
    
    Args:
        filename: The filename to sanitize.
    
    Returns:
        A sanitized filename.
    """
    # Remove any path traversal sequences
    sanitized = os.path.basename(filename)
    
    # Remove any control characters or other dangerous characters
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in ('.', '-', '_'))
    
    return sanitized


def sanitize_file_path(file_path: str, base_dir: Union[str, Path]) -> Path:
    """
    Sanitize a file path to ensure it is within the allowed directory.
    
    Args:
        file_path: The file path to sanitize.
        base_dir: The base directory to which the file path should be relative.
    
    Returns:
        A safe Path object that is guaranteed to be within the base directory.
    
    Raises:
        ValueError: If the file path is outside the base directory.
    """
    base_dir = Path(base_dir).resolve()
    file_path = Path(file_path).resolve()
    
    # Check if the file path is within the base directory
    try:
        file_path.relative_to(base_dir)
    except ValueError as e:
        raise ValueError(f"File path {file_path} is outside the allowed directory {base_dir}") from e
    
    return file_path


def sanitize_owner_and_room_id(owner_id: str, room_id: str) -> tuple:
    """
    Sanitize owner_id and room_id to prevent directory traversal.
    
    Args:
        owner_id: The owner ID to sanitize.
        room_id: The room ID to sanitize.
    
    Returns:
        A tuple of sanitized (owner_id, room_id).
    
    Raises:
        ValueError: If the owner_id or room_id contains dangerous characters.
    """
    # Remove any path traversal sequences
    sanitized_owner_id = sanitize_filename(owner_id)
    sanitized_room_id = sanitize_filename(room_id)
    
    if not sanitized_owner_id or not sanitized_room_id:
        raise ValueError("Invalid owner_id or room_id")
    
    return sanitized_owner_id, sanitized_room_id
