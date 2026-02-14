#!/usr/bin/env python3
"""
STEALTH STORAGE SYSTEM - ULTIMATE EDITION (FULL STEALTH)
Fitur:
- AES-256-GCM enkripsi per file
- Multi-encoding acak (base32/64/85/91)
- Fragmentasi data dalam kode (string tersebar)
- Template kode sangat realistis (seperti proyek nyata)
- Steganografi whitespace pada komentar
- Git history palsu + aktivitas commit
- Distribusi chunk cerdas + file realistis (tanpa kata "dummy")
- Timestamp randomisasi
- Verifikasi integritas otomatis
- API lengkap dengan fitur preview dan manajemen
- Metadata sangat ringkas (hanya kode pendek) dan tidak mencolok
"""

import os
import json
import base64
import hashlib
import mimetypes
import random
import string
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import zlib
import secrets

# Third-party
try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    HAVE_AES = True
except ImportError:
    HAVE_AES = False
    print("WARNING: pycryptodome not installed. AES disabled.")

try:
    import base91
    HAVE_BASE91 = True
except ImportError:
    HAVE_BASE91 = False
    print("WARNING: base91 not installed. Base91 encoding disabled.")

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename


# ======================== CONFIGURATION ========================
class Config:
    RAW_CHUNK_SIZE = 3 * 1024 * 1024          # 3 MB per chunk
    TOTAL_REPOS = 150                          # jumlah repositori palsu
    REPO_MAX_SIZE = 1 * 1024 * 1024 * 1024     # 1 GB per repo
    BASE_DIR = Path(__file__).parent
    REPOS_ROOT = BASE_DIR / "github_repositories"
    METADATA_ROOT = BASE_DIR / "system_data"
    TEMP_DIR = BASE_DIR / "temp_cache"
    
    REPO_TYPES = [
        "web-development", "machine-learning", "data-science",
        "mobile-apps", "devops-tools", "game-development",
        "blockchain", "iot-projects"
    ]
    
    AES_KEY_SIZE = 32   # 256 bits
    AES_IV_SIZE = 12    # 96 bits (GCM)
    AES_TAG_SIZE = 16
    
    # Stealth settings
    ENABLE_WHITESPACE_STEGO = True
    ENABLE_GIT_HISTORY = True
    ENABLE_TIMESTAMP_RANDOMIZE = True
    ENABLE_REALISTIC_FILES = True               # selalu aktif
    MIN_FILES_PER_REPO = 10
    MAX_FILES_PER_REPO = 30
    
    ENCODINGS = ['base32', 'base64', 'base85']
    if HAVE_BASE91:
        ENCODINGS.append('base91')


# ======================== DATA CLASSES ========================
@dataclass
class ChunkInfo:
    chunk_id: str
    repo_index: int                     # 0..149
    file_path: str                       # path relatif terhadap repo root
    index: int
    hash: str
    created_at: str
    encryption_algo: str = "aes-256-gcm" if HAVE_AES else "xor"
    encryption_iv: str = ""              # base64
    encryption_tag: str = ""             # base64
    xor_key: str = ""                    # legacy
    encoding_used: str = "base85"


@dataclass
class FileMetadata:
    file_id: str
    original_name: str
    original_size: int
    mime_type: str
    upload_time: str
    chunks: List[ChunkInfo]
    tags: List[str]
    file_key: str = ""                   # base64 encoded AES key


# ======================== KOMPAKTOR METADATA (MANUAL, TANPA asdict) ========================
def compact_chunk(c: ChunkInfo) -> dict:
    """Ubah dataclass ChunkInfo menjadi dict dengan kode pendek."""
    # Pastikan c adalah objek, bukan dict
    if not isinstance(c, ChunkInfo):
        # Jika sudah dict (misal dari metadata corrupt), kembalikan apa adanya
        return c
    return {
        'id': c.chunk_id,
        'ri': c.repo_index,
        'p': c.file_path,
        'i': c.index,
        'h': c.hash,
        'c': c.created_at,
        'ea': c.encryption_algo,
        'ei': c.encryption_iv,
        'et': c.encryption_tag,
        'xk': c.xor_key,
        'eu': c.encoding_used
    }

def expand_chunk(d: dict) -> ChunkInfo:
    """Kembalikan dict dengan kode pendek ke dataclass ChunkInfo."""
    required = ['id', 'ri', 'p', 'i', 'h', 'c', 'ea', 'eu']
    for f in required:
        if f not in d:
            raise ValueError(f"Missing field {f} in chunk data")
    return ChunkInfo(
        chunk_id=d['id'],
        repo_index=d['ri'],
        file_path=d['p'],
        index=d['i'],
        hash=d['h'],
        created_at=d['c'],
        encryption_algo=d['ea'],
        encryption_iv=d.get('ei', ''),
        encryption_tag=d.get('et', ''),
        xor_key=d.get('xk', ''),
        encoding_used=d['eu']
    )

def compact_file(f: FileMetadata) -> dict:
    """Ubah dataclass FileMetadata menjadi dict dengan kode pendek."""
    if not isinstance(f, FileMetadata):
        return f
    return {
        'id': f.file_id,
        'n': f.original_name,
        'sz': f.original_size,
        'm': f.mime_type,
        'ut': f.upload_time,
        'cs': [compact_chunk(c) for c in f.chunks],
        't': f.tags,
        'k': f.file_key
    }

def expand_file(d: dict) -> FileMetadata:
    """Kembalikan dict dengan kode pendek ke dataclass FileMetadata."""
    required = ['id', 'n', 'sz', 'm', 'ut', 'cs', 't']
    for f in required:
        if f not in d:
            raise ValueError(f"Missing field {f} in file data")
    return FileMetadata(
        file_id=d['id'],
        original_name=d['n'],
        original_size=d['sz'],
        mime_type=d['m'],
        upload_time=d['ut'],
        chunks=[expand_chunk(c) for c in d['cs']],
        tags=d['t'],
        file_key=d.get('k', '')
    )


