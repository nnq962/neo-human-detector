import json
from utils import LOGGER

def load_config(file_path: str) -> dict:
    """Load configuration from JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        LOGGER.error(f"Cannot load config {file_path}, using defaults: {e}")
        return {}