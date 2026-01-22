
import json
from pathlib import Path

def save_metadata(metadata, path: str):
    with open(path, 'w') as f:
        json.dump(metadata, f, indent=2)

def load_metadata(path: str):
    with open(path, 'r') as f:
        return json.load(f)