# ======================== ENCODING & STEGO UTILITIES ========================
class EncodingManager:
    @staticmethod
    def encode(data: bytes, encoding: str = None) -> Tuple[str, str]:
        if encoding is None:
            encoding = random.choice(Config.ENCODINGS)
        if encoding == 'base32':
            return base64.b32encode(data).decode('ascii').rstrip('='), encoding
        elif encoding == 'base64':
            return base64.b64encode(data).decode('ascii'), encoding
        elif encoding == 'base85':
            return base64.b85encode(data).decode('ascii'), encoding
        elif encoding == 'base91' and HAVE_BASE91:
            return base91.encode(data), encoding
        else:
            return base64.b85encode(data).decode('ascii'), 'base85'
    
    @staticmethod
    def decode(encoded: str, encoding: str) -> bytes:
        if encoding == 'base32':
            missing = len(encoded) % 8
            if missing:
                encoded += '=' * (8 - missing)
            return base64.b32decode(encoded)
        elif encoding == 'base64':
            return base64.b64decode(encoded)
        elif encoding == 'base85':
            return base64.b85decode(encoded)
        elif encoding == 'base91' and HAVE_BASE91:
            return base91.decode(encoded)
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")


class StegoText:
    """Menyisipkan bit dalam whitespace pada komentar."""
    
    @staticmethod
    def hide(cover_text: str, secret_bits: str) -> str:
        """Sisipkan bit setelah setiap baris komentar."""
        lines = cover_text.split('\n')
        result = []
        bit_idx = 0
        for line in lines:
            result.append(line)
            if bit_idx < len(secret_bits) and line.strip().startswith(('#', '//', '/*', '*')):
                # Tambahkan spasi/tab di akhir baris komentar
                if secret_bits[bit_idx] == '1':
                    result[-1] += ' '
                else:
                    result[-1] += '\t'
                bit_idx += 1
        return '\n'.join(result)
    
    @staticmethod
    def extract(stego_text: str) -> str:
        bits = []
        for line in stego_text.split('\n'):
            if line.endswith(' '):
                bits.append('1')
                line = line.rstrip(' ')
            elif line.endswith('\t'):
                bits.append('0')
                line = line.rstrip('\t')
        return ''.join(bits)
    
    @staticmethod
    def text_to_bits(text: str) -> str:
        return ''.join(format(ord(c), '08b') for c in text)
    
    @staticmethod
    def bits_to_text(bits: str) -> str:
        chars = []
        for i in range(0, len(bits), 8):
            byte = bits[i:i+8]
            if len(byte) == 8:
                chars.append(chr(int(byte, 2)))
        return ''.join(chars)


# ======================== TEMPLATE KODE REALISTIS ========================
class CodeTemplateGenerator:
    """
    Menghasilkan kode yang terlihat seperti proyek sungguhan.
    String data disamarkan sebagai konstanta base64, konfigurasi, atau hash.
    """
    
    @staticmethod
    def generate(repo_type: str, encoded_data: str, metadata: dict) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Pilih template berdasarkan tipe repo
        templates = CodeTemplateGenerator._get_templates_for_type(repo_type)
        template = random.choice(templates)
        
        # Opsional sisipkan whitespace stego (nanti dilakukan setelah generate)
        return template.format(
            timestamp=timestamp,
            encoded_data=encoded_data,
            random_hex=secrets.token_hex(8),
            random_int=random.randint(1000, 9999),
            random_float=random.uniform(1.0, 100.0),
            random_string=secrets.token_urlsafe(12)
        )
    
    @staticmethod
    def _get_templates_for_type(repo_type):
        # Template sangat bervariasi, tanpa kata mencolok.
        # String encoded ditempatkan sebagai konstanta, nilai default, atau dalam komentar.
        templates = {
            "web-development": [
                # Python config module
                '''# config/settings.py
# Auto-generated {timestamp}
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# API configuration
API_SECRET = "{encoded_data}"
DEBUG = {random_int} % 2 == 0

def get_api_key():
    return API_SECRET
''',
                # JavaScript utility
                '''// utils/helpers.js
// Generated: {timestamp}

const CONFIG = {{
    version: "{random_hex}",
    apiKey: "{encoded_data}",
    retries: {random_int}
}};

module.exports = { CONFIG };
''',
                # HTML with data attribute
                '''<!DOCTYPE html>
<html>
<head>
    <title>App</title>
    <meta name="config" content="{encoded_data}">
</head>
<body>
    <div id="app" data-config="{encoded_data}"></div>
</body>
</html>
''',
                # JSON configuration
                '''{
    "timestamp": "{timestamp}",
    "version": "{random_hex}",
    "parameters": {
        "api_key": "{encoded_data}",
        "timeout": {random_int}
    }
}''',
                # YAML
                '''# docker-compose.yml
version: '3'
services:
  app:
    image: app:{random_hex}
    environment:
      - SECRET_KEY={encoded_data}
''',
            ],
            "machine-learning": [
                # Python model config
                '''# models/config.py
# {timestamp}

MODEL_CONFIG = {{
    "weights": "{encoded_data}",
    "batch_size": {random_int},
    "learning_rate": {random_float:.4f}
}}

def load_weights():
    return MODEL_CONFIG["weights"]
''',
                # JSON model metadata
                '''{{
    "model_id": "{random_hex}",
    "checkpoint": "{encoded_data}",
    "metrics": {{
        "accuracy": {random_float:.4f}
    }}
}}''',
                # Python script with embedded base64
                '''# data_loader.py
import base64

# Pre-trained weights (base64)
_WEIGHTS = "{encoded_data}"

def get_weights():
    return base64.b64decode(_WEIGHTS)
''',
            ],
            "data-science": [
                # Jupyter notebook style (JSON)
                '''{{
 "cells": [
  {{
   "cell_type": "code",
   "execution_count": null,
   "metadata": {{}},
   "outputs": [],
   "source": [
    "# {timestamp}\\n",
    "DATA = \\"{encoded_data}\\""
   ]
  }}
 ]
}}''',
                # Python analysis script
                '''# analysis/process.py
import pandas as pd

# Encoded dataset fragment
_DATA = "{encoded_data}"

def load_fragment():
    return _DATA
''',
            ],
            "mobile-apps": [
                # Android resource string
                '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="api_key">{encoded_data}</string>
    <integer name="version">{random_int}</integer>
</resources>''',
                # iOS plist
                '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>APIKey</key>
    <string>{encoded_data}</string>
    <key>Build</key>
    <integer>{random_int}</integer>
</dict>
</plist>''',
            ],
            "devops-tools": [
                # Terraform variable
                '''variable "secret" {{
  description = "Secret key"
  default     = "{encoded_data}"
}}

output "key" {{
  value = var.secret
}}
''',
                # Kubernetes secret (YAML)
                '''apiVersion: v1
kind: Secret
metadata:
  name: app-secret
type: Opaque
data:
  .secret: {encoded_data}
''',
            ],
            "game-development": [
                # Unity C# script
                '''using UnityEngine;

public class GameConfig : MonoBehaviour
{{
    public static string secret = "{encoded_data}";
    void Start()
    {{
        Debug.Log("Game initialized");
    }}
}}
''',
                # JSON asset
                '''{{
    "asset_id": "{random_hex}",
    "data": "{encoded_data}"
}}''',
            ],
            "blockchain": [
                # Solidity contract snippet
                '''pragma solidity ^0.8.0;

contract Config {{
    string private constant DATA = "{encoded_data}";
    function getData() public view returns (string memory) {{
        return DATA;
    }}
}}
''',
                # Truffle config
                '''module.exports = {{
  networks: {{
    development: {{
      host: "127.0.0.1",
      port: 8545,
      network_id: "*",
      from: "{encoded_data}"
    }}
  }}
}};
''',
            ],
            "iot-projects": [
                # Arduino sketch
                '''// config.h
#ifndef CONFIG_H
#define CONFIG_H

#define SECRET_KEY "{encoded_data}"
#define VERSION {random_int}

#endif
''',
                # Python firmware
                '''# firmware/config.py
DEVICE_ID = "{random_hex}"
SECRET = "{encoded_data}"
''',
            ]
        }
        # Fallback ke web-development jika tipe tidak ditemukan
        return templates.get(repo_type, templates["web-development"])


