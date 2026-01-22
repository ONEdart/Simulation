# 🗃️ Drive Simulator v2.5

**A Distributed File Storage System Simulation with Base85 Encoding & Batch Rotation**

A complete simulation of a stealthy, distributed file storage system that mimics GitHub's repository structure while implementing advanced chunking, encoding, and batch rotation mechanisms.

## 🚀 Features

### 🎯 **Core Capabilities**
- **Distributed Chunking**: Files split into 4MB chunks and encoded with Base85
- **Batch Rotation**: 100 repositories organized into batches with intelligent rotation
- **Stealth System**: Multiple layers of obscurity to avoid detection patterns
- **Real-time Preview**: Image, PDF, and text file preview in browser
- **Health Monitoring**: Automated system checks and maintenance

### 🔧 **Technical Highlights**
- **Base85 Encoding**: ~25% size increase with ASCII85 compatibility
- **Repository Management**: 1GB max per repo, 15 active repos at any time
- **Background Tasks**: Automated cleanup, health checks, and batch rotation
- **Metadata Backup**: Automatic backup system with versioning
- **Error Recovery**: Graceful degradation and self-healing mechanisms

## 📁 System Architecture

### Repository Structure
```
project/
├── app.py                 # Main Flask backend
├── static/
│   ├── index.html         # Upload & management interface
│   └── viewer.html        # File viewer interface
├── simulated_github_repos/ # 100 simulated repositories
│   ├── repo_000/
│   ├── repo_001/
│   └── ... (100 repos total)
├── system_metadata/       # System metadata and backups
├── temp_files/           # Temporary download files
└── logs/                 # System logs
```

### Data Flow
```
File Upload → Chunking (4MB) → Base85 Encoding → 
Distribute to Repositories → Update Metadata → 
Store in Multiple Repositories → Batch Rotation
```

## 🛠️ Installation

### Prerequisites
```bash
# Python 3.8 or higher required
python --version

# Install dependencies
pip install flask flask-cors
```

### Quick Start
```bash
# Clone or download the project
git clone <repository-url>
cd drive-simulator

# Run the server
python app.py

# Access at http://localhost:5000
```

## 📊 System Configuration

### Key Parameters
| Parameter | Value | Description |
|-----------|-------|-------------|
| `TOTAL_REPOS` | 100 | Total simulated repositories |
| `ACTIVE_REPOS` | 15 | Active repositories at any time |
| `REPO_MAX_SIZE` | 1GB | Maximum size per repository |
| `RAW_CHUNK_SIZE` | 4MB | Chunk size before encoding |
| `BATCH_SIZE` | 5 | Repositories per batch |
| `MAX_PARALLEL_CHUNKS` | 8 | Maximum concurrent chunk operations |

### Repository Types
The system simulates 5 types of repositories for stealth:
1. **Computer Vision Dataset** - Image and vision data
2. **Audio Processing Samples** - Audio files and samples
3. **ML Model Weights** - Machine learning model data
4. **Document Test Suite** - Document processing data
5. **Benchmark Data** - Performance benchmark data

## 🌐 API Endpoints

### Core Operations
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health check |
| `/api/upload` | POST | Upload file with chunking |
| `/api/files` | GET | List all files with pagination |
| `/api/file/<id>` | GET | Download complete file |
| `/api/file/<id>/info` | GET | Get detailed file info |
| `/api/file/<id>/preview` | GET | Preview file content |
| `/api/file/<id>` | DELETE | Delete file (soft then hard) |

### System Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats` | GET | Complete system statistics |
| `/api/batches` | GET | List all batches |
| `/api/repos` | GET | List all repositories |
| `/api/system/rotate` | POST | Manually rotate batches |
| `/api/system/maintenance` | POST | Run maintenance operations |
| `/api/search` | GET | Search files by criteria |

## 🖥️ Web Interface

### Upload & Management (`/`)
- **Drag & Drop Upload**: Intuitive file upload interface
- **Real-time Progress**: Chunk-by-chunk upload progress
- **File Management**: List, download, delete files
- **System Stats**: Real-time statistics dashboard
- **Batch Management**: View and manage repository batches

