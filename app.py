#!/usr/bin/env python3

import os
import json
import base64
import hashlib
import mimetypes
import random
import string
import time
import math
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import threading
from queue import Queue
import zlib

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

class Config:
    RAW_CHUNK_SIZE = 3 * 1024 * 1024
    TOTAL_REPOS = 150
    REPO_MAX_SIZE = 1 * 1024 * 1024 * 1024
    BASE_DIR = Path(__file__).parent
    REPOS_ROOT = BASE_DIR / "github_repositories"
    METADATA_ROOT = BASE_DIR / "system_data"
    TEMP_DIR = BASE_DIR / "temp_cache"
    REPO_TYPES = [
        "web-development",
        "machine-learning",
        "data-science",
        "mobile-apps",
        "devops-tools",
        "game-development",
        "blockchain",
        "iot-projects"
    ]

@dataclass
class ChunkInfo:
    chunk_id: str
    repo_id: str
    file_path: str
    encoded_size: int
    index: int
    hash: str
    created_at: str
    xor_key: str = ""
    compression_level: int = 6
    fragment_type: str = ""

@dataclass
class FileMetadata:
    file_id: str
    original_name: str
    display_name: str
    original_size: int
    mime_type: str
    upload_time: str
    chunks: List[ChunkInfo]
    chunk_count: int
    tags: List[str]
    description: str

