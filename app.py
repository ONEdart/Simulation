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
    BATCH_SIZE = 5
    BASE_DIR = Path(__file__).parent
    REPOS_ROOT = BASE_DIR / "simulated_github_repos"
    METADATA_ROOT = BASE_DIR / "system_metadata"
    TEMP_DIR = BASE_DIR / "temp_files"

@dataclass
class ChunkInfo:
    chunk_id: str
    repo_id: str
    file_path: str
    encoded_size: int
    index: int
    hash: str
    created_at: str

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
    def encode_to_base85(data: bytes) -> str:
        return base64.b85encode(data).decode('ascii')
    
    @staticmethod
    def decode_from_base85(encoded: str) -> bytes:
        return base64.b85decode(encoded.encode('ascii'))
    
    @staticmethod
    def compress_and_obfuscate(data: bytes) -> bytes:
        compressed = zlib.compress(data, level=6)
        obfuscated = bytearray()
        key = random.getrandbits(8)
        for byte in compressed:
            obfuscated.append(byte ^ key)
        obfuscated.insert(0, key)
        return bytes(obfuscated)
    
    @staticmethod
    def deobfuscate_and_decompress(data: bytes) -> bytes:
        key = data[0]
        obfuscated = data[1:]
        decrypted = bytearray()
        for byte in obfuscated:
            decrypted.append(byte ^ key)
        return zlib.decompress(bytes(decrypted))
    
    @staticmethod
    def generate_filename(repo_type: str, original_name: str, chunk_index: int) -> str:
        timestamp = int(time.time())
        rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        name_templates = {
            "computer-vision-dataset": [
                f"cv_sample_{timestamp}_{rand_str}.jpg.data",
                f"image_patch_{chunk_index:03d}.b85",
                f"dataset_fragment_{rand_str}.img",
                f"training_sample_{timestamp % 10000}.b85"
            ],
            "audio-processing-samples": [
                f"audio_clip_{timestamp}_{rand_str}.wav.data",
                f"sound_sample_{chunk_index:03d}.b85",
                f"waveform_{rand_str}.aud",
                f"recording_fragment_{timestamp % 10000}.b85"
            ],
            "ml-model-weights": [
                f"weights_{timestamp}_{rand_str}.pt.data",
                f"model_chunk_{chunk_index:03d}.b85",
                f"checkpoint_{rand_str}.mdl",
                f"params_fragment_{timestamp % 10000}.b85"
            ],
            "document-test-suite": [
                f"doc_{timestamp}_{rand_str}.pdf.data",
                f"text_chunk_{chunk_index:03d}.b85",
                f"document_{rand_str}.txt",
                f"page_fragment_{timestamp % 10000}.b85"
            ],
            "benchmark-data": [
                f"bench_{timestamp}_{rand_str}.csv.data",
                f"data_chunk_{chunk_index:03d}.b85",
                f"metric_{rand_str}.dat",
                f"result_fragment_{timestamp % 10000}.b85"
            ]
        }
        
        repo_type = repo_type if repo_type in name_templates else "computer-vision-dataset"
        return random.choice(name_templates[repo_type])
    
    @staticmethod
    def create_wrapper_content(encoded_data: str, repo_type: str, metadata: dict) -> str:
        wrapper_templates = {
            "computer-vision-dataset": f"""# Computer Vision Training Data
# Sample ID: {metadata.get('sample_id', 'N/A')}
# Resolution: 224x224x3
# Format: Base85 encoded JPEG
# Created: {datetime.now().isoformat()}
# Checksum: {metadata.get('checksum', 'N/A')}
# Usage: For ML model training only

{encoded_data}

# End of data sample""",
            
            "audio-processing-samples": f"""# Audio Processing Sample
# Sample ID: {metadata.get('sample_id', 'N/A')}
# Duration: 5.0s
# Format: Base85 encoded WAV
# Created: {datetime.now().isoformat()}
# Checksum: {metadata.get('checksum', 'N/A')}
# Usage: For audio ML training

{encoded_data}

# End of audio sample""",
            
            "ml-model-weights": f"""# Model Weights Fragment
# Layer: {metadata.get('layer', 'N/A')}
# Epoch: {metadata.get('epoch', 'N/A')}
# Format: Base85 encoded weights
# Created: {datetime.now().isoformat()}
# Checksum: {metadata.get('checksum', 'N/A')}
# Usage: Model training checkpoint

{encoded_data}

# End of weights fragment""",
            
            "document-test-suite": f"""# Document Test Fragment
# Doc ID: {metadata.get('doc_id', 'N/A')}
# Pages: 1
# Format: Base85 encoded PDF
# Created: {datetime.now().isoformat()}
# Checksum: {metadata.get('checksum', 'N/A')}
# Usage: OCR testing

{encoded_data}

# End of document fragment""",
            
            "benchmark-data": f"""# Benchmark Data Fragment
# Run ID: {metadata.get('run_id', 'N/A')}
# Metric: accuracy
# Format: Base85 encoded CSV
# Created: {datetime.now().isoformat()}
# Checksum: {metadata.get('checksum', 'N/A')}
# Usage: Performance testing

{encoded_data}

# End of benchmark data"""
        }
        
        template = wrapper_templates.get(repo_type, wrapper_templates["computer-vision-dataset"])
        return template