### File Viewer (`/viewer.html`)
- **Chunk Visualization**: Visual representation of chunk distribution
- **File Preview**: Native preview for images, PDFs, and text
- **Technical Details**: Complete file metadata and encoding info
- **Repository Map**: See which repositories contain file chunks

## 🔒 Stealth Mechanisms

### 5-Layer Obscurity System
1. **Pattern Randomization**: No predictable timing or size patterns
2. **Credible Structure**: Each repository looks like a real development project
3. **Natural Timing**: Uploads follow realistic human patterns (9AM-6PM)
4. **Encoding Variants**: Random choice of Base85, ASCII85, Base64
5. **Dynamic Rotation**: Active repositories rotate based on utilization

### Anti-Detection Features
- **Random Delays**: 100-800ms delays on API calls
- **Natural File Names**: Files renamed to look like dataset samples
- **Dummy Code Files**: Each repo contains Python scripts and configs
- **Realistic READMEs**: Complete documentation for each repository type
- **Gitignore Files**: Proper .gitignore files in each repo

## 🔄 Batch Rotation System

### How It Works
```
100 Repositories → 20 Batches (5 repos/batch) → 3 Active Batches
    ↓
Utilization Monitoring → Rotation Trigger → Batch Swap
    ↓
New Active Batches → Repository Status Update
```

### Rotation Triggers
- **Utilization > 80%**: Batch marked for rotation
- **Time-based**: Automatic rotation every 30 minutes
- **Manual**: API endpoint for manual rotation
- **Health-based**: Poor health score triggers rotation

## 📈 Performance Characteristics

### Storage Efficiency
| Metric | Value |
|--------|-------|
| Chunk Size | 4MB → 5MB (Base85 encoded) |
| Storage Overhead | ~25% |
| Max File Size | Unlimited (chunked) |
| Theoretical Capacity | 100GB (100 repos × 1GB) |

### Operational Limits
| Operation | Limit |
|-----------|-------|
| Upload Speed | Depends on chunk processing |
| Download Speed | Parallel chunk retrieval |
| Concurrent Operations | 8 parallel chunks |
| Memory Usage | Optimized for large files |

## 🚨 Error Handling

### Recovery Mechanisms
- **Metadata Backup**: Automatic backups every save
- **Chunk Validation**: Health checks verify chunk integrity
- **Auto-Retry**: Failed operations automatically retry
- **Graceful Degradation**: System maintains functionality during issues

### Common Error Scenarios
1. **Repository Full**: Automatically selects next available repo
2. **Chunk Corruption**: Health check detects and reports issues
3. **Network Issues**: Retry logic with exponential backoff
4. **Memory Limits**: Stream processing for large files

## 🧪 Testing

### Manual Testing
```bash
# Test upload
curl -X POST -F "file=@test.jpg" http://localhost:5000/api/upload

# Test download
curl -O http://localhost:5000/api/file/<file_id>

# Test system stats
curl http://localhost:5000/api/stats
```

### Test Scenarios
1. **Small Files**: < 4MB (single chunk)
2. **Medium Files**: 4MB - 100MB (multiple chunks)
3. **Large Files**: > 100MB (stress test chunking)
4. **Batch Rotation**: Manual rotation via API
5. **System Recovery**: Simulate failures and recovery

## 🔧 Maintenance

### Automated Tasks
| Task | Frequency | Description |
|------|-----------|-------------|
| Health Check | Every 5 minutes | Repository health validation |
| Batch Rotation | Every 30 minutes | Automatic batch rotation |
| Temp Cleanup | Every hour | Clean old temporary files |
| Stats Update | Every 2 minutes | Update system statistics |

### Manual Maintenance
```bash
# Rotate batches manually
curl -X POST http://localhost:5000/api/system/rotate

# Run health check
curl -X POST -H "Content-Type: application/json" \
  -d '{"action":"recalculate_health"}' \
  http://localhost:5000/api/system/maintenance

# Cleanup temp files
curl -X POST -H "Content-Type: application/json" \
  -d '{"action":"cleanup"}' \
  http://localhost:5000/api/system/maintenance
```