# ======================== FILE REALISTIS GENERATOR ========================
class RealisticFileGenerator:
    """Menambahkan file-file yang terlihat seperti bagian dari proyek nyata."""
    
    @staticmethod
    def generate(repo_path: Path, repo_type: str):
        if not Config.ENABLE_REALISTIC_FILES:
            return
        
        num_files = random.randint(Config.MIN_FILES_PER_REPO, Config.MAX_FILES_PER_REPO)
        for _ in range(num_files):
            # Pilih folder yang ada
            folders = [d for d in repo_path.iterdir() if d.is_dir()]
            if not folders:
                folders = [repo_path]  # fallback ke root
            folder = random.choice(folders)
            
            # Tentukan jenis file sesuai tipe repo
            ext, content_func = RealisticFileGenerator._pick_file_type(repo_type)
            fname = f"{RealisticFileGenerator._random_name()}{ext}"
            file_path = folder / fname
            
            # Jangan timpa file yang sudah ada (mungkin dari chunk)
            if file_path.exists():
                continue
            
            content = content_func(repo_type)
            file_path.write_text(content, encoding='utf-8')
            TimestampRandomizer.randomize(file_path)
    
    @staticmethod
    def _random_name():
        prefixes = ['test', 'utils', 'helpers', 'main', 'index', 'app', 'config', 'settings', 
                    'database', 'models', 'views', 'controllers', 'routes', 'middleware']
        return f"{random.choice(prefixes)}_{secrets.token_hex(2)}"
    
    @staticmethod
    def _pick_file_type(repo_type):
        # Mapping ekstensi ke fungsi pembuat konten
        options = []
        if repo_type in ["web-development", "mobile-apps"]:
            options = [('.py', RealisticFileGenerator._py_util), 
                       ('.js', RealisticFileGenerator._js_util),
                       ('.json', RealisticFileGenerator._json_config),
                       ('.html', RealisticFileGenerator._html_page),
                       ('.css', RealisticFileGenerator._css_styles)]
        elif repo_type in ["machine-learning", "data-science"]:
            options = [('.py', RealisticFileGenerator._ml_script),
                       ('.ipynb', RealisticFileGenerator._notebook),
                       ('.json', RealisticFileGenerator._json_config),
                       ('.csv', RealisticFileGenerator._csv_data)]
        elif repo_type == "devops-tools":
            options = [('.yaml', RealisticFileGenerator._yaml_config),
                       ('.tf', RealisticFileGenerator._terraform),
                       ('.sh', RealisticFileGenerator._shell_script)]
        elif repo_type == "game-development":
            options = [('.cs', RealisticFileGenerator._csharp),
                       ('.json', RealisticFileGenerator._json_config)]
        elif repo_type == "blockchain":
            options = [('.sol', RealisticFileGenerator._solidity),
                       ('.js', RealisticFileGenerator._truffle)]
        elif repo_type == "iot-projects":
            options = [('.ino', RealisticFileGenerator._arduino),
                       ('.py', RealisticFileGenerator._py_util)]
        else:
            options = [('.txt', RealisticFileGenerator._text_file)]
        
        return random.choice(options)
    
    @staticmethod
    def _py_util(repo_type):
        return f'''# {secrets.token_hex(4)}.py
"""
Utility module auto-generated.
"""

import os
import sys

VERSION = "{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,9)}"

def helper_function(param=None):
    """A helper function."""
    return param or {random.randint(1,100)}

if __name__ == "__main__":
    print(helper_function())
'''
    
    @staticmethod
    def _js_util(repo_type):
        return f'''// {secrets.token_hex(4)}.js
/**
 * Utility functions
 * @module utils
 */

export const version = "{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,9)}";

export function calculate(x) {{
    return x * {random.randint(1,10)};
}}
'''
    
    @staticmethod
    def _json_config(repo_type):
        return json.dumps({
            "name": f"config_{secrets.token_hex(4)}",
            "version": f"{random.randint(1,5)}.{random.randint(0,9)}",
            "settings": {
                "debug": random.choice([True, False]),
                "port": random.randint(3000, 9000)
            }
        }, indent=2)
    
    @staticmethod
    def _html_page(repo_type):
        return f'''<!DOCTYPE html>
<html>
<head>
    <title>Page {secrets.token_hex(2)}</title>
</head>
<body>
    <h1>Welcome</h1>
    <p>Generated at {datetime.now().isoformat()}</p>
</body>
</html>
'''
    
    @staticmethod
    def _css_styles(repo_type):
        return f'''/* styles_{secrets.token_hex(2)}.css */
body {{
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 0;
}}
h1 {{
    color: #{secrets.token_hex(3)};
}}
'''
    
    @staticmethod
    def _ml_script(repo_type):
        return f'''# ml_{secrets.token_hex(4)}.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Model configuration
MODEL_PARAMS = {{
    "n_estimators": {random.randint(50,200)},
    "max_depth": {random.randint(5,20)},
    "random_state": {random.randint(1,1000)}
}}

def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
'''
    
    @staticmethod
    def _notebook(repo_type):
        # Jupyter notebook JSON
        return json.dumps({
            "cells": [{
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["# Analysis notebook\n", "print('Hello')"]
            }],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 4
        }, indent=1)
    
    @staticmethod
    def _csv_data(repo_type):
        # Buat CSV kecil
        lines = ["id,value,timestamp"]
        for i in range(random.randint(5, 20)):
            lines.append(f"{i},{random.randint(1,100)},{int(time.time())}")
        return "\n".join(lines)
    
    @staticmethod
    def _yaml_config(repo_type):
        return f'''# config_{secrets.token_hex(2)}.yaml
version: "{random.randint(1,5)}.{random.randint(0,9)}"
services:
  - name: service_{random.randint(1,10)}
    port: {random.randint(3000,9000)}
'''
    
    @staticmethod
    def _terraform(repo_type):
        return f'''# main.tf
resource "random_pet" "name" {{
  length = {random.randint(1,3)}
}}

output "name" {{
  value = random_pet.name.id
}}
'''
    
    @staticmethod
    def _shell_script(repo_type):
        return f'''#!/bin/bash
# {secrets.token_hex(4)}.sh
echo "Running script"
exit 0
'''
    
    @staticmethod
    def _csharp(repo_type):
        return f'''using System;

namespace MyGame
{{
    public class Config
    {{
        public static string Version = "{random.randint(1,5)}.{random.randint(0,9)}";
    }}
}}
'''
    
    @staticmethod
    def _solidity(repo_type):
        return f'''pragma solidity ^0.8.0;

contract Storage {{
    uint256 private data = {random.randint(1,1000)};
    function set(uint256 x) public {{ data = x; }}
    function get() public view returns (uint256) {{ return data; }}
}}
'''
    
    @staticmethod
    def _truffle(repo_type):
        return f'''module.exports = {{
  networks: {{
    development: {{
      host: "127.0.0.1",
      port: 8545,
      network_id: "*"
    }}
  }}
}};
'''
    
    @staticmethod
    def _arduino(repo_type):
        return f'''// {secrets.token_hex(4)}.ino
void setup() {{
    Serial.begin(9600);
}}

void loop() {{
    Serial.println("Hello");
    delay(1000);
}}
'''
    
    @staticmethod
    def _text_file(repo_type):
        return f"Documentation file generated at {datetime.now().isoformat()}\n"