class StealthEncoder:
    @staticmethod
    def obfuscate_data(data: bytes, xor_key: int = None) -> Tuple[bytes, int]:
        if xor_key is None:
            xor_key = random.randint(1, 255)
        obfuscated = bytearray()
        for byte in data:
            obfuscated.append(byte ^ xor_key)
        return bytes(obfuscated), xor_key

    @staticmethod
    def deobfuscate_data(data: bytes, xor_key: int) -> bytes:
        deobfuscated = bytearray()
        for byte in data:
            deobfuscated.append(byte ^ xor_key)
        return bytes(deobfuscated)

    @staticmethod
    def compress_data(data: bytes, level: int = 6) -> bytes:
        return zlib.compress(data, level=level)

    @staticmethod
    def decompress_data(data: bytes) -> bytes:
        return zlib.decompress(data)

    @staticmethod
    def encode_to_base85(data: bytes) -> str:
        return base64.b85encode(data).decode('ascii')

    @staticmethod
    def decode_from_base85(encoded: str) -> bytes:
        return base64.b85decode(encoded.encode('ascii'))

    @staticmethod
    def generate_code_filename(repo_type: str, chunk_index: int) -> str:
        timestamp = int(time.time())
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        code_extensions = {
            "web-development": [".py", ".js", ".ts", ".vue", ".jsx", ".tsx", ".html", ".css"],
            "machine-learning": [".py", ".ipynb", ".json", ".yaml", ".yml", ".csv", ".txt"],
            "data-science": [".py", ".r", ".sql", ".json", ".md", ".txt", ".csv"],
            "mobile-apps": [".java", ".kt", ".swift", ".dart", ".xml", ".gradle"],
            "devops-tools": [".sh", ".yaml", ".yml", ".dockerfile", ".tf", ".json"],
            "game-development": [".cs", ".cpp", ".h", ".lua", ".json", ".gd"],
            "blockchain": [".sol", ".rs", ".js", ".json", ".md", ".txt"],
            "iot-projects": [".cpp", ".ino", ".py", ".json", ".md", ".txt"]
        }
        
        name_templates = [
            f"utils_{random_str}{random.choice(code_extensions[repo_type])}",
            f"helper_{timestamp}_{random_str}{random.choice(code_extensions[repo_type])}",
            f"config_{chunk_index:03d}{random.choice(code_extensions[repo_type])}",
            f"data_{random_str}{random.choice(code_extensions[repo_type])}",
            f"module_{timestamp}{random.choice(code_extensions[repo_type])}",
            f"lib_{chunk_index:03d}_{random_str}{random.choice(code_extensions[repo_type])}"
        ]
        
        return random.choice(name_templates)

    @staticmethod
    def create_code_content(encoded_data: str, repo_type: str, metadata: dict) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fragment_id = metadata.get('fragment_id', 'unknown')
        chunk_index = metadata.get('chunk_index', 0)
        
        code_templates = {
            "web-development": [
                f'''# Web utility module
# Auto-generated: {timestamp}
# Fragment: {fragment_id}
# Index: {chunk_index}

import json
import base64

def load_data_fragment():
    """
    Returns encoded data fragment for processing
    """
    encoded = """
{encoded_data}
    """
    return encoded.strip()

def process_fragment():
    fragment = load_data_fragment()
    return fragment

if __name__ == "__main__":
    print("Data fragment loaded")
''',
                f'''// JavaScript utility module
// Generated: {timestamp}
// Fragment: {fragment_id}
// Index: {chunk_index}

const dataFragment = `{encoded_data}`;

module.exports = {{
    getFragment: function() {{
        return dataFragment;
    }},
    version: "1.0.{chunk_index}"
}};
''',
                f'''// TypeScript interface
// Created: {timestamp}
// Fragment: {fragment_id}

interface DataFragment {{
    id: string;
    content: string;
    timestamp: string;
}}

export const fragment: DataFragment = {{
    id: "{fragment_id}",
    content: `{encoded_data}`,
    timestamp: "{timestamp}"
}};
'''
            ],
            "machine-learning": [
                f'''# Machine Learning data fragment
# Generated: {timestamp}
# Fragment ID: {fragment_id}
# Index: {chunk_index}

import numpy as np
import base64

class DataFragment:
    def __init__(self):
        self.encoded_data = """
{encoded_data}
        """
    
    def get_encoded(self):
        return self.encoded_data.strip()
    
    def __repr__(self):
        return f"DataFragment({{self.encoded_data[:50]}}...)"

fragment = DataFragment()
''',
                f'''{{ 
    "metadata": {{
        "type": "data_fragment",
        "id": "{fragment_id}",
        "index": {chunk_index},
        "timestamp": "{timestamp}",
        "format": "base85_encoded"
    }},
    "data": "{encoded_data}"
}}'''
            ],
            "data-science": [
                f'''# Data science utility
# Created: {timestamp}
# Fragment: {fragment_id}
# Index: {chunk_index}

import pandas as pd
import numpy as np

ENCODED_FRAGMENT = "{encoded_data}"

def get_fragment():
    """Return encoded data fragment"""
    return ENCODED_FRAGMENT

class FragmentLoader:
    def __init__(self):
        self.fragment = ENCODED_FRAGMENT
    
    def load(self):
        return self.fragment
''',
                f'''---
# Data fragment configuration
fragment_id: {fragment_id}
index: {chunk_index}
timestamp: {timestamp}
data_format: base85
content: |
{chr(10).join('  ' + line for line in encoded_data.split(chr(10)))}
---
'''
            ]
        }
        
        default_template = f'''# Code fragment
# Generated: {timestamp}
# ID: {fragment_id}
# Index: {chunk_index}

ENCODED_DATA = "{encoded_data}"

def get_fragment():
    return ENCODED_DATA
'''
        
        templates = code_templates.get(repo_type, [default_template])
        return random.choice(templates)

    @staticmethod
    def extract_encoded_from_code(code_content: str) -> str:
        lines = code_content.split('\n')
        encoded_data = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#') or line.startswith('//') or line.startswith('/*') or line.startswith('*') or line.startswith('--'):
                continue
            if 'ENCODED_DATA' in line or 'encoded_data' in line or 'dataFragment' in line or 'fragment' in line:
                if '=' in line:
                    parts = line.split('=')
                    if len(parts) > 1:
                        data_part = parts[1].strip().strip('"').strip("'").strip('`')
                        if data_part:
                            encoded_data.append(data_part)
                elif ':' in line and ('"' in line or "'" in line):
                    parts = line.split(':')
                    if len(parts) > 1:
                        data_part = parts[1].strip().strip(',').strip('"').strip("'").strip('`')
                        if data_part:
                            encoded_data.append(data_part)
            elif '"""' in line or "'''" in line:
                continue
        
        if encoded_data:
            return encoded_data[0]
        
        for line in lines:
            if line.strip() and not line.startswith('#') and not line.startswith('//') and not line.startswith('/*'):
                clean_line = line.strip().strip('"').strip("'").strip('`').strip()
                if clean_line and len(clean_line) > 20:
                    return clean_line
        
        return ""

