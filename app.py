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
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import threading
from queue import Queue

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

class Config:
    RAW_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB per chunk asli
    ENCODED_CHUNK_SIZE = 5 * 1024 * 1024  # ~5MB setelah encoding
    TOTAL_REPOS = 100
    ACTIVE_REPOS = 15
    REPO_MAX_SIZE = 1 * 1024 * 1024 * 1024  # 1 GB per repo
    REPO_WARNING_SIZE = int(REPO_MAX_SIZE * 0.8)
    BATCH_SIZE = 5
    MIN_BATCH_UTILIZATION = 0.3
    ENCODING_TYPES = ["base85", "ascii85", "base64"]
    REPO_TYPES = [
        "computer-vision-dataset",
        "audio-processing-samples", 
        "ml-model-weights",
        "document-test-suite",
        "benchmark-data"
    ]
    BASE_DIR = Path(__file__).parent
    REPOS_ROOT = BASE_DIR / "simulated_github_repos"
    METADATA_ROOT = BASE_DIR / "system_metadata"
    TEMP_DIR = BASE_DIR / "temp_files"
    LOGS_DIR = BASE_DIR / "logs"
    MAX_PARALLEL_CHUNKS = 8
    CACHE_SIZE = 100

@dataclass
class ChunkInfo:
    chunk_id: str
    repo_id: str
    file_path: str
    encoded_size: int
    index: int
    encoding_type: str
    hash: str
    created_at: str
    batch_id: int

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
    is_hidden: bool = False
    batch_distribution: Dict[int, int] = None

@dataclass
class RepoInfo:
    repo_id: str
    repo_type: str
    display_name: str
    description: str
    created_at: str
    chunk_count: int
    total_size: int  # Real size on disk
    last_accessed: str
    batch_id: int
    is_active: bool
    health_score: float
    utilization: float

@dataclass
class BatchInfo:
    batch_id: int
    repo_ids: List[str]
    created_at: str
    is_active: bool
    total_size: int
    utilization: float
    avg_health: float

@dataclass  
class SystemState:
    total_files: int
    total_size: int  # Original total size of all files
    total_chunks: int
    active_batch_ids: List[int]
    batch_rotation_schedule: Dict[str, str]
    stealth_mode: str
    last_health_check: str
    storage_stats: Dict[str, int]

class StealthUtility:
    @staticmethod
    def generate_repo_structure(repo_type: str) -> Dict:
        structures = {
            "computer-vision-dataset": {
                "folders": ["raw_samples", "augmented", "annotations", "test_suite"],
                "file_types": [".py", ".md", ".json", ".yaml", ".txt", ".jpg", ".png"]
            },
            "audio-processing-samples": {
                "folders": ["raw_audio", "processed", "spectrograms", "test_data"],
                "file_types": [".py", ".md", ".json", ".wav", ".mp3", ".txt"]
            },
            "ml-model-weights": {
                "folders": ["checkpoints", "configs", "training_logs", "evaluation"],
                "file_types": [".py", ".md", ".json", ".pt", ".h5", ".txt"]
            },
            "document-test-suite": {
                "folders": ["documents", "processed", "templates", "test_cases"],
                "file_types": [".py", ".md", ".json", ".pdf", ".docx", ".txt"]
            },
            "benchmark-data": {
                "folders": ["datasets", "results", "scripts", "visualizations"],
                "file_types": [".py", ".md", ".json", ".csv", ".txt", ".html"]
            }
        }
        return structures.get(repo_type, structures["computer-vision-dataset"])
    
    @staticmethod
    def generate_credible_filename(original_name: str, repo_type: str) -> str:
        prefixes = {
            "computer-vision-dataset": ["sample", "image", "photo", "frame", "dataset"],
            "audio-processing-samples": ["audio", "recording", "sample", "track", "sound"],
            "ml-model-weights": ["model", "weights", "checkpoint", "params", "network"],
            "document-test-suite": ["doc", "document", "test", "sample", "example"],
            "benchmark-data": ["data", "benchmark", "metric", "result", "measure"]
        }
        
        prefix_options = prefixes.get(repo_type, ["data"])
        prefix = random.choice(prefix_options)
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        
        if repo_type == "computer-vision-dataset":
            new_ext = random.choice([".png", ".jpg", ".jpeg", ".bmp"])
        elif repo_type == "audio-processing-samples":
            new_ext = random.choice([".wav", ".mp3", ".flac", ".ogg"])
        elif repo_type == "ml-model-weights":
            new_ext = random.choice([".bin", ".pt", ".h5", ".pkl"])
        elif repo_type == "document-test-suite":
            new_ext = random.choice([".pdf", ".txt", ".md", ".json"])
        elif repo_type == "benchmark-data":
            new_ext = random.choice([".csv", ".json", ".txt", ".dat"])
        else:
            new_ext = ".dat"
        
        return f"{prefix}_{suffix}{new_ext}"
    
    @staticmethod
    def encode_data(data: bytes, encoding_type: str = "base85") -> str:
        if encoding_type == "base85":
            return base64.b85encode(data).decode('ascii')
        elif encoding_type == "ascii85":
            return base64.a85encode(data).decode('ascii')
        elif encoding_type == "base64":
            return base64.b64encode(data).decode('ascii')
        else:
            return base64.b85encode(data).decode('ascii')
    
    @staticmethod
    def decode_data(encoded_text: str, encoding_type: str = "base85") -> bytes:
        if encoding_type == "base85":
            return base64.b85decode(encoded_text.encode('ascii'))
        elif encoding_type == "ascii85":
            return base64.a85decode(encoded_text.encode('ascii'))
        elif encoding_type == "base64":
            return base64.b64decode(encoded_text.encode('ascii'))
        else:
            return base64.b85decode(encoded_text.encode('ascii'))