# ======================== GIT SIMULATOR ========================
class GitSimulator:
    @staticmethod
    def init_repo(repo_path: Path):
        if not Config.ENABLE_GIT_HISTORY:
            return
        git_dir = repo_path / '.git'
        if git_dir.exists():
            return
        git_dir.mkdir(exist_ok=True)
        (git_dir / 'objects').mkdir(exist_ok=True)
        (git_dir / 'refs' / 'heads').mkdir(parents=True, exist_ok=True)
        (git_dir / 'HEAD').write_text('ref: refs/heads/main')
        GitSimulator._create_fake_commits(repo_path, git_dir)
    
    @staticmethod
    def _create_fake_commits(repo_path: Path, git_dir: Path):
        tree_hash = hashlib.sha1(b'tree placeholder').hexdigest()
        tree_dir = git_dir / 'objects' / tree_hash[:2]
        tree_dir.mkdir(exist_ok=True)
        (tree_dir / tree_hash[2:]).write_text('tree content')
        commits = []
        for i in range(random.randint(3, 8)):
            commit_time = int(time.time()) - i * 86400 * random.randint(1, 3)
            commit_data = f"""tree {tree_hash}
author Dev <dev@example.com> {commit_time} +0000
committer Dev <dev@example.com> {commit_time} +0000

Update #{i}
"""
            commit_hash = hashlib.sha1(commit_data.encode()).hexdigest()
            commit_dir = git_dir / 'objects' / commit_hash[:2]
            commit_dir.mkdir(exist_ok=True)
            (commit_dir / commit_hash[2:]).write_text(commit_data)
            commits.append(commit_hash)
        if commits:
            (git_dir / 'refs' / 'heads' / 'main').write_text(commits[-1])


# ======================== TIMESTAMP RANDOMIZER ========================
class TimestampRandomizer:
    @staticmethod
    def randomize(file_path: Path):
        if not Config.ENABLE_TIMESTAMP_RANDOMIZE:
            return
        years_ago = random.randint(1, 3)
        fake_time = datetime.now() - timedelta(days=365*years_ago, hours=random.randint(0, 8760))
        mod_time = fake_time.timestamp()
        os.utime(file_path, (mod_time, mod_time))


