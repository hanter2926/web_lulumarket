import re
from pathlib import Path
from uuid import uuid4


def secure_filename(filename: str) -> str:
    """Generate a secure, unique filename preserving extension."""
    ext = Path(filename).suffix
    name = uuid4().hex
    # remove any unsafe characters
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    return f"{name}{ext}"