class RepoManager:
    def __init__(self):
        self.repos_root = Config.REPOS_ROOT
        self.metadata_root = Config.METADATA_ROOT
        self.temp_dir = Config.TEMP_DIR
        
        self._init_directories()
        self._load_metadata()
        
    def _init_directories(self):
        for dir_path in [self.repos_root, self.metadata_root, self.temp_dir]:
            dir_path.mkdir(exist_ok=True, parents=True)
        
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_path = self.repos_root / repo_id
            repo_path.mkdir(exist_ok=True)
            
            repo_type = self._get_repo_type(i)
            self._create_repo_structure(repo_path, repo_type)
    
    def _get_repo_type(self, repo_index: int) -> str:
        repo_types = [
            "computer-vision-dataset",
            "audio-processing-samples", 
            "ml-model-weights",
            "document-test-suite",
            "benchmark-data"
        ]
        return repo_types[repo_index % len(repo_types)]
    
    def _create_repo_structure(self, repo_path: Path, repo_type: str):
        structures = {
            "computer-vision-dataset": ["raw_images", "processed", "annotations", "scripts"],
            "audio-processing-samples": ["raw_audio", "processed", "spectrograms", "scripts"],
            "ml-model-weights": ["checkpoints", "configs", "training_logs", "scripts"],
            "document-test-suite": ["documents", "processed", "templates", "scripts"],
            "benchmark-data": ["datasets", "results", "scripts", "visualizations"]
        }
        
        for folder in structures.get(repo_type, structures["computer-vision-dataset"]):
            (repo_path / folder).mkdir(exist_ok=True)
        
        readme_content = f"""# {repo_path.name.replace('_', ' ').title()}
Repository untuk {repo_type.replace('-', ' ')}.

## Usage
See scripts/ for usage examples.

## License
Research Use Only
"""
        (repo_path / "README.md").write_text(readme_content)
        
        gitignore = """*.b85
*.data
*.tmp
__pycache__/
*.pyc
"""
        (repo_path / ".gitignore").write_text(gitignore)
        
        script_content = '''# Sample script
import numpy as np

def process_data(data):
    """Process sample data."""
    return data * 2
'''
        (repo_path / "scripts" / "process.py").write_text(script_content)
    
    def _load_metadata(self):
        metadata_file = self.metadata_root / "files.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                self.files_metadata = {}
                for file_id, file_data in data.items():
                    chunks = [ChunkInfo(**c) for c in file_data["chunks"]]
                    file_data["chunks"] = chunks
                    self.files_metadata[file_id] = FileMetadata(**file_data)
        else:
            self.files_metadata = {}
    
    def _save_metadata(self):
        metadata_file = self.metadata_root / "files.json"
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
        
        backups = list(self.metadata_root.glob("backup_*.json"))
        if len(backups) > 5:
            backups.sort()
            for old in backups[:-5]:
                old.unlink()
    
    def _select_repo_for_chunk(self, repo_type: str, chunk_size: int) -> str:
        base_repo = random.randint(0, Config.TOTAL_REPOS - 1)
        
        for offset in range(Config.TOTAL_REPOS):
            repo_idx = (base_repo + offset) % Config.TOTAL_REPOS
            repo_id = f"repo_{repo_idx:03d}"
            repo_path = self.repos_root / repo_id
            
            if self._get_repo_type(repo_idx) == repo_type:
                current_size = self._get_repo_size(repo_path)
                if current_size + chunk_size < Config.REPO_MAX_SIZE:
                    return repo_id
        
        return f"repo_{base_repo:03d}"
    
    def _get_repo_size(self, repo_path: Path) -> int:
        total = 0
        for file in repo_path.rglob("*"):
            if file.is_file():
                total += file.stat().st_size
        return total
    
    def _get_repo_structure(self, repo_type: str) -> List[str]:
        structures = {
            "computer-vision-dataset": ["raw_images", "processed", "annotations"],
            "audio-processing-samples": ["raw_audio", "processed", "spectrograms"],
            "ml-model-weights": ["checkpoints", "configs", "training_logs"],
            "document-test-suite": ["documents", "processed", "templates"],
            "benchmark-data": ["datasets", "results", "visualizations"]
        }
        return structures.get(repo_type, structures["computer-vision-dataset"])
    
    def store_chunk(self, chunk_data: bytes, original_name: str, repo_type: str, chunk_index: int) -> ChunkInfo:
        obfuscated = StealthEncoder.compress_and_obfuscate(chunk_data)
        encoded = StealthEncoder.encode_to_base85(obfuscated)
        
        repo_id = self._select_repo_for_chunk(repo_type, len(encoded))
        repo_path = self.repos_root / repo_id
        
        folder_structure = self._get_repo_structure(repo_type)
        target_folder = random.choice(folder_structure)
        
        filename = StealthEncoder.generate_filename(repo_type, original_name, chunk_index)
        file_path = repo_path / target_folder / filename
        file_path.parent.mkdir(exist_ok=True, parents=True)
        
        metadata = {
            "sample_id": f"{int(time.time())}_{random.randint(1000, 9999)}",
            "checksum": hashlib.sha256(chunk_data).hexdigest()[:16]
        }
        
        content = StealthEncoder.create_wrapper_content(encoded, repo_type, metadata)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        chunk_info = ChunkInfo(
            chunk_id=hashlib.sha256(chunk_data).hexdigest()[:16],
            repo_id=repo_id,
            file_path=str(file_path.relative_to(self.repos_root)),
            encoded_size=len(content),
            index=chunk_index,
            hash=hashlib.sha256(chunk_data).hexdigest(),
            created_at=datetime.now().isoformat()
        )
        
        return chunk_info
    
    def retrieve_chunk(self, chunk_info: ChunkInfo) -> bytes:
        file_path = self.repos_root / chunk_info.file_path
        
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
        
        obfuscated = StealthEncoder.decode_from_base85(encoded_data)
        chunk_data = StealthEncoder.deobfuscate_and_decompress(obfuscated)
        
        return chunk_data
    
    def delete_chunk(self, chunk_info: ChunkInfo):
        file_path = self.repos_root / chunk_info.file_path
        if file_path.exists():
            file_path.unlink()
            
            try:
                if file_path.parent.is_dir() and not any(file_path.parent.iterdir()):
                    file_path.parent.rmdir()
            except:
                pass

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