# ======================== REPO MANAGER (CORE) ========================
class RepoManager:
    def __init__(self):
        self.repos_root = Config.REPOS_ROOT
        self.metadata_root = Config.METADATA_ROOT
        self.temp_dir = Config.TEMP_DIR
        for dir_path in [self.repos_root, self.metadata_root, self.temp_dir]:
            dir_path.mkdir(exist_ok=True, parents=True)
        self.repo_structure_cache = {}
        self.files_metadata = {}
        self._init_repos()
        self._load_metadata()
    
    def _init_repos(self):
        for i in range(Config.TOTAL_REPOS):
            repo_path = self.repos_root / f"repo_{i:03d}"
            if repo_path.exists():
                self._update_repo_cache(i)
                continue
            repo_path.mkdir(exist_ok=True)
            repo_type = Config.REPO_TYPES[i % len(Config.REPO_TYPES)]
            
            # Buat struktur folder lebih kaya
            structures = {
                "web-development": ["src", "public", "utils", "tests", "config", "scripts"],
                "machine-learning": ["models", "data", "notebooks", "utils", "configs", "tests", "scripts"],
                "data-science": ["analysis", "data", "notebooks", "scripts", "visualization", "reports"],
                "mobile-apps": ["android", "ios", "lib", "screens", "utils", "assets", "tests"],
                "devops-tools": ["docker", "kubernetes", "scripts", "terraform", "monitoring", "config"],
                "game-development": ["assets", "scripts", "scenes", "prefabs", "shaders", "tests"],
                "blockchain": ["contracts", "tests", "scripts", "migrations", "utils", "config"],
                "iot-projects": ["firmware", "schematics", "docs", "tests", "utils", "config"]
            }
            folders = structures.get(repo_type, structures["web-development"])
            for folder in folders:
                (repo_path / folder).mkdir(exist_ok=True)
            
            # File dasar proyek
            (repo_path / "README.md").write_text(f"# Project {repo_type}\n\nAuto-generated.\n")
            (repo_path / ".gitignore").write_text("__pycache__\n*.pyc\nnode_modules\n")
            if repo_type in ["web-development", "mobile-apps"]:
                (repo_path / "package.json").write_text(json.dumps({
                    "name": f"project-{secrets.token_hex(4)}",
                    "version": "1.0.0",
                    "scripts": {"test": "echo test"}
                }, indent=2))
            elif repo_type in ["machine-learning", "data-science"]:
                (repo_path / "requirements.txt").write_text("numpy\npandas\nscikit-learn\n")
            
            # Tambahkan file realistis
            RealisticFileGenerator.generate(repo_path, repo_type)
            
            # Simulasi git history
            GitSimulator.init_repo(repo_path)
            
            self.repo_structure_cache[i] = {"type": repo_type, "folders": folders}
    
    def _update_repo_cache(self, idx):
        repo_path = self.repos_root / f"repo_{idx:03d}"
        if repo_path.exists():
            repo_type = Config.REPO_TYPES[idx % len(Config.REPO_TYPES)]
            folders = [d.name for d in repo_path.iterdir() if d.is_dir()]
            self.repo_structure_cache[idx] = {"type": repo_type, "folders": folders or ["src"]}
    
    def _load_metadata(self):
        meta_file = self.metadata_root / "system.json"
        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    data = json.load(f)
                self.files_metadata = {}
                for fid, fdata in data.items():
                    try:
                        self.files_metadata[fid] = expand_file(fdata)
                    except Exception as e:
                        print(f"Error expanding file {fid}: {e}, skipping")
                        # Backup file corrupt
                        corrupt_backup = self.metadata_root / f"corrupt_{fid}_{int(time.time())}.json"
                        with open(corrupt_backup, 'w') as cf:
                            json.dump(fdata, cf)
                # Simpan ulang metadata yang bersih
                self._save_metadata()
            except Exception as e:
                print(f"Metadata load error: {e}")
                # Backup file utama
                meta_file.rename(self.metadata_root / f"system_corrupt_{int(time.time())}.json")
                self.files_metadata = {}
        else:
            self.files_metadata = {}
    
    def _save_metadata(self):
        meta_file = self.metadata_root / "system.json"
        data = {fid: compact_file(fmeta) for fid, fmeta in self.files_metadata.items()}
        with open(meta_file, 'w') as f:
            json.dump(data, f, separators=(',', ':'))  # compact JSON
        backup = self.metadata_root / f"backup_{int(time.time())}.json"
        with open(backup, 'w') as f:
            json.dump(data, f, separators=(',', ':'))
    
    def _get_repo_size(self, repo_index: int) -> int:
        repo_path = self.repos_root / f"repo_{repo_index:03d}"
        total = 0
        for f in repo_path.rglob('*'):
            if f.is_file():
                total += f.stat().st_size
        return total
    
    def _select_repo_for_chunk(self, estimated_size: int) -> Tuple[int, str]:
        candidates = []
        for i in range(Config.TOTAL_REPOS):
            current = self._get_repo_size(i)
            if current + estimated_size < Config.REPO_MAX_SIZE:
                candidates.append((i, current))
        if candidates:
            candidates.sort(key=lambda x: x[1])
            idx = candidates[0][0]
            return idx, Config.REPO_TYPES[idx % len(Config.REPO_TYPES)]
        # fallback
        idx = random.randint(0, Config.TOTAL_REPOS-1)
        return idx, Config.REPO_TYPES[idx % len(Config.REPO_TYPES)]
    
    def store_chunk(self, chunk_data: bytes, original_name: str, chunk_index: int, file_key: bytes) -> ChunkInfo:
        compressed = zlib.compress(chunk_data, level=6)
        if HAVE_AES:
            iv, ciphertext, tag = self._aes_encrypt(compressed, file_key)
            algo = "aes-256-gcm"
            iv_b64 = base64.b64encode(iv).decode()
            tag_b64 = base64.b64encode(tag).decode()
            xor_key_str = ""
            data_to_encode = ciphertext
        else:
            xor_key = random.randint(1, 255)
            obfuscated = bytearray(b ^ xor_key for b in compressed)
            algo = "xor"
            iv_b64 = ""
            tag_b64 = ""
            xor_key_str = str(xor_key)
            data_to_encode = bytes(obfuscated)
        
        encoded_str, encoding_used = EncodingManager.encode(data_to_encode)
        
        # Opsional: tambahkan steganografi whitespace pada encoded_str? Tidak, karena akan merusak decoding.
        # Stego dilakukan di tingkat template nanti (jika diinginkan).
        
        estimated_final_size = len(encoded_str) + 1000
        repo_index, repo_type = self._select_repo_for_chunk(estimated_final_size)
        
        filename = self._generate_filename(repo_type, chunk_index)
        folders = self.repo_structure_cache.get(repo_index, {}).get("folders", ["src"])
        target_folder = random.choice(folders) if folders else "src"
        
        repo_path = self.repos_root / f"repo_{repo_index:03d}"
        file_path = repo_path / target_folder / filename
        file_path.parent.mkdir(exist_ok=True, parents=True)
        
        # Metadata untuk template (tanpa kata mencolok)
        meta = {
            "fragment_id": hashlib.sha256(chunk_data).hexdigest()[:12],
            "chunk_index": chunk_index
        }
        code_content = CodeTemplateGenerator.generate(repo_type, encoded_str, meta)
        
        # Jika steganografi whitespace diaktifkan, sisipkan bit dari hash atau sesuatu
        if Config.ENABLE_WHITESPACE_STEGO:
            # Sisipkan beberapa bit acak untuk membuatnya lebih alami? Atau bisa hash chunk.
            # Di sini kita sisipkan 16 bit pertama dari hash chunk
            bits = bin(int(hashlib.sha256(chunk_data).hexdigest(), 16))[2:][:16]
            code_content = StegoText.hide(code_content, bits)
        
        file_path.write_text(code_content, encoding='utf-8')
        TimestampRandomizer.randomize(file_path)
        
        chunk_info = ChunkInfo(
            chunk_id=hashlib.sha256(chunk_data).hexdigest()[:16],
            repo_index=repo_index,
            file_path=str(file_path.relative_to(repo_path)),
            index=chunk_index,
            hash=hashlib.sha256(chunk_data).hexdigest(),
            created_at=datetime.now().isoformat(),
            encryption_algo=algo,
            encryption_iv=iv_b64,
            encryption_tag=tag_b64,
            xor_key=xor_key_str,
            encoding_used=encoding_used
        )
        return chunk_info
    
    def _aes_encrypt(self, data: bytes, key: bytes) -> Tuple[bytes, bytes, bytes]:
        iv = get_random_bytes(Config.AES_IV_SIZE)
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        return iv, ciphertext, tag
    
    def _aes_decrypt(self, ciphertext: bytes, key: bytes, iv: bytes, tag: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ciphertext, tag)
    
    def _generate_filename(self, repo_type: str, idx: int) -> str:
        # Nama file realistis
        names = [
            f"config_{secrets.token_hex(2)}.py",
            f"utils_{idx}.js",
            f"helper_{random.randint(100,999)}.ts",
            f"settings_{idx}.json",
            f"data_{secrets.token_hex(2)}.yaml",
            f"module_{idx}.py",
            f"test_{secrets.token_hex(2)}.sh",
            f"main_{idx}.c",
            f"script_{idx}.lua",
        ]
        return random.choice(names)
    
    def retrieve_chunk(self, chunk_info: ChunkInfo, file_key: bytes) -> bytes:
        repo_path = self.repos_root / f"repo_{chunk_info.repo_index:03d}"
        file_path = repo_path / chunk_info.file_path
        if not file_path.exists():
            raise FileNotFoundError(f"Chunk file missing: {chunk_info.file_path}")
        
        code = file_path.read_text(encoding='utf-8')
        
        # Ekstrak steganografi whitespace jika ada (tidak mengganggu decoding)
        # Kita abaikan karena hanya bit acak, tidak perlu diekstrak untuk data.
        
        encoded_str = self._extract_encoded_from_code(code)
        if not encoded_str:
            raise ValueError("No encoded data found")
        
        try:
            data_blob = EncodingManager.decode(encoded_str, chunk_info.encoding_used)
        except Exception as e:
            print(f"Decode error with {chunk_info.encoding_used}: {e}")
            for enc in Config.ENCODINGS:
                try:
                    data_blob = EncodingManager.decode(encoded_str, enc)
                    print(f"Fallback success with {enc}")
                    break
                except:
                    continue
            else:
                raise
        
        if chunk_info.encryption_algo == "aes-256-gcm":
            iv = base64.b64decode(chunk_info.encryption_iv)
            tag = base64.b64decode(chunk_info.encryption_tag)
            compressed = self._aes_decrypt(data_blob, file_key, iv, tag)
        elif chunk_info.encryption_algo == "xor":
            xor_key = int(chunk_info.xor_key)
            compressed = bytes(b ^ xor_key for b in data_blob)
        else:
            compressed = data_blob
        
        chunk_data = zlib.decompress(compressed)
        if hashlib.sha256(chunk_data).hexdigest() != chunk_info.hash:
            print(f"Hash mismatch for chunk {chunk_info.chunk_id}")
        return chunk_data
    
    def _extract_encoded_from_code(self, code: str) -> str:
        # Pola yang lebih umum untuk menangkap string panjang
        patterns = [
            r'API_SECRET\s*=\s*["\']([^"\']*)["\']',
            r'apiKey\s*:\s*["\']([^"\']*)["\']',
            r'content\s*=\s*["\']([^"\']*)["\']',
            r'DATA\s*=\s*["\']([^"\']*)["\']',
            r'secret\s*=\s*["\']([^"\']*)["\']',
            r'"secret"\s*:\s*"([^"]*)"',
            r'"payload"\s*:\s*"([^"]*)"',
            r'<string name="api_key">([^<]*)</string>',
            r'<meta name="config" content="([^"]*)">',
            r'data-config="([^"]*)"',
            r'default\s*=\s*["\']([^"\']*)["\']',
            r'from:\s*["\']([^"\']*)["\']',
            r'\_WEIGHTS\s*=\s*["\']([^"\']*)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, code, re.IGNORECASE)
            if m:
                return m.group(1)
        
        # Fallback: cari string panjang base64-like
        candidates = re.findall(r'["\']([A-Za-z0-9+/=]{50,})["\']', code)
        if candidates:
            return candidates[0]
        return ""
    
    def delete_chunk(self, chunk_info: ChunkInfo):
        repo_path = self.repos_root / f"repo_{chunk_info.repo_index:03d}"
        file_path = repo_path / chunk_info.file_path
        if file_path.exists():
            file_path.unlink()
            # Hapus folder jika kosong
            try:
                if file_path.parent.is_dir() and not any(file_path.parent.iterdir()):
                    file_path.parent.rmdir()
            except:
                pass
    
    def get_file_data(self, file_id: str) -> Optional[bytes]:
        if file_id not in self.files_metadata:
            return None
        meta = self.files_metadata[file_id]
        file_key = base64.b64decode(meta.file_key) if meta.file_key else b''
        chunks = sorted(meta.chunks, key=lambda x: x.index)
        data = bytearray()
        for c in chunks:
            try:
                chunk = self.retrieve_chunk(c, file_key)
                data.extend(chunk)
            except Exception as e:
                print(f"Error retrieving chunk {c.chunk_id}: {e}")
                return None
        return bytes(data)
    
    def get_preview_data(self, file_id: str, max_size=10*1024*1024) -> Optional[dict]:
        if file_id not in self.files_metadata:
            return None
        meta = self.files_metadata[file_id]
        if meta.original_size > max_size:
            return {"too_large": True, "max_allowed": max_size}
        data = self.get_file_data(file_id)
        if data is None:
            return None
        mime = meta.mime_type
        if mime.startswith('image/'):
            return {"type": "image", "data": base64.b64encode(data).decode(), "mime": mime}
        elif mime.startswith('text/'):
            text = data.decode('utf-8', errors='ignore')[:10000]
            return {"type": "text", "text": text, "mime": mime}
        elif mime == 'application/pdf':
            return {"type": "pdf", "data": base64.b64encode(data).decode(), "mime": mime}
        else:
            return {"type": "binary", "message": "Binary file", "mime": mime}
    
    def get_repo_stats(self) -> Dict:
        stats = {}
        for i in range(Config.TOTAL_REPOS):
            size = self._get_repo_size(i)
            repo_path = self.repos_root / f"repo_{i:03d}"
            files = sum(1 for _ in repo_path.rglob('*') if _.is_file())
            stats[f"repo_{i:03d}"] = {
                "size": size,
                "files": files,
                "utilization": (size / Config.REPO_MAX_SIZE) * 100
            }
        return stats
    
    def add_realistic_files_to_all(self):
        """Tambahkan file realistis ke semua repositori secara periodik."""
        for i in range(Config.TOTAL_REPOS):
            repo_path = self.repos_root / f"repo_{i:03d}"
            if repo_path.exists():
                repo_type = Config.REPO_TYPES[i % len(Config.REPO_TYPES)]
                RealisticFileGenerator.generate(repo_path, repo_type)
    
    def verify_integrity(self, file_id: str) -> bool:
        if file_id not in self.files_metadata:
            return False
        meta = self.files_metadata[file_id]
        file_key = base64.b64decode(meta.file_key) if meta.file_key else b''
        for c in meta.chunks:
            try:
                data = self.retrieve_chunk(c, file_key)
                if hashlib.sha256(data).hexdigest() != c.hash:
                    return False
            except:
                return False
        return True


# ======================== FLASK APP ========================
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
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "total_repos": Config.TOTAL_REPOS,
        "files_count": len(repo_manager.files_metadata),
        "aes_available": HAVE_AES,
        "encodings": Config.ENCODINGS
    })

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file"}), 400
        f = request.files['file']
        if f.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        
        filename = secure_filename(f.filename)
        data = f.read()
        size = len(data)
        if size == 0:
            return jsonify({"error": "Empty file"}), 400
        
        mime, _ = mimetypes.guess_type(filename)
        mime = mime or "application/octet-stream"
        tags = []
        if mime.startswith('image/'):
            tags = ["image", "media"]
        elif mime.startswith('text/'):
            tags = ["text", "document"]
        elif mime == 'application/pdf':
            tags = ["pdf", "document"]
        else:
            tags = ["binary"]
        
        if HAVE_AES:
            file_key = get_random_bytes(Config.AES_KEY_SIZE)
            file_key_b64 = base64.b64encode(file_key).decode()
        else:
            file_key = b''
            file_key_b64 = ''
        
        chunks = []
        num_chunks = (size + Config.RAW_CHUNK_SIZE - 1) // Config.RAW_CHUNK_SIZE
        for i in range(num_chunks):
            start = i * Config.RAW_CHUNK_SIZE
            end = min(start + Config.RAW_CHUNK_SIZE, size)
            chunk_data = data[start:end]
            chunk_info = repo_manager.store_chunk(chunk_data, filename, i, file_key)
            chunks.append(chunk_info)
        
        file_id = hashlib.sha256(f"{filename}{datetime.now()}{random.random()}".encode()).hexdigest()[:20]
        
        meta = FileMetadata(
            file_id=file_id,
            original_name=filename,
            original_size=size,
            mime_type=mime,
            upload_time=datetime.now().isoformat(),
            chunks=chunks,
            tags=tags,
            file_key=file_key_b64
        )
        repo_manager.files_metadata[file_id] = meta
        repo_manager._save_metadata()
        
        return jsonify({
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "size": size,
            "chunks": num_chunks,
            "encryption": "AES-256-GCM" if HAVE_AES else "XOR",
            "chunk_details": [
                {"chunk_id": c.chunk_id, "repo_index": c.repo_index, "path": c.file_path, "encoding": c.encoding_used}
                for c in chunks
            ]
        })
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/files', methods=['GET'])
def list_files():
    files = []
    for fid, meta in repo_manager.files_metadata.items():
        files.append({
            "id": fid,
            "filename": meta.original_name,
            "size": meta.original_size,
            "mime": meta.mime_type,
            "upload_time": meta.upload_time,
            "chunk_count": len(meta.chunks),
            "tags": meta.tags
        })
    return jsonify({"files": files})