## 📚 Technical Details

### Base85 Encoding
```python
# Example encoding
import base64
data = b"Hello World"
encoded = base64.b85encode(data)  # ASCII85/Base85
decoded = base64.b85decode(encoded)
```

### Chunk Storage Format
```
# File: repo_001/raw_samples/ab/sample_abc123.png.b85
# Dataset Sample File
# Repo: repo_001
# Batch: 0
# Generated: 2024-01-15T14:30:00.000Z
# Encoding: base85
# Original: myphoto.jpg
# Hash: abc123def456

<Base85 Encoded Data>
```

### Metadata Structure
```json
{
  "files": {
    "file_id": {
      "id": "abc123",
      "filename": "original.jpg",
      "size": 1048576,
      "chunks": [
        {"repo": "repo_001", "path": "...", "index": 0},
        {"repo": "repo_002", "path": "...", "index": 1}
      ]
    }
  },
  "system_state": {
    "total_files": 42,
    "total_size": 104857600,
    "active_batches": [0, 1, 2]
  }
}
```

## 🐛 Troubleshooting

### Common Issues

1. **Upload Fails**
   ```
   - Check disk space in temp_files directory
   - Verify repository directories exist
   - Check system logs for errors
   ```

2. **Download Fails**
   ```
   - Verify file ID exists
   - Check chunk integrity via health check
   - Ensure repositories are accessible
   ```

3. **Slow Performance**
   ```
   - Reduce MAX_PARALLEL_CHUNKS
   - Increase chunk size
   - Check system resources
   ```

4. **Memory Issues**
   ```
   - Large files use streaming
   - Reduce CACHE_SIZE in config
   - Monitor temp_files directory
   ```

### Log Files
- `logs/app_YYYYMMDD.log` - Application logs
- `logs/error_YYYYMMDD.log` - Error logs
- Check logs for detailed error information

## 🔮 Future Enhancements

### Planned Features
1. **Compression**: Add optional compression before encoding
2. **Encryption**: Optional client-side encryption
3. **WebDAV Support**: Mount as network drive
4. **CLI Interface**: Command-line tool for automation
5. **Docker Support**: Containerized deployment
6. **Cloud Sync**: Sync with actual cloud storage
7. **Versioning**: File version history
8. **Sharing**: File sharing with expiration

### Optimization Targets
- **Performance**: Faster chunk processing
- **Storage**: Better encoding efficiency
- **Memory**: Lower memory footprint
- **Scalability**: More repositories, larger capacity

## 📄 License

This project is for educational and demonstration purposes. Use responsibly and in accordance with all applicable laws and terms of service.

## 🙏 Acknowledgments

- **Base85/ASCII85**: Adobe's ASCII85 encoding standard
- **Flask**: Lightweight Python web framework
- **Vue.js**: Progressive JavaScript framework
- **Tailwind CSS**: Utility-first CSS framework

## 📞 Support

For issues, questions, or contributions:
1. Check the troubleshooting section
2. Review system logs
3. Open an issue with detailed information
4. Include relevant logs and error messages

---

**⚠️ Important Note**: This system is a simulation for educational purposes. It does not connect to real GitHub services and operates entirely locally.

**Version**: 2.5.0  
**Last Updated**: January 2024  
**Status**: Production Ready  
**Complexity**: Advanced
```

This comprehensive README covers:
1. **Installation & Setup** - Getting started instructions
2. **Architecture** - System design and data flow
3. **Features** - Complete feature list
4. **API Documentation** - All endpoints with examples
5. **Configuration** - All system parameters
6. **Usage Guides** - How to use the web interface
7. **Technical Details** - Implementation specifics
8. **Troubleshooting** - Common issues and solutions
9. **Future Plans** - Roadmap and enhancements

The README is professional, thorough, and suitable for both technical users and developers who want to understand or modify the system.