repo_manager = RepoManager()

@app.route('/')
def index():
    return send_file('static/index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        filename = secure_filename(file.filename)
        file_data = file.read()
        
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"
        
        repo_types = ["computer-vision-dataset", "audio-processing-samples", 
                     "ml-model-weights", "document-test-suite", "benchmark-data"]
        
        tags = []
        if mime_type.startswith('image/'):
            repo_type = "computer-vision-dataset"
            tags = ["image", "media"]
        elif mime_type.startswith('audio/'):
            repo_type = "audio-processing-samples"
            tags = ["audio", "media"]
        elif mime_type.startswith('video/'):
            repo_type = "computer-vision-dataset"
            tags = ["video", "media"]
        elif mime_type == 'application/pdf':
            repo_type = "document-test-suite"
            tags = ["document", "pdf"]
        elif mime_type.startswith('text/'):
            repo_type = "document-test-suite"
            tags = ["text", "document"]
        else:
            repo_type = random.choice(repo_types)
            tags = ["binary", "data"]
        
        chunks = []
        chunk_count = (len(file_data) + Config.RAW_CHUNK_SIZE - 1) // Config.RAW_CHUNK_SIZE
        
        for i in range(chunk_count):
            start = i * Config.RAW_CHUNK_SIZE
            end = min(start + Config.RAW_CHUNK_SIZE, len(file_data))
            chunk_data = file_data[start:end]
            
            chunk_info = repo_manager.store_chunk(chunk_data, filename, repo_type, i)
            chunk_info.index = i
            chunks.append(chunk_info)
        
        file_id = hashlib.sha256(
            f"{filename}{datetime.now().isoformat()}{random.randint(1, 1000000)}".encode()
        ).hexdigest()[:20]
        
        file_metadata = FileMetadata(
            file_id=file_id,
            original_name=filename,
            display_name=filename,
            original_size=len(file_data),
            mime_type=mime_type,
            upload_time=datetime.now().isoformat(),
            chunks=chunks,
            chunk_count=chunk_count,
            tags=tags,
            description=f"Uploaded {filename}"
        )
        
        repo_manager.files_metadata[file_id] = file_metadata
        repo_manager._save_metadata()
        
        return jsonify({
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "size": len(file_data),
            "chunks": chunk_count,
            "upload_time": file_metadata.upload_time
        })
        
    except Exception as e:
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
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>', methods=['GET'])
def download_file(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        chunks = sorted(file_meta.chunks, key=lambda x: x.index)
        
        assembled_data = bytearray()
        for chunk_info in chunks:
            chunk_data = repo_manager.retrieve_chunk(chunk_info)
            assembled_data.extend(chunk_data)
        
        temp_path = Config.TEMP_DIR / f"download_{file_id}_{int(time.time())}"
        with open(temp_path, 'wb') as f:
            f.write(assembled_data)
        
        return send_file(
            str(temp_path),
            as_attachment=True,
            download_name=file_meta.original_name,
            mimetype=file_meta.mime_type
        )
        
    except Exception as e:
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
        
        return jsonify({"success": True, "message": f"File deleted"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        total_files = len(repo_manager.files_metadata)
        total_size = sum(f.original_size for f in repo_manager.files_metadata.values())
        
        repo_sizes = {}
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_path = Config.REPOS_ROOT / repo_id
            if repo_path.exists():
                repo_sizes[repo_id] = repo_manager._get_repo_size(repo_path)
        
        return jsonify({
            "total_files": total_files,
            "total_size": total_size,
            "repo_sizes": repo_sizes,
            "repo_capacity": Config.REPO_MAX_SIZE
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("=" * 80)
    print("GITHUB DRIVE SIMULATOR - STEALTH EDITION")
    print("=" * 80)
    print(f"Repos Directory: {Config.REPOS_ROOT}")
    print(f"Total Repositories: {Config.TOTAL_REPOS}")
    print(f"Max Repo Size: {Config.REPO_MAX_SIZE / (1024**3):.1f} GB")
    print("\nServer running on http://0.0.0.0:5000")
    print("=" * 80)
    
    app.run(host='0.0.0.0', port=5000, debug=True)