@app.route('/api/file/<file_id>', methods=['GET'])
def download(file_id):
    if file_id not in repo_manager.files_metadata:
        return jsonify({"error": "Not found"}), 404
    meta = repo_manager.files_metadata[file_id]
    data = repo_manager.get_file_data(file_id)
    if data is None:
        return jsonify({"error": "Failed to reconstruct"}), 500
    
    temp = Config.TEMP_DIR / f"dl_{file_id}_{int(time.time())}.tmp"
    temp.write_bytes(data)
    response = send_file(
        str(temp),
        as_attachment=True,
        download_name=meta.original_name,
        mimetype=meta.mime_type
    )
    @response.call_on_close
    def cleanup():
        try:
            temp.unlink()
        except:
            pass
    return response

@app.route('/api/file/<file_id>/preview', methods=['GET'])
def preview(file_id):
    if file_id not in repo_manager.files_metadata:
        return jsonify({"error": "Not found"}), 404
    meta = repo_manager.files_metadata[file_id]
    if meta.original_size > 10 * 1024 * 1024:
        return jsonify({"error": "Too large for preview", "max": "10MB"}), 400
    preview = repo_manager.get_preview_data(file_id)
    if preview is None:
        return jsonify({"error": "Preview failed"}), 500
    return jsonify(preview)