class BatchManager:
    def __init__(self, total_repos: int = 100, batch_size: int = 5):
        self.total_repos = total_repos
        self.batch_size = batch_size
        self.batches: Dict[int, BatchInfo] = {}
        self.repo_to_batch: Dict[str, int] = {}
        self.active_batches: List[int] = []
        self._init_batches()
    
    def _init_batches(self):
        num_batches = math.ceil(self.total_repos / self.batch_size)
        
        for batch_id in range(num_batches):
            start_idx = batch_id * self.batch_size
            end_idx = min(start_idx + self.batch_size, self.total_repos)
            repo_ids = [f"repo_{i:03d}" for i in range(start_idx, end_idx)]
            
            for repo_id in repo_ids:
                self.repo_to_batch[repo_id] = batch_id
            
            self.batches[batch_id] = BatchInfo(
                batch_id=batch_id,
                repo_ids=repo_ids,
                created_at=datetime.now().isoformat(),
                is_active=False,
                total_size=0,
                utilization=0.0,
                avg_health=1.0
            )
        
        self.set_active_batches([0])
    
    def set_active_batches(self, batch_ids: List[int]):
        for batch_id in self.active_batches:
            self.batches[batch_id].is_active = False
        
        self.active_batches = batch_ids
        for batch_id in batch_ids:
            if batch_id in self.batches:
                self.batches[batch_id].is_active = True
    
    def get_repos_in_batch(self, batch_id: int) -> List[str]:
        if batch_id in self.batches:
            return self.batches[batch_id].repo_ids
        return []
    
    def get_batch_for_repo(self, repo_id: str) -> Optional[int]:
        return self.repo_to_batch.get(repo_id)
    
    def get_available_batch(self, required_size: int) -> Tuple[int, str]:
        for batch_id in self.active_batches:
            batch = self.batches[batch_id]
            if batch.total_size + required_size <= Config.REPO_MAX_SIZE:
                return batch_id, "active"
        
        for batch_id, batch in self.batches.items():
            if batch_id not in self.active_batches:
                if batch.total_size + required_size <= Config.REPO_MAX_SIZE:
                    return batch_id, "inactive"
        
        lowest_utilization = float('inf')
        selected_batch = None
        
        for batch_id, batch in self.batches.items():
            if batch.utilization < lowest_utilization:
                lowest_utilization = batch.utilization
                selected_batch = batch_id
        
        return selected_batch, "full_rotation_needed"
    
    def update_batch_stats(self, batch_id: int, size_delta: int):
        if batch_id in self.batches:
            batch = self.batches[batch_id]
            batch.total_size += size_delta
            batch.utilization = batch.total_size / Config.REPO_MAX_SIZE
            
            if 0.6 <= batch.utilization <= 0.8:
                batch.avg_health = 0.9
            elif 0.4 <= batch.utilization <= 0.9:
                batch.avg_health = 0.7
            else:
                batch.avg_health = 0.5
    
    def rotate_batches(self):
        if len(self.batches) <= 1:
            return self.active_batches
        
        sorted_batches = sorted(
            self.batches.items(),
            key=lambda x: x[1].utilization,
            reverse=True
        )
        
        to_deactivate = []
        for batch_id, batch in sorted_batches:
            if batch.is_active and batch.utilization > Config.MIN_BATCH_UTILIZATION:
                to_deactivate.append(batch_id)
                if len(to_deactivate) >= self.batch_size:
                    break
        
        to_activate = []
        for batch_id, batch in sorted_batches:
            if not batch.is_active and batch_id not in to_deactivate:
                to_activate.append(batch_id)
                if len(to_activate) >= self.batch_size:
                    break
        
        for batch_id in to_deactivate:
            self.batches[batch_id].is_active = False
        
        for batch_id in to_activate:
            self.batches[batch_id].is_active = True
        
        self.active_batches = [
            bid for bid in self.active_batches 
            if bid not in to_deactivate
        ] + to_activate
        
        return {
            "rotated_at": datetime.now().isoformat(),
            "deactivated": to_deactivate,
            "activated": to_activate,
            "new_active": self.active_batches
        }

