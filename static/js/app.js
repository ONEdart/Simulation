// Konfigurasi Sistem
const CONFIG = {
    CHUNK_SIZE: 1024 * 1024 * 2, // 2MB per chunk
    REPOSITORIES: 4, // Jumlah repository simulasi
    BASE85_ALPHABET: "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~",
    METADATA_FILE: 'metadata.json'
};

// Warna untuk setiap repo (deterministic)
const REPO_COLORS = [
    '#3B82F6', // Blue
    '#10B981', // Green
    '#F59E0B', // Yellow
    '#EF4444', // Red
    '#8B5CF6', // Purple
    '#EC4899', // Pink
    '#06B6D4', // Cyan
    '#84CC16'  // Lime
];

// State aplikasi Vue
const app = Vue.createApp({
    data() {
        return {
            // UI State
            currentPage: 'drive',
            dragOver: false,
            showRenameModal: false,
            
            // Data State
            files: [],
            repos: Array.from({ length: CONFIG.REPOSITORIES }, (_, i) => `repo_${i}`),
            uploadQueue: [],
            systemLog: [],
            reconstructionLog: [],
            
            // File State
            currentFile: null,
            filePreviewUrl: null,
            filePreviewContent: '',
            
            // Edit State
            renameFileId: null,
            renameName: '',
            
            // Performance tracking
            storageUsed: 0,
            totalChunks: 0
        };
    },
    
    computed: {
        formattedSystemLog() {
            return this.systemLog.map(log => `[${log.time}] ${log.message}`).join('\n');
        }
    },
    
    async created() {
        this.addSystemLog('Sistem GitFS Simulator dimulai', 'info');
        await this.loadMetadata();
        this.calculateStorage();
        this.initializeRepositories();
        
        // Simulasi filesystem watcher
        setInterval(() => {
            this.calculateStorage();
        }, 5000);
    },
    
    methods: {
        // ========== SYSTEM UTILITIES ==========
        
        addSystemLog(message, type = 'info') {
            const time = new Date().toLocaleTimeString('id-ID', { 
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
            this.systemLog.push({ time, message, type });
        },
        
        addReconstructionLog(message, type = 'info') {
            const timestamp = new Date().toLocaleTimeString('id-ID', { 
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                fractionalSecondDigits: 3
            });
            this.reconstructionLog.push({ timestamp, message, type });
        },
        
        getLogClass(type) {
            const classes = {
                info: 'text-blue-600',
                success: 'text-green-600',
                warning: 'text-yellow-600',
                error: 'text-red-600',
                system: 'text-purple-600'
            };
            return classes[type] || 'text-gray-600';
        },
        
        formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },
        
        formatDate(dateString) {
            const date = new Date(dateString);
            return date.toLocaleDateString('id-ID', {
                day: '2-digit',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        },
        
        getFileIcon(mimeType) {
            const icons = {
                'image/': '🖼️',
                'text/': '📄',
                'audio/': '🎵',
                'video/': '🎬',
                'application/pdf': '📕',
                'application/zip': '📦',
                'application/json': '📊'
            };
            
            for (const [prefix, icon] of Object.entries(icons)) {
                if (mimeType.startsWith(prefix)) return icon;
            }
            return '📁';
        },
        
        getRepoColor(repoName) {
            const repoNum = parseInt(repoName.split('_')[1]) || 0;
            return REPO_COLORS[repoNum % REPO_COLORS.length];
        },
        
        // ========== FILE SYSTEM OPERATIONS ==========
        
        async loadMetadata() {
            try {
                const response = await fetch(CONFIG.METADATA_FILE);
                if (response.ok) {
                    const data = await response.json();
                    this.files = data.files || [];
                    this.totalChunks = this.files.reduce((sum, file) => sum + file.chunks.length, 0);
                    this.addSystemLog(`Metadata loaded: ${this.files.length} files`, 'success');
                }
            } catch (error) {
                this.addSystemLog('Membuat metadata baru', 'info');
                // Inisialisasi metadata kosong
                this.saveMetadata();
            }
        },
        
        async saveMetadata() {
            const metadata = {
                version: '1.0',
                system: 'GitFS Simulator',
                config: CONFIG,
                files: this.files,
                updated: new Date().toISOString()
            };
            
            try {
                // Simulasi penyimpanan metadata
                const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = CONFIG.METADATA_FILE;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                this.addSystemLog('Metadata disimpan', 'success');
            } catch (error) {
                this.addSystemLog(`Error saving metadata: ${error.message}`, 'error');
            }
        },
        
        calculateStorage() {
            this.storageUsed = this.files.reduce((sum, file) => sum + file.size, 0);
            this.totalChunks = this.files.reduce((sum, file) => sum + file.chunks.length, 0);
        },
        
        initializeRepositories() {
            this.addSystemLog(`Menginisialisasi ${this.repos.length} repository`, 'info');
            this.repos.forEach(repo => {
                this.addSystemLog(`Repository ${repo} siap`, 'success');
            });
        },
        
        // ========== FILE UPLOAD & PROCESSING ==========
        
        handleDrop(event) {
            this.dragOver = false;
            const files = Array.from(event.dataTransfer.files);
            this.processFiles(files);
        },
        
        handleFileSelect(event) {
            const files = Array.from(event.target.files);
            this.processFiles(files);
            event.target.value = '';
        },
        
        processFiles(files) {
            files.forEach(file => {
                if (file.size > 100 * 1024 * 1024) { // 100MB limit
                    this.addSystemLog(`File ${file.name} terlalu besar (${this.formatBytes(file.size)})`, 'error');
                    return;
                }
                
                const uploadId = Date.now() + Math.random().toString(36).substr(2, 9);
                const queueItem = {
                    id: uploadId,
                    file,
                    status: 'Waiting',
                    progress: 0,
                    step: '',
                    chunks: null
                };
                
                this.uploadQueue.push(queueItem);
                this.processUploadQueue();
            });
        },
        
        async processUploadQueue() {
            const pendingItem = this.uploadQueue.find(item => item.status === 'Waiting');
            if (!pendingItem) return;
            
            pendingItem.status = 'Processing';
            pendingItem.step = 'Memulai proses...';
            
            try {
                // 1. Baca file sebagai binary
                pendingItem.step = 'Membaca file...';
                pendingItem.progress = 10;
                
                const arrayBuffer = await pendingItem.file.arrayBuffer();
                
                // 2. Encode ke Base85
                pendingItem.step = 'Encoding ke Base85...';
                pendingItem.progress = 30;
                
                const base85Data = this.encodeToBase85(arrayBuffer);
                
                // 3. Chunking
                pendingItem.step = 'Membagi menjadi chunk...';
                pendingItem.progress = 50;
                
                const chunks = this.createChunks(base85Data, pendingItem.file);
                pendingItem.chunks = chunks;
                
                // 4. Distribusi ke repo (simulasi)
                pendingItem.step = 'Mendistribusikan chunk...';
                pendingItem.progress = 70;
                
                const fileRecord = await this.createFileRecord(pendingItem.file, chunks);
                
                // 5. Simpan metadata
                pendingItem.step = 'Menyimpan metadata...';
                pendingItem.progress = 90;
                
                this.files.push(fileRecord);
                await this.saveMetadata();
                this.calculateStorage();
                
                // 6. Selesai
                pendingItem.status = 'Completed';
                pendingItem.progress = 100;
                pendingItem.step = 'Selesai';
                
                this.addSystemLog(`File "${pendingItem.file.name}" berhasil diupload (${chunks.length} chunk)`, 'success');
                
                // Hapus dari queue setelah 3 detik
                setTimeout(() => {
                    const index = this.uploadQueue.findIndex(item => item.id === pendingItem.id);
                    if (index > -1) this.uploadQueue.splice(index, 1);
                }, 3000);
                
            } catch (error) {
                pendingItem.status = 'Error';
                pendingItem.step = `Error: ${error.message}`;
                this.addSystemLog(`Upload gagal: ${error.message}`, 'error');
            }
            
            // Proses item berikutnya
            this.processUploadQueue();
        },
        
        encodeToBase85(arrayBuffer) {
            // Implementasi Base85 sederhana (ASCII85 variant)
            const bytes = new Uint8Array(arrayBuffer);
            let result = '';
            
            for (let i = 0; i < bytes.length; i += 4) {
                let chunk = 0;
                const pad = Math.min(4, bytes.length - i);
                
                for (let j = 0; j < 4; j++) {
                    chunk = chunk * 256 + (i + j < bytes.length ? bytes[i + j] : 0);
                }
                
                for (let j = 0; j < 5; j++) {
                    if (j <= pad) {
                        const digit = Math.floor(chunk / Math.pow(85, 4 - j)) % 85;
                        result += CONFIG.BASE85_ALPHABET[digit];
                    }
                }
            }
            
            return result;
        },
        
        decodeFromBase85(base85String) {
            const result = [];
            let chunk = 0;
            let count = 0;
            
            for (let i = 0; i < base85String.length; i++) {
                const char = base85String[i];
                const digit = CONFIG.BASE85_ALPHABET.indexOf(char);
                
                if (digit === -1) continue;
                
                chunk = chunk * 85 + digit;
                count++;
                
                if (count === 5) {
                    for (let j = 3; j >= 0; j--) {
                        result.push((chunk >> (8 * j)) & 0xFF);
                    }
                    chunk = 0;
                    count = 0;
                }
            }
            
            // Handle padding
            if (count > 0) {
                for (let j = 0; j < 4 - (count - 1); j++) {
                    chunk = chunk * 85 + 84;
                }
                for (let j = 3; j >= 0; j--) {
                    if (j > 4 - count) {
                        result.push((chunk >> (8 * j)) & 0xFF);
                    }
                }
            }
            
            return new Uint8Array(result);
        },
        
        createChunks(base85Data, file) {
            const chunks = [];
            const chunkCount = Math.ceil(base85Data.length / CONFIG.CHUNK_SIZE);
            
            for (let i = 0; i < chunkCount; i++) {
                const start = i * CONFIG.CHUNK_SIZE;
                const end = Math.min(start + CONFIG.CHUNK_SIZE, base85Data.length);
                const chunkData = base85Data.substring(start, end);
                
                // Distribusi round-robin ke repo
                const repoIndex = i % this.repos.length;
                const repo = this.repos[repoIndex];
                
                const chunkId = `chunk_${Date.now()}_${i}_${Math.random().toString(36).substr(2, 9)}`;
                const filename = `${chunkId}.b85`;
                
                chunks.push({
                    index: i,
                    repo: repo,
                    filename: filename,
                    data: chunkData,
                    size: chunkData.length,
                    hash: this.simpleHash(chunkData)
                });
            }
            
            return chunks;
        },
        
        simpleHash(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                hash = ((hash << 5) - hash) + str.charCodeAt(i);
                hash = hash & hash;
            }
            return Math.abs(hash).toString(36).substr(0, 8);
        },
        
        async createFileRecord(file, chunks) {
            const fileId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
            
            return {
                id: fileId,
                name: file.name,
                type: file.type,
                size: file.size,
                created: new Date().toISOString(),
                modified: new Date().toISOString(),
                chunks: chunks.map(chunk => ({
                    index: chunk.index,
                    repo: chunk.repo,
                    filename: chunk.filename,
                    size: chunk.size,
                    hash: chunk.hash
                }))
            };
        },
        
        // ========== FILE MANAGEMENT ==========
        
        getUniqueRepos(chunks) {
            return [...new Set(chunks.map(chunk => chunk.repo))];
        },
        
        editFileName(file) {
            this.renameFileId = file.id;
            this.renameName = file.name;
            this.showRenameModal = true;
        },
        
        saveRename() {
            const fileIndex = this.files.findIndex(f => f.id === this.renameFileId);
            if (fileIndex > -1) {
                this.files[fileIndex].name = this.renameName;
                this.files[fileIndex].modified = new Date().toISOString();
                this.saveMetadata();
                this.addSystemLog(`File di-rename: ${this.renameName}`, 'success');
            }
            this.showRenameModal = false;
            this.renameFileId = null;
            this.renameName = '';
        },
        
        async deleteFile(fileId) {
            if (!confirm('Hapus file ini? Tindakan ini tidak dapat dibatalkan.')) return;
            
            const fileIndex = this.files.findIndex(f => f.id === fileId);
            if (fileIndex > -1) {
                const fileName = this.files[fileIndex].name;
                this.files.splice(fileIndex, 1);
                await this.saveMetadata();
                this.calculateStorage();
                this.addSystemLog(`File "${fileName}" dihapus`, 'success');
                
                if (this.currentFile && this.currentFile.id === fileId) {
                    this.currentFile = null;
                    this.filePreviewUrl = null;
                }
            }
        },
        
        // ========== FILE VIEWING & RECONSTRUCTION ==========
        
        async viewFile(file) {
            this.currentPage = 'viewer';
            this.currentFile = file;
            this.reconstructionLog = [];
            this.filePreviewUrl = null;
            this.filePreviewContent = '';
            
            this.addReconstructionLog('Memulai rekonstruksi file...', 'info');
            this.addReconstructionLog(`File: ${file.name} (${file.chunks.length} chunk)`, 'info');
            
            try {
                // Simulasi: Rekonstruksi dari "repository"
                this.addReconstructionLog('Mengumpulkan chunk dari repository...', 'info');
                
                // Simulasi delay network
                await this.sleep(300);
                
                const sortedChunks = [...file.chunks].sort((a, b) => a.index - b.index);
                
                // Simulasi pengambilan chunk
                for (let i = 0; i < sortedChunks.length; i++) {
                    const chunk = sortedChunks[i];
                    this.addReconstructionLog(`Mengambil chunk ${i + 1} dari ${chunk.repo}...`, 'info');
                    await this.sleep(100); // Simulasi delay
                }
                
                // Simulasi: Gabungkan data Base85
                this.addReconstructionLog('Menggabungkan chunk...', 'info');
                await this.sleep(200);
                
                // Untuk simulasi, kita buat data Base85 dummy
                const dummyBase85Data = this.generateDummyBase85Data(file);
                
                this.addReconstructionLog('Mendecode Base85...', 'info');
                await this.sleep(300);
                
                // Decode Base85 (simulasi)
                const decodedData = this.decodeFromBase85(dummyBase85Data);
                
                this.addReconstructionLog('Membuat file dari data biner...', 'info');
                
                // Buat blob dari decoded data
                const blob = new Blob([decodedData], { type: file.type });
                
                // Set preview berdasarkan tipe file
                if (file.type.startsWith('image/')) {
                    this.filePreviewUrl = URL.createObjectURL(blob);
                    this.addReconstructionLog('Preview gambar siap', 'success');
                } else if (file.type.startsWith('text/')) {
                    const text = await blob.text();
                    this.filePreviewContent = text.substring(0, 5000) + (text.length > 5000 ? '...' : '');
                    this.addReconstructionLog('Preview teks siap', 'success');
                }
                
                this.addReconstructionLog('Rekonstruksi selesai', 'success');
                
            } catch (error) {
                this.addReconstructionLog(`Error: ${error.message}`, 'error');
            }
        },
        
        generateDummyBase85Data(file) {
            // Generate Base85 dummy berdasarkan tipe file
            const size = Math.min(10000, file.size); // Limit untuk demo
            let content = '';
            
            if (file.type.startsWith('text/')) {
                content = `// Simulasi file: ${file.name}\n// Size: ${file.size} bytes\n// Created: ${file.created}\n\n`;
                content += 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. '.repeat(50);
            } else if (file.type.startsWith('image/')) {
                // Untuk gambar, buat data Base85 dari canvas kecil
                const canvas = document.createElement('canvas');
                canvas.width = 200;
                canvas.height = 150;
                const ctx = canvas.getContext('2d');
                
                // Buat gradient
                const gradient = ctx.createLinearGradient(0, 0, 200, 150);
                gradient.addColorStop(0, '#3B82F6');
                gradient.addColorStop(1, '#8B5CF6');
                
                ctx.fillStyle = gradient;
                ctx.fillRect(0, 0, 200, 150);
                
                ctx.fillStyle = 'white';
                ctx.font = '20px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(file.name, 100, 80);
                
                const dataUrl = canvas.toDataURL('image/png');
                const base64Data = dataUrl.split(',')[1];
                // Convert base64 ke base85 dummy
                content = this.encodeToBase85(this.base64ToArrayBuffer(base64Data));
            }
            
            return content;
        },
        
        base64ToArrayBuffer(base64) {
            const binaryString = atob(base64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            return bytes.buffer;
        },
        
        async downloadFile(file) {
            try {
                this.addSystemLog(`Mendownload ${file.name}...`, 'info');
                
                // Simulasi rekonstruksi
                const dummyBase85Data = this.generateDummyBase85Data(file);
                const decodedData = this.decodeFromBase85(dummyBase85Data);
                const blob = new Blob([decodedData], { type: file.type });
                
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = file.name;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                this.addSystemLog(`Download ${file.name} berhasil`, 'success');
                
            } catch (error) {
                this.addSystemLog(`Download gagal: ${error.message}`, 'error');
            }
        },
        
        // ========== UTILITY FUNCTIONS ==========
        
        sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }
    }
});

// Mount aplikasi
app.mount('#app');

// Fungsi helper tambahan
window.addEventListener('DOMContentLoaded', () => {
    console.log('GitFS Simulator initialized');
});