@app.route('/api/file/<file_id>/info', methods=['GET'])
def info(file_id):
    if file_id not in repo_manager.files_metadata:
        return jsonify({"error": "Not found"}), 404
    meta = repo_manager.files_metadata[file_id]
    dist = defaultdict(int)
    for c in meta.chunks:
        dist[f"repo_{c.repo_index:03d}"] += 1
    return jsonify({
        "id": file_id,
        "filename": meta.original_name,
        "size": meta.original_size,
        "mime": meta.mime_type,
        "upload_time": meta.upload_time,
        "chunk_count": len(meta.chunks),
        "tags": meta.tags,
        "encryption": meta.chunks[0].encryption_algo if meta.chunks else "none",
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "repo_index": c.repo_index,
                "path": c.file_path,
                "index": c.index,
                "encoding": c.encoding_used,
                "algo": c.encryption_algo
            }
            for c in meta.chunks
        ],
        "repo_distribution": dict(dist)
    })

@app.route('/api/file/<file_id>', methods=['DELETE'])
def delete(file_id):
    if file_id not in repo_manager.files_metadata:
        return jsonify({"error": "Not found"}), 404
    meta = repo_manager.files_metadata[file_id]
    for c in meta.chunks:
        repo_manager.delete_chunk(c)
    del repo_manager.files_metadata[file_id]
    repo_manager._save_metadata()
    return jsonify({"success": True, "message": f"Deleted {meta.original_name}"})