class RepoManager:
    def __init__(self):
        self.repos_root = Config.REPOS_ROOT
        self.metadata_root = Config.METADATA_ROOT
        self.temp_dir = Config.TEMP_DIR
        self.logs_dir = Config.LOGS_DIR
        
        self.batch_manager = BatchManager(
            total_repos=Config.TOTAL_REPOS,
            batch_size=Config.BATCH_SIZE
        )
        
        self._init_directories()
        self._load_or_create_metadata()
        
        self.task_queue = Queue()
        self._start_background_worker()
    
    def _init_directories(self):
        """Initialize all directories and ensure they're writable"""
        for dir_path in [self.repos_root, self.metadata_root, 
                        self.temp_dir, self.logs_dir]:
            dir_path.mkdir(exist_ok=True, parents=True)
            # Test write permission
            test_file = dir_path / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                print(f"✓ Directory writable: {dir_path}")
            except Exception as e:
                print(f"✗ Directory NOT writable: {dir_path} - {e}")
        
        # Create repository structure
        for i in range(Config.TOTAL_REPOS):
            repo_id = f"repo_{i:03d}"
            repo_path = self.repos_root / repo_id
            repo_path.mkdir(exist_ok=True)
            
            repo_type = self._get_repo_type(i)
            structure = StealthUtility.generate_repo_structure(repo_type)
            
            for folder in structure["folders"]:
                (repo_path / folder).mkdir(exist_ok=True)
            
            self._create_repo_artifacts(repo_path, repo_type, repo_id)
    
    def _get_repo_type(self, repo_index: int) -> str:
        return Config.REPO_TYPES[repo_index % len(Config.REPO_TYPES)]
    
    def _create_repo_artifacts(self, repo_path: Path, repo_type: str, repo_id: str):
        readme_content = f"""# {repo_id.replace('_', ' ').title()}
Repository untuk {repo_type.replace('-', ' ')}.
## Struktur
- `raw_samples/`: Data mentah
- `processed/`: Data diproses
- `scripts/`: Skrip preprocessing
- `models/`: Model terlatih
## Penggunaan
Lihat examples/tutorial.ipynb
## Lisensi
CC BY-SA 4.0
"""
        (repo_path / "README.md").write_text(readme_content)
        
        scripts = [
            ("load_dataset.py", self._generate_loader_script(repo_type)),
            ("preprocess.py", self._generate_preprocess_script()),
            ("utils.py", self._generate_utils_script()),
            ("config.yaml", self._generate_config_yaml(repo_type))
        ]
        
        for filename, content in scripts:
            file_path = repo_path / "scripts" / filename
            file_path.parent.mkdir(exist_ok=True)
            file_path.write_text(content)
        
        gitignore = """*.b85
*.bin
*.dat
*.tmp
__pycache__/
*.pyc
*.log
.DS_Store
"""
        (repo_path / ".gitignore").write_text(gitignore)
    
    def _generate_loader_script(self, repo_type: str) -> str:
        templates = {
            "computer-vision-dataset": """
import cv2
import numpy as np
from pathlib import Path

class DatasetLoader:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
    
    def load_image(self, image_path: str):
        img = cv2.imread(str(image_path))
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            """,
            "audio-processing-samples": """
import librosa
import numpy as np

class AudioLoader:
    def __init__(self, sample_rate=22050):
        self.sample_rate = sample_rate
    
    def load_audio(self, file_path: str):
        audio, sr = librosa.load(file_path, sr=self.sample_rate)
        return audio
            """,
            "ml-model-weights": """
import torch
import tensorflow as tf
from pathlib import Path

class ModelLoader:
    def __init__(self, model_dir: str):
        self.model_dir = Path(model_dir)
    
    def load_pytorch_model(self, model_path: str):
        return torch.load(model_path, map_location='cpu')
            """
        }
        return templates.get(repo_type, templates["computer-vision-dataset"])
    
    def _generate_preprocess_script(self) -> str:
        return """
import numpy as np

class Preprocessor:
    def __init__(self):
        pass
    
    def preprocess_image(self, image):
        return image / 255.0
"""
    
    def _generate_utils_script(self) -> str:
        return """
import json
from pathlib import Path

def save_metadata(metadata, path: str):
    with open(path, 'w') as f:
        json.dump(metadata, f, indent=2)

def load_metadata(path: str):
    with open(path, 'r') as f:
        return json.load(f)
"""
    
    def _generate_config_yaml(self, repo_type: str) -> str:
        configs = {
            "computer-vision-dataset": """
dataset:
  name: "CV Dataset"
  image_size: [224, 224, 3]
training:
  batch_size: 32
  epochs: 100
""",
            "audio-processing-samples": """
dataset:
  name: "Audio Samples"
  sample_rate: 22050
  duration_seconds: 5.0
"""
        }
        return configs.get(repo_type, configs["computer-vision-dataset"])
    
    def _load_or_create_metadata(self):
        metadata_file = self.metadata_root / "system_state.json"
        
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                data = json.load(f)
            
            self.system_state = SystemState(**data["system_state"])
            
            self.files_metadata = {}
            for file_id, file_data in data["files"].items():
                chunks = [ChunkInfo(**c) for c in file_data["chunks"]]
                file_data["chunks"] = chunks
                self.files_metadata[file_id] = FileMetadata(**file_data)
            
            self.repos_info = {}
            for repo_id, repo_data in data["repos"].items():
                self.repos_info[repo_id] = RepoInfo(**repo_data)
            
            for batch_id, batch_data in data.get("batches", {}).items():
                if batch_id in self.batch_manager.batches:
                    batch_info = BatchInfo(**batch_data)
                    self.batch_manager.batches[int(batch_id)] = batch_info
            
            # Recalculate real sizes from disk
            self._recalculate_real_sizes()
            
        else:
            self.system_state = SystemState(
                total_files=0,
                total_size=0,
                total_chunks=0,
                active_batch_ids=[0],
                batch_rotation_schedule={},
                stealth_mode="normal",
                last_health_check=datetime.now().isoformat(),
                storage_stats={
                    "total_capacity": Config.TOTAL_REPOS * Config.REPO_MAX_SIZE,
                    "used": 0,
                    "available": Config.TOTAL_REPOS * Config.REPO_MAX_SIZE
                }
            )
            
            self.files_metadata = {}
            self.repos_info = {}
            
            for i in range(Config.TOTAL_REPOS):
                repo_id = f"repo_{i:03d}"
                repo_type = self._get_repo_type(i)
                batch_id = self.batch_manager.get_batch_for_repo(repo_id)
                
                self.repos_info[repo_id] = RepoInfo(
                    repo_id=repo_id,
                    repo_type=repo_type,
                    display_name=f"{repo_type.replace('-', ' ').title()} {i+1}",
                    description=f"Dataset untuk {repo_type.replace('-', ' ')}",
                    created_at=datetime.now().isoformat(),
                    chunk_count=0,
                    total_size=0,  # Will be calculated from disk
                    last_accessed=datetime.now().isoformat(),
                    batch_id=batch_id,
                    is_active=(batch_id in self.batch_manager.active_batches),
                    health_score=1.0,
                    utilization=0.0
                )
            
            self._save_metadata()
    
    def _recalculate_real_sizes(self):
        """Recalculate real file sizes from disk"""
        for repo_id, repo_info in self.repos_info.items():
            repo_path = self.repos_root / repo_id
            if repo_path.exists():
                actual_size = self._calculate_folder_size(repo_path)
                repo_info.total_size = actual_size
                repo_info.utilization = repo_info.total_size / Config.REPO_MAX_SIZE
    
    def _save_metadata(self):
        metadata_file = self.metadata_root / "system_state.json"
        
        data = {
            "system_state": asdict(self.system_state),
            "files": {},
            "repos": {},
            "batches": {}
        }
        
        for file_id, file_meta in self.files_metadata.items():
            file_dict = asdict(file_meta)
            file_dict["chunks"] = [asdict(c) for c in file_meta.chunks]
            data["files"][file_id] = file_dict
        
        for repo_id, repo_info in self.repos_info.items():
            data["repos"][repo_id] = asdict(repo_info)
        
        for batch_id, batch_info in self.batch_manager.batches.items():
            data["batches"][str(batch_id)] = asdict(batch_info)
        
        with open(metadata_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        backup_dir = self.metadata_root / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_file = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(backup_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        backups = list(backup_dir.glob("backup_*.json"))
        backups.sort()
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                old_backup.unlink()
    
    def _start_background_worker(self):
        def worker():
            while True:
                task = self.task_queue.get()
                if task is None:
                    break
                
                try:
                    task_type = task.get("type")
                    
                    if task_type == "health_check":
                        self._perform_health_check()
                    elif task_type == "rotate_batches":
                        self._rotate_batches_task()
                    elif task_type == "cleanup_temp":
                        self._cleanup_temp_files()
                    elif task_type == "update_stats":
                        self._update_system_stats()
                    
                except Exception as e:
                    self._log_error(f"Background task failed: {str(e)}")
                
                finally:
                    self.task_queue.task_done()
        
        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()
        
        self._schedule_periodic_tasks()
    
    def _schedule_periodic_tasks(self):
        def schedule_task(task_type, delay_seconds):
            def task_wrapper():
                time.sleep(delay_seconds)
                self.task_queue.put({"type": task_type})
                schedule_task(task_type, delay_seconds)
            
            thread = threading.Thread(target=task_wrapper, daemon=True)
            thread.start()
        
        schedule_task("health_check", 300)
        schedule_task("rotate_batches", 1800)
        schedule_task("cleanup_temp", 3600)
        schedule_task("update_stats", 120)
    
    def _perform_health_check(self):
        try:
            for repo_id, repo_info in self.repos_info.items():
                repo_path = self.repos_root / repo_id
                
                if not repo_path.exists():
                    repo_info.health_score = 0.1
                    continue
                
                actual_size = self._calculate_folder_size(repo_path)
                size_diff = abs(actual_size - repo_info.total_size)
                
                if size_diff < 1024:
                    accuracy_score = 1.0
                elif size_diff < 1024 * 1024:
                    accuracy_score = 0.8
                else:
                    accuracy_score = 0.5
                
                utilization = repo_info.utilization
                if 0.3 <= utilization <= 0.8:
                    utilization_score = 0.9
                elif utilization < 0.9:
                    utilization_score = 0.7
                else:
                    utilization_score = 0.4
                
                repo_info.health_score = (accuracy_score + utilization_score) / 2
            
            self.system_state.last_health_check = datetime.now().isoformat()
            self._log_info("Health check completed")
            
        except Exception as e:
            self._log_error(f"Health check failed: {str(e)}")
    
    def _rotate_batches_task(self):
        try:
            rotation_info = self.batch_manager.rotate_batches()
            
            for repo_id, repo_info in self.repos_info.items():
                batch_id = repo_info.batch_id
                repo_info.is_active = (batch_id in self.batch_manager.active_batches)
            
            self.system_state.active_batch_ids = self.batch_manager.active_batches
            self.system_state.batch_rotation_schedule = rotation_info
            
            self._save_metadata()
            self._log_info(f"Batch rotated: {rotation_info}")
            
        except Exception as e:
            self._log_error(f"Batch rotation failed: {str(e)}")
    
    def _cleanup_temp_files(self):
        try:
            temp_files = list(self.temp_dir.glob("*"))
            deleted_count = 0
            
            for temp_file in temp_files:
                if temp_file.is_file():
                    file_age = time.time() - temp_file.stat().st_mtime
                    if file_age > 3600:
                        temp_file.unlink()
                        deleted_count += 1
            
            if deleted_count > 0:
                self._log_info(f"Cleaned up {deleted_count} temp files")
                
        except Exception as e:
            self._log_error(f"Cleanup failed: {str(e)}")
    
    def _update_system_stats(self):
        """Update system stats with real data from disk"""
        try:
            total_used = 0
            total_chunks = 0
            
            for repo_id, repo_info in self.repos_info.items():
                repo_path = self.repos_root / repo_id
                if repo_path.exists():
                    actual_size = self._calculate_folder_size(repo_path)
                    repo_info.total_size = actual_size
                    total_used += actual_size
                
                total_chunks += repo_info.chunk_count
            
            self.system_state.total_chunks = total_chunks
            self.system_state.storage_stats["used"] = total_used
            self.system_state.storage_stats["available"] = \
                (Config.TOTAL_REPOS * Config.REPO_MAX_SIZE) - total_used
            
            # Update batch stats from real repo sizes
            for batch_id, batch in self.batch_manager.batches.items():
                batch_total = 0
                for repo_id in batch.repo_ids:
                    if repo_id in self.repos_info:
                        batch_total += self.repos_info[repo_id].total_size
                batch.total_size = batch_total
                batch.utilization = batch_total / Config.REPO_MAX_SIZE
            
            self._save_metadata()
            
        except Exception as e:
            self._log_error(f"Update stats failed: {str(e)}")
    
    def _calculate_folder_size(self, folder_path: Path) -> int:
        total_size = 0
        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except:
                    pass
        return total_size
    
    def _log_info(self, message: str):
        log_file = self.logs_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_file, 'a') as f:
            f.write(f"[INFO] {timestamp} - {message}\n")
    
    def _log_error(self, message: str):
        log_file = self.logs_dir / f"error_{datetime.now().strftime('%Y%m%d')}.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_file, 'a') as f:
            f.write(f"[ERROR] {timestamp} - {message}\n")
    
    def get_optimal_repo_for_chunk(self, chunk_size: int, preferred_batch: int = None) -> Tuple[str, str, int]:
        if preferred_batch is not None and preferred_batch in self.batch_manager.batches:
            batch = self.batch_manager.batches[preferred_batch]
            for repo_id in batch.repo_ids:
                repo = self.repos_info[repo_id]
                if repo.total_size + chunk_size <= Config.REPO_MAX_SIZE:
                    return repo_id, self._get_folder_path(repo), preferred_batch
        
        for batch_id in self.batch_manager.active_batches:
            batch = self.batch_manager.batches[batch_id]
            for repo_id in batch.repo_ids:
                repo = self.repos_info[repo_id]
                if repo.total_size + chunk_size <= Config.REPO_MAX_SIZE:
                    return repo_id, self._get_folder_path(repo), batch_id
        
        for batch_id, batch in self.batch_manager.batches.items():
            if batch_id not in self.batch_manager.active_batches:
                for repo_id in batch.repo_ids:
                    repo = self.repos_info[repo_id]
                    if repo.total_size + chunk_size <= Config.REPO_MAX_SIZE:
                        return repo_id, self._get_folder_path(repo), batch_id
        
        available_repos = []
        for repo_id, repo in self.repos_info.items():
            available_space = Config.REPO_MAX_SIZE - repo.total_size
            if available_space >= chunk_size:
                available_repos.append((repo_id, repo.utilization, repo.batch_id))
        
        if available_repos:
            available_repos.sort(key=lambda x: x[1])
            repo_id, _, batch_id = available_repos[0]
            return repo_id, self._get_folder_path(self.repos_info[repo_id]), batch_id
        
        raise Exception(f"No repository with enough space for {chunk_size} bytes chunk")
    
    def _get_folder_path(self, repo: RepoInfo) -> str:
        structure = StealthUtility.generate_repo_structure(repo.repo_type)
        folder = random.choice(structure["folders"])
        hash_val = hashlib.md5(str(repo.total_size).encode()).hexdigest()
        subfolder = hash_val[:2]
        return f"{folder}/{subfolder}"
    
    def store_chunk(self, chunk_data: bytes, original_filename: str, 
                   batch_id: int = None) -> ChunkInfo:
        """Store chunk to physical disk"""
        try:
            encoding_type = random.choice(Config.ENCODING_TYPES)
            encoded_data = StealthUtility.encode_data(chunk_data, encoding_type)
            encoded_size = len(encoded_data.encode('utf-8'))  # Size in bytes
            
            repo_id, folder_path, actual_batch_id = self.get_optimal_repo_for_chunk(
                encoded_size, batch_id
            )
            
            repo = self.repos_info[repo_id]
            credible_name = StealthUtility.generate_credible_filename(
                original_filename, repo.repo_type
            )
            final_name = f"{credible_name}.b85"
            
            repo_path = self.repos_root / repo_id / folder_path
            repo_path.mkdir(exist_ok=True, parents=True)
            file_path = repo_path / final_name
            
            header = f"""# Dataset Sample File
# Repo: {repo_id}
# Batch: {actual_batch_id}
# Generated: {datetime.now().isoformat()}
# Encoding: {encoding_type}
# Original: {original_filename}
# Hash: {hashlib.sha256(chunk_data).hexdigest()[:16]}

"""
            
            # Write to physical file
            full_content = header + encoded_data
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
            
            # Verify file was written
            if not file_path.exists():
                raise Exception(f"Failed to create chunk file: {file_path}")
            
            # Get actual file size
            actual_file_size = file_path.stat().st_size
            
            # Update repo info
            repo.chunk_count += 1
            repo.total_size += actual_file_size
            repo.last_accessed = datetime.now().isoformat()
            repo.utilization = repo.total_size / Config.REPO_MAX_SIZE
            
            # Update batch stats
            self.batch_manager.update_batch_stats(actual_batch_id, actual_file_size)
            
            chunk_info = ChunkInfo(
                chunk_id=hashlib.sha256(chunk_data).hexdigest()[:16],
                repo_id=repo_id,
                file_path=str(file_path.relative_to(self.repos_root)),
                encoded_size=actual_file_size,
                index=0,  # Will be updated by caller
                encoding_type=encoding_type,
                hash=hashlib.sha256(chunk_data).hexdigest()[:16],
                created_at=datetime.now().isoformat(),
                batch_id=actual_batch_id
            )
            
            self._log_info(f"Chunk stored: {file_path} ({actual_file_size} bytes)")
            return chunk_info
            
        except Exception as e:
            self._log_error(f"Failed to store chunk: {str(e)}")
            raise
    
    def retrieve_chunk(self, chunk_info: ChunkInfo) -> bytes:
        """Retrieve chunk from physical disk"""
        file_path = self.repos_root / chunk_info.file_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"Chunk not found: {chunk_info.chunk_id} at {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract data from header
            lines = content.split('\n')
            data_start = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.startswith('#'):
                    data_start = i
                    break
            
            encoded_data = '\n'.join(lines[data_start:])
            decoded_data = StealthUtility.decode_data(encoded_data, chunk_info.encoding_type)
            
            # Update last accessed
            repo_id = chunk_info.repo_id
            self.repos_info[repo_id].last_accessed = datetime.now().isoformat()
            
            return decoded_data
            
        except Exception as e:
            self._log_error(f"Failed to retrieve chunk {chunk_info.chunk_id}: {str(e)}")
            raise
    
    def delete_chunk(self, chunk_info: ChunkInfo):
        """Delete chunk from physical disk"""
        file_path = self.repos_root / chunk_info.file_path
        
        if file_path.exists():
            try:
                # Get actual file size before deletion
                actual_size = file_path.stat().st_size
                
                # Delete file
                file_path.unlink()
                
                # Update repo info
                repo_id = chunk_info.repo_id
                repo = self.repos_info[repo_id]
                repo.chunk_count -= 1
                repo.total_size -= actual_size
                repo.utilization = repo.total_size / Config.REPO_MAX_SIZE
                
                # Update batch stats
                batch_id = chunk_info.batch_id
                self.batch_manager.update_batch_stats(batch_id, -actual_size)
                
                # Try to remove empty directories
                try:
                    if file_path.parent.is_dir() and not any(file_path.parent.iterdir()):
                        file_path.parent.rmdir()
                except OSError:
                    pass
                
                self._log_info(f"Chunk deleted: {file_path}")
                
            except Exception as e:
                self._log_error(f"Failed to delete chunk {chunk_info.chunk_id}: {str(e)}")
                raise
        else:
            # File doesn't exist, but still update metadata
            repo_id = chunk_info.repo_id
            repo = self.repos_info[repo_id]
            repo.chunk_count -= 1
            repo.total_size -= chunk_info.encoded_size
            repo.utilization = repo.total_size / Config.REPO_MAX_SIZE
            
            batch_id = chunk_info.batch_id
            self.batch_manager.update_batch_stats(batch_id, -chunk_info.encoded_size)
    
    def get_system_stats(self) -> Dict:
        """Get system statistics with real data"""
        # Recalculate from disk to ensure accuracy
        self._update_system_stats()
        
        total_files = self.system_state.total_files
        total_size = self.system_state.total_size
        total_storage = self.system_state.storage_stats["used"]
        
        batch_stats = {}
        for batch_id, batch in self.batch_manager.batches.items():
            batch_stats[batch_id] = {
                "repos": len(batch.repo_ids),
                "total_size": batch.total_size,
                "utilization": batch.utilization,
                "avg_health": batch.avg_health,
                "is_active": batch.is_active
            }
        
        repo_type_stats = defaultdict(lambda: {"count": 0, "size": 0, "chunks": 0})
        for repo in self.repos_info.values():
            repo_type_stats[repo.repo_type]["count"] += 1
            repo_type_stats[repo.repo_type]["size"] += repo.total_size
            repo_type_stats[repo.repo_type]["chunks"] += repo.chunk_count
        
        return {
            "files": {
                "total": total_files,
                "total_size": total_size,
                "avg_file_size": total_size / max(total_files, 1)
            },
            "storage": {
                "used": total_storage,
                "capacity": Config.TOTAL_REPOS * Config.REPO_MAX_SIZE,
                "available": self.system_state.storage_stats["available"],
                "utilization_percent": self.system_state.storage_stats["used"] / (Config.TOTAL_REPOS * Config.REPO_MAX_SIZE) * 100
            },
            "chunks": {
                "total": self.system_state.total_chunks,
                "avg_size": total_storage / max(self.system_state.total_chunks, 1) if self.system_state.total_chunks > 0 else 0
            },
            "repos": {
                "total": len(self.repos_info),
                "active": len([r for r in self.repos_info.values() if r.is_active]),
                "types": dict(repo_type_stats)
            },
            "batches": {
                "total": len(self.batch_manager.batches),
                "active": len(self.batch_manager.active_batches),
                "stats": batch_stats
            },
            "system": {
                "stealth_mode": self.system_state.stealth_mode,
                "last_health_check": self.system_state.last_health_check,
                "batch_rotation": self.system_state.batch_rotation_schedule
            }
        }

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

repo_manager = RepoManager()

@app.before_request
def before_request():
    if request.path.startswith('/api/'):
        time.sleep(random.uniform(0.1, 0.8))
        
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    return send_file('static/index.html')

@app.route('/viewer.html')
def viewer():
    return send_file('static/viewer.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('static/js', filename)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "system": "github-drive-simulator-v2.5",
        "version": "2.5.0",
        "active_batches": repo_manager.system_state.active_batch_ids
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
        
        file_id = hashlib.sha256(
            f"{filename}{datetime.now().isoformat()}{random.randint(1, 1000000)}".encode()
        ).hexdigest()[:20]
        
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"
        
        tags = []
        if mime_type.startswith('image/'):
            tags = ["image", "media", "visual"]
        elif mime_type.startswith('video/'):
            tags = ["video", "media", "motion"]
        elif mime_type.startswith('audio/'):
            tags = ["audio", "media", "sound"]
        elif mime_type == 'application/pdf':
            tags = ["document", "pdf", "text"]
        elif mime_type.startswith('text/'):
            tags = ["text", "document", "code"]
        else:
            tags = ["binary", "data", "archive"]
        
        num_chunks = (file_size + Config.RAW_CHUNK_SIZE - 1) // Config.RAW_CHUNK_SIZE
        active_batches = repo_manager.system_state.active_batch_ids
        selected_batch = random.choice(active_batches) if active_batches else 0
        
        chunks = []
        batch_distribution = defaultdict(int)
        
        for i in range(num_chunks):
            start = i * Config.RAW_CHUNK_SIZE
            end = min(start + Config.RAW_CHUNK_SIZE, file_size)
            chunk_data = file_data[start:end]
            
            try:
                chunk_info = repo_manager.store_chunk(chunk_data, filename, selected_batch)
                chunk_info.index = i
                chunks.append(chunk_info)
                batch_distribution[chunk_info.batch_id] += 1
                
            except Exception as e:
                # Rollback: delete already stored chunks
                for chunk in chunks:
                    try:
                        repo_manager.delete_chunk(chunk)
                    except:
                        pass
                return jsonify({
                    "error": f"Failed to store chunk {i+1}/{num_chunks}: {str(e)}"
                }), 500
        
        file_metadata = FileMetadata(
            file_id=file_id,
            original_name=filename,
            display_name=filename,
            original_size=file_size,
            mime_type=mime_type,
            upload_time=datetime.now().isoformat(),
            chunks=chunks,
            chunk_count=len(chunks),
            tags=tags,
            description=f"Uploaded {filename} ({file_size} bytes)",
            batch_distribution=dict(batch_distribution)
        )
        
        repo_manager.files_metadata[file_id] = file_metadata
        
        repo_manager.system_state.total_files += 1
        repo_manager.system_state.total_size += file_size
        repo_manager.system_state.total_chunks += len(chunks)
        
        repo_manager._save_metadata()
        repo_manager._update_system_stats()
        
        return jsonify({
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "size": file_size,
            "chunks": len(chunks),
            "batches_used": list(batch_distribution.keys()),
            "batch_distribution": dict(batch_distribution),
            "upload_time": file_metadata.upload_time
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/files', methods=['GET'])
def list_files():
    try:
        files_list = []
        
        for file_id, file_meta in repo_manager.files_metadata.items():
            if file_meta.is_hidden:
                continue
                
            files_list.append({
                "id": file_id,
                "filename": file_meta.original_name,
                "display_name": file_meta.display_name,
                "size": file_meta.original_size,
                "mime_type": file_meta.mime_type,
                "upload_time": file_meta.upload_time,
                "chunk_count": file_meta.chunk_count,
                "tags": file_meta.tags,
                "batch_distribution": file_meta.batch_distribution
            })
        
        sort_by = request.args.get('sort', 'upload_time')
        reverse = request.args.get('order', 'desc') == 'desc'
        
        if sort_by in ['filename', 'display_name']:
            files_list.sort(key=lambda x: x[sort_by].lower(), reverse=reverse)
        elif sort_by in ['size', 'chunk_count', 'upload_time']:
            files_list.sort(key=lambda x: x[sort_by], reverse=reverse)
        
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        return jsonify({
            "files": files_list[start_idx:end_idx],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": len(files_list),
                "total_pages": (len(files_list) + per_page - 1) // per_page
            }
        })
    
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
            mimetype=file_meta.mime_type,
            conditional=True
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>/info', methods=['GET'])
def get_file_info(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        
        repo_distribution = defaultdict(int)
        for chunk in file_meta.chunks:
            repo_distribution[chunk.repo_id] += 1
        
        batch_distribution = defaultdict(int)
        for chunk in file_meta.chunks:
            batch_distribution[chunk.batch_id] += 1
        
        return jsonify({
            "id": file_id,
            "filename": file_meta.original_name,
            "display_name": file_meta.display_name,
            "size": file_meta.original_size,
            "mime_type": file_meta.mime_type,
            "upload_time": file_meta.upload_time,
            "chunk_count": file_meta.chunk_count,
            "tags": file_meta.tags,
            "description": file_meta.description,
            "repo_distribution": dict(repo_distribution),
            "batch_distribution": dict(batch_distribution),
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "repo": c.repo_id,
                    "batch": c.batch_id,
                    "path": c.file_path,
                    "encoding": c.encoding_type,
                    "size": c.encoded_size,
                    "index": c.index
                }
                for c in file_meta.chunks
            ]
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>/preview', methods=['GET'])
def preview_file(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        mime_type = file_meta.mime_type
        
        # Check if file is small enough for preview (< 10MB)
        if file_meta.original_size > 10 * 1024 * 1024:
            return jsonify({
                "error": "File too large for preview",
                "size": file_meta.original_size,
                "limit": 10 * 1024 * 1024
            }), 400
        
        # Check supported preview types
        supported_types = [
            'image/', 'text/', 'application/pdf',
            'application/json', 'application/xml'
        ]
        
        if not any(mime_type.startswith(t) for t in supported_types):
            return jsonify({
                "error": "Preview not supported for this file type",
                "mime_type": mime_type
            }), 400
        
        # Download and assemble file
        chunks = sorted(file_meta.chunks, key=lambda x: x.index)
        assembled_data = bytearray()
        
        for chunk_info in chunks:
            chunk_data = repo_manager.retrieve_chunk(chunk_info)
            assembled_data.extend(chunk_data)
        
        # Encode to base64 for preview
        b64_data = base64.b64encode(bytes(assembled_data)).decode('ascii')
        
        # If text file, also provide decoded text
        text_content = None
        if mime_type.startswith('text/'):
            try:
                text_content = assembled_data.decode('utf-8', errors='ignore')
            except:
                pass
        
        return jsonify({
            "filename": file_meta.original_name,
            "mime_type": mime_type,
            "size": len(assembled_data),
            "data": b64_data,
            "text": text_content,
            "encoding": "base64"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    try:
        if file_id not in repo_manager.files_metadata:
            return jsonify({"error": "File not found"}), 404
        
        file_meta = repo_manager.files_metadata[file_id]
        
        # Soft delete first
        file_meta.is_hidden = True
        repo_manager._save_metadata()
        
        # Schedule hard delete in background
        def perform_hard_delete():
            time.sleep(300)  # 5 minutes delay
            
            # Delete all chunks
            for chunk_info in file_meta.chunks:
                try:
                    repo_manager.delete_chunk(chunk_info)
                except Exception as e:
                    repo_manager._log_error(f"Failed to delete chunk {chunk_info.chunk_id}: {str(e)}")
            
            # Update system state
            repo_manager.system_state.total_files -= 1
            repo_manager.system_state.total_size -= file_meta.original_size
            repo_manager.system_state.total_chunks -= file_meta.chunk_count
            
            # Remove from metadata
            del repo_manager.files_metadata[file_id]
            repo_manager._save_metadata()
            repo_manager._update_system_stats()
            
            repo_manager._log_info(f"Hard deleted file: {file_id}")
        
        thread = threading.Thread(target=perform_hard_delete, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "message": f"File '{file_meta.display_name}' scheduled for deletion",
            "file_id": file_id,
            "hard_delete_in": "5 minutes"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_system_stats():
    try:
        stats = repo_manager.get_system_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/batches', methods=['GET'])
def list_batches():
    try:
        batches_list = []
        
        for batch_id, batch in repo_manager.batch_manager.batches.items():
            batches_list.append({
                "id": batch_id,
                "repo_ids": batch.repo_ids,
                "repos_count": len(batch.repo_ids),
                "total_size": batch.total_size,
                "utilization": batch.utilization,
                "avg_health": batch.avg_health,
                "is_active": batch.is_active,
                "created_at": batch.created_at
            })
        
        return jsonify({
            "batches": batches_list,
            "active_batches": repo_manager.batch_manager.active_batches,
            "batch_size": Config.BATCH_SIZE
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/repos', methods=['GET'])
def list_repos():
    try:
        repos_list = []
        
        for repo_id, repo_info in repo_manager.repos_info.items():
            repos_list.append({
                "id": repo_id,
                "type": repo_info.repo_type,
                "display_name": repo_info.display_name,
                "chunks": repo_info.chunk_count,
                "size": repo_info.total_size,
                "utilization": repo_info.utilization,
                "health": repo_info.health_score,
                "batch": repo_info.batch_id,
                "is_active": repo_info.is_active,
                "created": repo_info.created_at,
                "last_accessed": repo_info.last_accessed
            })
        
        batch_filter = request.args.get('batch')
        if batch_filter:
            try:
                batch_id = int(batch_filter)
                repos_list = [r for r in repos_list if r['batch'] == batch_id]
            except:
                pass
        
        active_only = request.args.get('active', '').lower() == 'true'
        if active_only:
            repos_list = [r for r in repos_list if r['is_active']]
        
        sort_by = request.args.get('sort', 'id')
        reverse = request.args.get('order', 'asc') == 'desc'
        
        if sort_by in ['size', 'chunks', 'utilization', 'health']:
            repos_list.sort(key=lambda x: x[sort_by], reverse=reverse)
        else:
            repos_list.sort(key=lambda x: x['id'], reverse=reverse)
        
        return jsonify({
            "repos": repos_list,
            "total": len(repos_list),
            "active": len([r for r in repos_list if r['is_active']])
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/rotate', methods=['POST'])
def rotate_batches():
    try:
        rotation_info = repo_manager.batch_manager.rotate_batches()
        
        for repo_id, repo_info in repo_manager.repos_info.items():
            batch_id = repo_info.batch_id
            repo_info.is_active = (batch_id in repo_manager.batch_manager.active_batches)
        
        repo_manager.system_state.active_batch_ids = repo_manager.batch_manager.active_batches
        repo_manager.system_state.batch_rotation_schedule = rotation_info
        
        repo_manager._save_metadata()
        
        return jsonify({
            "success": True,
            "rotation": rotation_info,
            "active_batches": repo_manager.batch_manager.active_batches
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/maintenance', methods=['POST'])
def system_maintenance():
    try:
        data = request.get_json() or {}
        action = data.get('action', '')
        
        if action == 'recalculate_health':
            repo_manager._perform_health_check()
            return jsonify({"success": True, "action": "recalculate_health"})
        
        elif action == 'update_stats':
            repo_manager._update_system_stats()
            return jsonify({"success": True, "action": "update_stats"})
        
        elif action == 'cleanup':
            repo_manager._cleanup_temp_files()
            return jsonify({"success": True, "action": "cleanup"})
        
        elif action == 'verify_storage':
            # Verify storage integrity
            total_chunks = sum(repo.chunk_count for repo in repo_manager.repos_info.values())
            total_storage = repo_manager._calculate_total_storage()
            
            # Count actual .b85 files
            b85_files = list(repo_manager.repos_root.rglob("*.b85"))
            
            return jsonify({
                "success": True,
                "action": "verify_storage",
                "metadata_chunks": total_chunks,
                "actual_files": len(b85_files),
                "total_storage": total_storage,
                "mismatch": total_chunks != len(b85_files)
            })
        
        else:
            return jsonify({
                "error": "Unknown action",
                "available_actions": ["recalculate_health", "update_stats", "cleanup", "verify_storage"]
            }), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/search', methods=['GET'])
def search_files():
    try:
        query = request.args.get('q', '').lower()
        tag_filter = request.args.get('tag', '')
        batch_filter = request.args.get('batch', '')
        
        results = []
        
        for file_id, file_meta in repo_manager.files_metadata.items():
            if file_meta.is_hidden:
                continue
            
            match = True
            
            if query:
                in_name = query in file_meta.original_name.lower() or \
                         query in file_meta.display_name.lower()
                in_desc = query in (file_meta.description or "").lower()
                in_tags = any(query in tag.lower() for tag in file_meta.tags)
                
                if not (in_name or in_desc or in_tags):
                    match = False
            
            if tag_filter and tag_filter not in file_meta.tags:
                match = False
            
            if batch_filter:
                try:
                    batch_id = int(batch_filter)
                    if file_meta.batch_distribution and batch_id not in file_meta.batch_distribution:
                        match = False
                except:
                    pass
            
            if match:
                results.append({
                    "id": file_id,
                    "filename": file_meta.original_name,
                    "display_name": file_meta.display_name,
                    "size": file_meta.original_size,
                    "mime_type": file_meta.mime_type,
                    "upload_time": file_meta.upload_time,
                    "tags": file_meta.tags,
                    "batch_distribution": file_meta.batch_distribution
                })
        
        results.sort(key=lambda x: x["upload_time"], reverse=True)
        
        return jsonify({
            "query": query,
            "results": results,
            "count": len(results)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    print("=" * 80)
    print("GITHUB DRIVE SIMULATOR v2.5 - REAL STORAGE SYSTEM")
    print("=" * 80)
    print(f"Base Directory: {Config.BASE_DIR}")
    print(f"Repositories: {Config.REPOS_ROOT}")
    print(f"Total Repos: {Config.TOTAL_REPOS}")
    print(f"Batch Size: {Config.BATCH_SIZE} repos per batch")
    print(f"Repo Max Size: {Config.REPO_MAX_SIZE / (1024**3):.1f} GB")
    print(f"Total Capacity: {Config.TOTAL_REPOS * Config.REPO_MAX_SIZE / (1024**3):.1f} GB")
    print(f"Active Batches: {repo_manager.system_state.active_batch_ids}")
    
    # Verify storage
    total_b85_files = list(Config.REPOS_ROOT.rglob("*.b85"))
    print(f"Found {len(total_b85_files)} existing chunk files")
    
    print("\n" + "=" * 80)
    print("API Endpoints:")
    print("  GET  /api/health             - Health check")
    print("  POST /api/upload             - Upload file")
    print("  GET  /api/files              - List files")
    print("  GET  /api/file/<id>          - Download file")
    print("  GET  /api/file/<id>/info     - File info")
    print("  GET  /api/file/<id>/preview  - Preview file")
    print("  DELETE /api/file/<id>        - Delete file")
    print("  GET  /api/stats              - System statistics")
    print("  GET  /api/batches            - List batches")
    print("  POST /api/system/rotate      - Rotate batches")
    print("  POST /api/system/maintenance - Maintenance operations")
    print("  GET  /api/search             - Search files")
    print("=" * 80)
    
    # Run server
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)