class RepoManager:
    def __init__(self):
        self.repos_root = Config.REPOS_ROOT
        self.metadata_root = Config.METADATA_ROOT
        self.temp_dir = Config.TEMP_DIR
        
        for dir_path in [self.repos_root, self.metadata_root, self.temp_dir]:
            dir_path.mkdir(exist_ok=True, parents=True)
        
        self.repo_structure_cache = {}
        self._init_repos()
        self._load_metadata()
    
    def _init_repos(self):
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_path = self.repos_root / repo_id
            repo_path.mkdir(exist_ok=True)
            
            repo_type = Config.REPO_TYPES[i % len(Config.REPO_TYPES)]
            
            self.repo_structure_cache[repo_id] = {
                "type": repo_type,
                "size": 0,
                "chunk_count": 0,
                "folders": []
            }
            
            self._create_repo_artifacts(repo_path, repo_type, repo_id)
    
    def _create_repo_artifacts(self, repo_path: Path, repo_type: str, repo_id: str):
        structures = {
            "web-development": ["src", "public", "components", "utils", "styles", "tests"],
            "machine-learning": ["models", "data", "notebooks", "utils", "configs", "tests"],
            "data-science": ["analysis", "data", "notebooks", "scripts", "visualization"],
            "mobile-apps": ["android", "ios", "lib", "screens", "utils", "assets"],
            "devops-tools": ["docker", "kubernetes", "scripts", "terraform", "monitoring"],
            "game-development": ["assets", "scripts", "scenes", "prefabs", "shaders"],
            "blockchain": ["contracts", "tests", "scripts", "migrations", "utils"],
            "iot-projects": ["firmware", "schematics", "docs", "tests", "utils"]
        }
        
        folders = structures.get(repo_type, structures["web-development"])
        
        if repo_id in self.repo_structure_cache:
            self.repo_structure_cache[repo_id]["folders"] = folders
        
        for folder in folders:
            (repo_path / folder).mkdir(exist_ok=True)
            
            if random.random() > 0.7:
                dummy_ext = random.choice([".py", ".js", ".txt", ".md", ".json", ".yaml"])
                dummy_file = repo_path / folder / f"placeholder_{''.join(random.choices(string.ascii_lowercase, k=6))}{dummy_ext}"
                dummy_file.write_text(f"# Placeholder for {repo_type}\n# {datetime.now().isoformat()}\n")
        
        readme_content = f"""# {repo_id.replace('_', ' ').title()}

Repository for {repo_type.replace('-', ' ')} related code and resources.

## Project Structure

{chr(10).join(f'- `{folder}/` - {folder.title()} directory' for folder in folders)}

## Usage

This is a development repository containing various utilities and code samples.

## License

MIT License
"""
        (repo_path / "README.md").write_text(readme_content)
        
        requirements_file = repo_path / "requirements.txt"
        requirements_content = """numpy>=1.19.0
pandas>=1.2.0
requests>=2.25.0
"""
        requirements_file.write_text(requirements_content)
    
    def _load_metadata(self):
        metadata_file = self.metadata_root / "system.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                    self.files_metadata = {}
                    for file_id, file_data in data.items():
                        chunks = [ChunkInfo(**c) for c in file_data["chunks"]]
                        file_data["chunks"] = chunks
                        self.files_metadata[file_id] = FileMetadata(**file_data)
            except Exception as e:
                print(f"Metadata load error: {e}")
                self.files_metadata = {}
        else:
            self.files_metadata = {}
    
    def _save_metadata(self):
        metadata_file = self.metadata_root / "system.json"
        data = {}
        for file_id, file_meta in self.files_metadata.items():
            file_dict = asdict(file_meta)
            file_dict["chunks"] = [asdict(c) for c in file_meta.chunks]
            data[file_id] = file_dict
        
        with open(metadata_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        backup_file = self.metadata_root / f"backup_{int(time.time())}.json"
        with open(backup_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_repo_size(self, repo_id: str) -> int:
        repo_path = self.repos_root / repo_id
        total_size = 0
        for file_path in repo_path.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size
    
    def _select_repo_for_chunk(self, chunk_size: int) -> Tuple[str, str]:
        candidate_repos = []
        
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_type = Config.REPO_TYPES[i % len(Config.REPO_TYPES)]
            current_size = self._get_repo_size(repo_id)
            if current_size + chunk_size < Config.REPO_MAX_SIZE:
                candidate_repos.append((repo_id, repo_type, current_size))
        
        if candidate_repos:
            candidate_repos.sort(key=lambda x: x[2])
            return candidate_repos[0][0], candidate_repos[0][1]
        
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_type = Config.REPO_TYPES[i % len(Config.REPO_TYPES)]
            current_size = self._get_repo_size(repo_id)
            if current_size + chunk_size < Config.REPO_MAX_SIZE * 1.1:
                return repo_id, repo_type
        
        return f"repo_{random.randint(0, Config.TOTAL_REPOS-1):03d}", random.choice(Config.REPO_TYPES)
    
    def store_chunk(self, chunk_data: bytes, original_name: str, chunk_index: int) -> ChunkInfo:
        xor_key = random.randint(1, 255)
        obfuscated_data, _ = StealthEncoder.obfuscate_data(chunk_data, xor_key)
        
        compressed_data = StealthEncoder.compress_data(obfuscated_data, level=6)
        
        encoded_data = StealthEncoder.encode_to_base85(compressed_data)
        
        chunk_size = len(encoded_data) + 500
        repo_id, repo_type = self._select_repo_for_chunk(chunk_size)
        
        filename = StealthEncoder.generate_code_filename(repo_type, chunk_index)
        
        repo_folders = self.repo_structure_cache[repo_id]["folders"]
        target_folder = random.choice(repo_folders)
        
        file_path = self.repos_root / repo_id / target_folder / filename
        file_path.parent.mkdir(exist_ok=True, parents=True)
        
        metadata = {
            "fragment_id": f"frag_{hashlib.sha256(chunk_data).hexdigest()[:8]}",
            "chunk_index": chunk_index
        }
        
        content = StealthEncoder.create_code_content(encoded_data, repo_type, metadata)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        chunk_info = ChunkInfo(
            chunk_id=hashlib.sha256(chunk_data).hexdigest()[:16],
            repo_id=repo_id,
            file_path=str(file_path.relative_to(self.repos_root)),
            encoded_size=len(content),
            index=chunk_index,
            hash=hashlib.sha256(chunk_data).hexdigest(),
            created_at=datetime.now().isoformat(),
            xor_key=str(xor_key),
            compression_level=6,
            fragment_type=repo_type
        )
        
        return chunk_info
    
    def retrieve_chunk(self, chunk_info: ChunkInfo) -> bytes:
        file_path = self.repos_root / chunk_info.file_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"Chunk file not found: {chunk_info.file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        encoded_data = StealthEncoder.extract_encoded_from_code(content)
        
        if not encoded_data:
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('//') and not line.startswith('/*'):
                    if len(line) > 50:
                        encoded_data = line.strip('"').strip("'").strip('`')
                        break
        
        try:
            compressed_data = StealthEncoder.decode_from_base85(encoded_data)
        except:
            return b""
        
        obfuscated_data = StealthEncoder.decompress_data(compressed_data)
        
        xor_key = int(chunk_info.xor_key) if chunk_info.xor_key else 0
        if xor_key == 0:
            xor_key = 1
        
        chunk_data = StealthEncoder.deobfuscate_data(obfuscated_data, xor_key)
        
        return chunk_data
    
    def delete_chunk(self, chunk_info: ChunkInfo):
        file_path = self.repos_root / chunk_info.file_path
        
        if file_path.exists():
            file_path.unlink()
            
            try:
                if file_path.parent.is_dir() and not any(file_path.parent.iterdir()):
                    file_path.parent.rmdir()
            except Exception:
                pass
    
    def get_file_data(self, file_id: str) -> Optional[bytes]:
        if file_id not in self.files_metadata:
            return None
        
        file_meta = self.files_metadata[file_id]
        chunks = sorted(file_meta.chunks, key=lambda x: x.index)
        
        assembled_data = bytearray()
        for chunk_info in chunks:
            try:
                chunk_data = self.retrieve_chunk(chunk_info)
                assembled_data.extend(chunk_data)
            except Exception:
                return None
        
        return bytes(assembled_data)
    
    def get_preview_data(self, file_id: str, max_size: int = 10 * 1024 * 1024) -> Optional[dict]:
        if file_id not in self.files_metadata:
            return None
        
        file_meta = self.files_metadata[file_id]
        
        if file_meta.original_size > max_size:
            return {"too_large": True, "max_allowed": max_size}
        
        file_data = self.get_file_data(file_id)
        if not file_data:
            return None
        
        mime_type = file_meta.mime_type
        
        if mime_type.startswith('image/'):
            try:
                base64_data = base64.b64encode(file_data).decode('utf-8')
                return {
                    "type": "image",
                    "data": base64_data,
                    "mime_type": mime_type
                }
            except Exception:
                return None
        
        elif mime_type.startswith('text/'):
            try:
                text_content = file_data.decode('utf-8', errors='ignore')
                if len(text_content) > 10000:
                    text_content = text_content[:10000] + "..."
                return {
                    "type": "text",
                    "text": text_content,
                    "mime_type": mime_type
                }
            except Exception:
                return None
        
        elif mime_type == 'application/pdf':
            try:
                base64_data = base64.b64encode(file_data).decode('utf-8')
                return {
                    "type": "pdf",
                    "data": base64_data,
                    "mime_type": mime_type
                }
            except Exception:
                return None
        
        return {
            "type": "binary",
            "message": "Binary file",
            "mime_type": mime_type
        }
    
    def get_repo_stats(self) -> Dict:
        stats = {}
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_path = self.repos_root / repo_id
            if repo_path.exists():
                size = self._get_repo_size(repo_id)
                file_count = sum(1 for _ in repo_path.rglob("*") if _.is_file())
                stats[repo_id] = {
                    "size": size,
                    "files": file_count,
                    "utilization": (size / Config.REPO_MAX_SIZE) * 100
                }
        return stats

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

repo_manager = RepoManager()

@app.route('/')
def index():
    return send_file('static/index.html')

@app.route('/viewer.html')
def viewer():
    return send_file('static/viewer.html')

@app.route('/js/<path:path>')
def serve_js(path):
    return send_from_directory('static/js', path)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "total_repos": Config.TOTAL_REPOS,
        "files_count": len(repo_manager.files_metadata)
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        filename = secure_filename(file.filename)
        file_data = file.read()
        file_size = len(file_data)
        
        if file_size == 0:
            return jsonify({"error": "Empty file"}), 400
        
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"
        
        tags = []
        if mime_type.startswith('image/'):
            tags = ["image", "media"]
        elif mime_type.startswith('audio/'):
            tags = ["audio", "media"]
        elif mime_type.startswith('video/'):
            tags = ["video", "media"]
        elif mime_type == 'application/pdf':
            tags = ["document", "pdf"]
        elif mime_type.startswith('text/'):
            tags = ["text", "document"]
        else:
            tags = ["binary", "data"]
        
        chunks = []
        num_chunks = (file_size + Config.RAW_CHUNK_SIZE - 1) // Config.RAW_CHUNK_SIZE
        
        for i in range(num_chunks):
            start = i * Config.RAW_CHUNK_SIZE
            end = min(start + Config.RAW_CHUNK_SIZE, file_size)
            chunk_data = file_data[start:end]
            
            chunk_info = repo_manager.store_chunk(chunk_data, filename, i)
            chunk_info.index = i
            chunks.append(chunk_info)
        
        file_id = hashlib.sha256(
            f"{filename}{datetime.now().isoformat()}{random.randint(1, 1000000)}".encode()
        ).hexdigest()[:20]
        
        file_metadata = FileMetadata(
            file_id=file_id,
            original_name=filename,
            display_name=filename,
            original_size=file_size,
            mime_type=mime_type,
            upload_time=datetime.now().isoformat(),
            chunks=chunks,
            chunk_count=num_chunks,
            tags=tags,
            description=f"Uploaded {filename} ({file_size} bytes)"
        )
        
        repo_manager.files_metadata[file_id] = file_metadata
        repo_manager._save_metadata()
        
        return jsonify({
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "size": file_size,
            "chunks": num_chunks,
            "upload_time": file_metadata.upload_time,
            "chunk_details": [{
                "chunk_id": c.chunk_id,
                "repo": c.repo_id,
                "path": c.file_path,
                "size": c.encoded_size
            } for c in chunks]
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/files', methods=['GET'])
def list_files():
    try:
        files_list = []
        for file_id, file_meta in repo_manager.files_metadata.items():
            files_list.append({
                "id": file_id,
                "filename": file_meta.original_name,
                "size": file_meta.original_size,
                "mime_type": file_meta.mime_type,
                "upload_time": file_meta.upload_time,
                "chunk_count": file_meta.chunk_count,
                "tags": file_meta.tags
            })
        
        return jsonify({"files": files_list})
    except Exception as e:
        print(f"List files error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>', methods=['GET'])
def download_file(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        
        file_data = repo_manager.get_file_data(file_id)
        if file_data is None:
            return jsonify({"error": "Failed to reconstruct file"}), 500
        
        temp_path = Config.TEMP_DIR / f"download_{file_id}_{int(time.time())}.tmp"
        with open(temp_path, 'wb') as f:
            f.write(file_data)
        
        return send_file(
            str(temp_path),
            as_attachment=True,
            download_name=file_meta.original_name,
            mimetype=file_meta.mime_type
        )
        
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>/preview', methods=['GET'])
def preview_file(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        preview_data = repo_manager.get_preview_data(file_id)
        if preview_data is None:
            return jsonify({"error": "Failed to generate preview"}), 500
        
        if preview_data.get("too_large"):
            return jsonify({
                "error": f"File too large for preview"
            }), 400
        
        return jsonify(preview_data)
        
    except Exception as e:
        print(f"Preview error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>/info', methods=['GET'])
def file_info(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        
        chunks = file_meta.chunks
        
        repo_distribution = defaultdict(int)
        for chunk in chunks:
            repo_distribution[chunk.repo_id] += 1
        
        return jsonify({
            "id": file_id,
            "filename": file_meta.original_name,
            "size": file_meta.original_size,
            "mime_type": file_meta.mime_type,
            "upload_time": file_meta.upload_time,
            "chunk_count": file_meta.chunk_count,
            "tags": file_meta.tags,
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "repo": c.repo_id,
                    "path": c.file_path,
                    "size": c.encoded_size,
                    "index": c.index
                }
                for c in chunks
            ],
            "repo_distribution": dict(repo_distribution)
        })
        
    except Exception as e:
        print(f"File info error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        
        for chunk_info in file_meta.chunks:
            repo_manager.delete_chunk(chunk_info)
        
        del repo_manager.files_metadata[file_id]
        repo_manager._save_metadata()
        
        return jsonify({"success": True, "message": f"File {file_meta.original_name} deleted"})
        
    except Exception as e:
        print(f"Delete error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        total_files = len(repo_manager.files_metadata)
        total_size = sum(f.original_size for f in repo_manager.files_metadata.values())
        total_chunks = sum(f.chunk_count for f in repo_manager.files_metadata.values())
        
        repo_stats = repo_manager.get_repo_stats()
        
        return jsonify({
            "files": {
                "total": total_files,
                "total_size": total_size,
                "total_chunks": total_chunks
            },
            "repos": repo_stats,
            "system": {
                "repo_capacity": Config.REPO_MAX_SIZE,
                "total_repos": Config.TOTAL_REPOS
            }
        })
    except Exception as e:
        print(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/repos', methods=['GET'])
def list_repos():
    try:
        repo_stats = repo_manager.get_repo_stats()
        repos_list = []
        
        for repo_id, stats in repo_stats.items():
            repo_index = int(repo_id.split('_')[1])
            repo_type = Config.REPO_TYPES[repo_index % len(Config.REPO_TYPES)]
            
            repos_list.append({
                "id": repo_id,
                "type": repo_type,
                "size": stats["size"],
                "files": stats["files"],
                "utilization": stats["utilization"]
            })
        
        return jsonify({"repos": repos_list})
    except Exception as e:
        print(f"List repos error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cleanup', methods=['POST'])
def cleanup_temp():
    try:
        deleted = 0
        for temp_file in Config.TEMP_DIR.glob("*.tmp"):
            if temp_file.is_file():
                file_age = time.time() - temp_file.stat().st_mtime
                if file_age > 300:
                    temp_file.unlink()
                    deleted += 1
        
        return jsonify({"success": True, "deleted": deleted})
    except Exception as e:
        print(f"Cleanup error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("=" * 80)
    print("STEALTH CODE STORAGE SYSTEM")
    print("=" * 80)
    print(f"Repositories: {Config.TOTAL_REPOS}")
    print(f"Repository Root: {Config.REPOS_ROOT}")
    print(f"Chunk Size: {Config.RAW_CHUNK_SIZE / (1024*1024):.1f} MB")
    print(f"Max Repo Size: {Config.REPO_MAX_SIZE / (1024**3):.1f} GB")
    print(f"Existing Files: {len(repo_manager.files_metadata)}")
    print("\nStarting server on http://0.0.0.0:5000")
    print("=" * 80)
    
    app.run(host='0.0.0.0', port=5000, debug=True)