@app.route('/api/stats', methods=['GET'])
def stats():
    total_files = len(repo_manager.files_metadata)
    total_size = sum(f.original_size for f in repo_manager.files_metadata.values())
    total_chunks = sum(len(f.chunks) for f in repo_manager.files_metadata.values())
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
            "total_repos": Config.TOTAL_REPOS,
            "aes_available": HAVE_AES
        }
    })

@app.route('/api/repos', methods=['GET'])
def list_repos():
    repo_stats = repo_manager.get_repo_stats()
    repos = []
    for i, rid in enumerate(sorted(repo_stats.keys())):  # urut
        repo_type = Config.REPO_TYPES[i % len(Config.REPO_TYPES)]
        repos.append({
            "id": rid,
            "type": repo_type,
            "size": repo_stats[rid]["size"],
            "files": repo_stats[rid]["files"],
            "utilization": repo_stats[rid]["utilization"]
        })
    return jsonify({"repos": repos})

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    deleted = 0
    for tmp in Config.TEMP_DIR.glob("*.tmp"):
        if tmp.is_file() and (time.time() - tmp.stat().st_mtime) > 300:
            tmp.unlink()
            deleted += 1
    return jsonify({"success": True, "deleted": deleted})

@app.route('/api/maintenance/realistic', methods=['POST'])
def add_realistic():
    repo_manager.add_realistic_files_to_all()
    return jsonify({"success": True, "message": "Realistic files added"})

@app.route('/api/verify/<file_id>', methods=['GET'])
def verify(file_id):
    ok = repo_manager.verify_integrity(file_id)
    return jsonify({"file_id": file_id, "integrity_ok": ok})


if __name__ == '__main__':
    print("=" * 80)
    print("STEALTH STORAGE SYSTEM - ULTIMATE EDITION (FULL STEALTH)")
    print("=" * 80)
    print(f"Repositories: {Config.TOTAL_REPOS}")
    print(f"Chunk size: {Config.RAW_CHUNK_SIZE/1024/1024:.1f} MB")
    print(f"Encodings: {Config.ENCODINGS}")
    print(f"AES-256: {'YES' if HAVE_AES else 'NO (fallback XOR)'}")
    print(f"Base91: {'YES' if HAVE_BASE91 else 'NO'}")
    print(f"Git history simulation: {'ON' if Config.ENABLE_GIT_HISTORY else 'OFF'}")
    print(f"Realistic files: ON (no dummy words)")
    print(f"Timestamp randomization: {'ON' if Config.ENABLE_TIMESTAMP_RANDOMIZE else 'OFF'}")
    print(f"Whitespace stego: {'ON' if Config.ENABLE_WHITESPACE_STEGO else 'OFF'}")
    print(f"Existing files: {len(repo_manager.files_metadata)}")
    print("\nServer running on http://0.0.0.0:5000")
    print("=" * 80)
    app.run(host='0.0.0.0', port=5000, debug=True)