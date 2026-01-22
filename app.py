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
    RAW_CHUNK_SIZE = 4 * 1024 * 1024
    TOTAL_REPOS = 100
    REPO_MAX_SIZE = 1 * 1024 * 1024 * 1024
    BASE_DIR = Path(__file__).parent
    REPOS_ROOT = BASE_DIR / "simulated_github_repos"
    METADATA_ROOT = BASE_DIR / "system_metadata"
    TEMP_DIR = BASE_DIR / "temp_files"
    REPO_TYPES = [
        "computer-vision-dataset",
        "audio-processing-samples",
        "ml-model-weights",
        "document-test-suite",
        "benchmark-data"
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
    def generate_stealth_filename(repo_type: str, chunk_index: int) -> str:
        timestamp = int(time.time())
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        templates = {
            "computer-vision-dataset": [
                f"sample_{timestamp}_{random_str}.b85",
                f"image_{chunk_index:03d}_{random_str}.b85",
                f"dataset_{timestamp}_{chunk_index:03d}.data",
                f"cv_sample_{random_str}.b85"
            ],
            "audio-processing-samples": [
                f"audio_{timestamp}_{random_str}.b85",
                f"sound_{chunk_index:03d}_{random_str}.b85",
                f"recording_{timestamp}_{chunk_index:03d}.data",
                f"audio_sample_{random_str}.b85"
            ],
            "ml-model-weights": [
                f"weights_{timestamp}_{random_str}.b85",
                f"model_{chunk_index:03d}_{random_str}.b85",
                f"checkpoint_{timestamp}_{chunk_index:03d}.data",
                f"params_{random_str}.b85"
            ],
            "document-test-suite": [
                f"doc_{timestamp}_{random_str}.b85",
                f"text_{chunk_index:03d}_{random_str}.b85",
                f"document_{timestamp}_{chunk_index:03d}.data",
                f"page_{random_str}.b85"
            ],
            "benchmark-data": [
                f"bench_{timestamp}_{random_str}.b85",
                f"data_{chunk_index:03d}_{random_str}.b85",
                f"metric_{timestamp}_{chunk_index:03d}.data",
                f"result_{random_str}.b85"
            ]
        }
        
        repo_template = templates.get(repo_type, templates["computer-vision-dataset"])
        return random.choice(repo_template)

    @staticmethod
    def create_stealth_content(encoded_data: str, repo_type: str, metadata: dict) -> str:
        timestamp = datetime.now().isoformat()
        
        wrappers = {
            "computer-vision-dataset": f"""# Computer Vision Dataset Fragment
# Created: {timestamp}
# Fragment ID: {metadata.get('fragment_id', 'N/A')}
# Format: Base85 encoded image data
# Checksum: {metadata.get('checksum', 'N/A')}
# Notes: For research and development use

{encoded_data}

# End of fragment
""",
            "audio-processing-samples": f"""# Audio Processing Sample Fragment
# Created: {timestamp}
# Fragment ID: {metadata.get('fragment_id', 'N/A')}
# Format: Base85 encoded audio data
# Checksum: {metadata.get('checksum', 'N/A')}
# Notes: Audio sample for machine learning

{encoded_data}

# End of fragment
""",
            "ml-model-weights": f"""# Model Weights Fragment
# Created: {timestamp}
# Fragment ID: {metadata.get('fragment_id', 'N/A')}
# Format: Base85 encoded model weights
# Checksum: {metadata.get('checksum', 'N/A')}
# Notes: Neural network parameters

{encoded_data}

# End of fragment
""",
            "document-test-suite": f"""# Document Test Fragment
# Created: {timestamp}
# Fragment ID: {metadata.get('fragment_id', 'N/A')}
# Format: Base85 encoded document data
# Checksum: {metadata.get('checksum', 'N/A')}
# Notes: Test document for OCR processing

{encoded_data}

# End of fragment
""",
            "benchmark-data": f"""# Benchmark Data Fragment
# Created: {timestamp}
# Fragment ID: {metadata.get('fragment_id', 'N/A')}
# Format: Base85 encoded benchmark data
# Checksum: {metadata.get('checksum', 'N/A')}
# Notes: Performance testing data

{encoded_data}

# End of fragment
"""
        }
        
        return wrappers.get(repo_type, wrappers["computer-vision-dataset"])

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
            
            # Initialize cache entry FIRST
            self.repo_structure_cache[repo_id] = {
                "type": repo_type,
                "size": 0,
                "chunk_count": 0,
                "folders": []
            }
            
            # Then create artifacts
            self._create_repo_artifacts(repo_path, repo_type, repo_id)
    
    def _create_repo_artifacts(self, repo_path: Path, repo_type: str, repo_id: str):
        structures = {
            "computer-vision-dataset": ["raw_images", "processed", "annotations", "scripts", "models"],
            "audio-processing-samples": ["raw_audio", "processed", "spectrograms", "scripts", "models"],
            "ml-model-weights": ["checkpoints", "configs", "training_logs", "scripts", "exports"],
            "document-test-suite": ["documents", "processed", "templates", "scripts", "results"],
            "benchmark-data": ["datasets", "results", "scripts", "visualizations", "logs"]
        }
        
        folders = structures.get(repo_type, structures["computer-vision-dataset"])
        
        # Update cache with folders
        if repo_id in self.repo_structure_cache:
            self.repo_structure_cache[repo_id]["folders"] = folders
        
        for folder in folders:
            (repo_path / folder).mkdir(exist_ok=True)
            
            if random.random() > 0.5:
                dummy_file = repo_path / folder / f"placeholder_{''.join(random.choices(string.ascii_lowercase, k=6))}.txt"
                dummy_file.write_text(f"# Placeholder file for {repo_type}\n# Generated: {datetime.now().isoformat()}\n")
        
        readme_content = f"""# {repo_id.replace('_', ' ').title()}
Repository for {repo_type.replace('-', ' ')} data.

## Structure
{chr(10).join(f'- `{folder}/`' for folder in folders)}

## Usage
This repository contains data samples for research and development purposes.

## License
Research Use Only - Not for Commercial Use
"""
        (repo_path / "README.md").write_text(readme_content)
        
        script_content = '''#!/usr/bin/env python3
# Sample processing script

def process_data(input_data):
    """Process input data."""
    return input_data

if __name__ == "__main__":
    print("Data processing script")
'''
        (repo_path / "scripts" / "process.py").write_text(script_content)
        
        gitignore_content = """*.b85
*.data
*.tmp
__pycache__/
*.pyc
*.pyo
*.pyd
.DS_Store
*.log
"""
        (repo_path / ".gitignore").write_text(gitignore_content)
    
    def _load_metadata(self):
        metadata_file = self.metadata_root / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                    self.files_metadata = {}
                    for file_id, file_data in data.items():
                        chunks = [ChunkInfo(**c) for c in file_data["chunks"]]
                        file_data["chunks"] = chunks
                        self.files_metadata[file_id] = FileMetadata(**file_data)
                print(f"Loaded metadata for {len(self.files_metadata)} files")
            except Exception as e:
                print(f"Error loading metadata: {e}")
                self.files_metadata = {}
        else:
            self.files_metadata = {}
            print("No existing metadata found, starting fresh")
    
    def _save_metadata(self):
        metadata_file = self.metadata_root / "metadata.json"
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
    
    def _select_repo_for_chunk(self, repo_type: str, chunk_size: int) -> str:
        candidate_repos = []
        
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            if Config.REPO_TYPES[i % len(Config.REPO_TYPES)] == repo_type:
                current_size = self._get_repo_size(repo_id)
                if current_size + chunk_size < Config.REPO_MAX_SIZE:
                    candidate_repos.append((repo_id, current_size))
        
        if candidate_repos:
            candidate_repos.sort(key=lambda x: x[1])
            return candidate_repos[0][0]
        
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            current_size = self._get_repo_size(repo_id)
            if current_size + chunk_size < Config.REPO_MAX_SIZE:
                return repo_id
        
        raise Exception(f"No repository with enough space for {chunk_size} bytes chunk")
    
    def store_chunk(self, chunk_data: bytes, original_name: str, chunk_index: int) -> ChunkInfo:
        xor_key = random.randint(1, 255)
        obfuscated_data, _ = StealthEncoder.obfuscate_data(chunk_data, xor_key)
        
        compressed_data = StealthEncoder.compress_data(obfuscated_data, level=6)
        
        encoded_data = StealthEncoder.encode_to_base85(compressed_data)
        
        repo_type = random.choice(Config.REPO_TYPES)
        repo_id = self._select_repo_for_chunk(repo_type, len(encoded_data) + 500)
        
        filename = StealthEncoder.generate_stealth_filename(repo_type, chunk_index)
        
        repo_folders = self.repo_structure_cache[repo_id]["folders"]
        target_folder = random.choice(repo_folders)
        
        file_path = self.repos_root / repo_id / target_folder / filename
        file_path.parent.mkdir(exist_ok=True, parents=True)
        
        metadata = {
            "fragment_id": f"frag_{hashlib.sha256(chunk_data).hexdigest()[:8]}",
            "checksum": hashlib.sha256(chunk_data).hexdigest()[:16]
        }
        
        content = StealthEncoder.create_stealth_content(encoded_data, repo_type, metadata)
        
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
            compression_level=6
        )
        
        print(f"Stored chunk {chunk_index} to {file_path} (size: {len(content)} bytes)")
        
        return chunk_info
    
    def retrieve_chunk(self, chunk_info: ChunkInfo) -> bytes:
        file_path = self.repos_root / chunk_info.file_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"Chunk file not found: {chunk_info.file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        encoded_data = ""
        in_data_section = False
        
        for line in lines:
            if line.strip() and not line.startswith('#'):
                if not in_data_section:
                    in_data_section = True
                encoded_data += line
        
        compressed_data = StealthEncoder.decode_from_base85(encoded_data)
        
        obfuscated_data = StealthEncoder.decompress_data(compressed_data)
        
        xor_key = int(chunk_info.xor_key) if chunk_info.xor_key else 0
        if xor_key == 0:
            print(f"Warning: No XOR key for chunk {chunk_info.chunk_id}, trying to recover")
            xor_key = 1
        
        chunk_data = StealthEncoder.deobfuscate_data(obfuscated_data, xor_key)
        
        return chunk_data
    
    def delete_chunk(self, chunk_info: ChunkInfo):
        file_path = self.repos_root / chunk_info.file_path
        
        if file_path.exists():
            file_path.unlink()
            print(f"Deleted chunk file: {file_path}")
            
            try:
                if file_path.parent.is_dir() and not any(file_path.parent.iterdir()):
                    file_path.parent.rmdir()
            except Exception as e:
                print(f"Could not remove empty directory: {e}")
    
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
            except Exception as e:
                print(f"Error retrieving chunk {chunk_info.chunk_id}: {e}")
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
            except Exception as e:
                print(f"Error encoding image: {e}")
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
            except Exception as e:
                print(f"Error decoding text: {e}")
                return None
        
        elif mime_type == 'application/pdf':
            try:
                base64_data = base64.b64encode(file_data).decode('utf-8')
                return {
                    "type": "pdf",
                    "data": base64_data,
                    "mime_type": mime_type
                }
            except Exception as e:
                print(f"Error encoding PDF: {e}")
                return None
        
        return {
            "type": "binary",
            "message": "Binary file cannot be previewed",
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
        
        print(f"Uploading {filename} ({file_size} bytes) as {num_chunks} chunks")
        
        for i in range(num_chunks):
            start = i * Config.RAW_CHUNK_SIZE
            end = min(start + Config.RAW_CHUNK_SIZE, file_size)
            chunk_data = file_data[start:end]
            
            chunk_info = repo_manager.store_chunk(chunk_data, filename, i)
            chunk_info.index = i
            chunks.append(chunk_info)
            
            print(f"  Chunk {i+1}/{num_chunks} stored")
        
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
        
        print(f"Upload completed: {filename} -> {file_id}")
        
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
                "error": f"File too large for preview (max {preview_data['max_allowed'] / (1024*1024)}MB)"
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
        
        print(f"Deleting {file_meta.original_name} ({len(file_meta.chunks)} chunks)")
        
        for i, chunk_info in enumerate(file_meta.chunks):
            print(f"  Deleting chunk {i+1}/{len(file_meta.chunks)} from {chunk_info.file_path}")
            repo_manager.delete_chunk(chunk_info)
        
        del repo_manager.files_metadata[file_id]
        repo_manager._save_metadata()
        
        print(f"File {file_id} deleted successfully")
        
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
    print("GITHUB DRIVE SIMULATOR - STEALTH STORAGE SYSTEM")
    print("=" * 80)
    print(f"Repositories: {Config.TOTAL_REPOS}")
    print(f"Repository Root: {Config.REPOS_ROOT}")
    print(f"Chunk Size: {Config.RAW_CHUNK_SIZE / (1024*1024):.1f} MB")
    print(f"Max Repo Size: {Config.REPO_MAX_SIZE / (1024**3):.1f} GB")
    print(f"Existing Files: {len(repo_manager.files_metadata)}")
    print("\nStarting server on http://0.0.0.0:5000")
    print("=" * 80)
    
    app.run(host='0.0.0.0', port=5000, debug=True)