const { createApp, ref, computed, onMounted } = Vue;

createApp({
    setup() {
        const fileInfo = ref(null);
        const fileData = ref(null);
        const loading = ref(true);
        const error = ref(null);
        const fileIdInput = ref('');
        const chunkLoadStatus = ref([]);

        // Get file ID from URL
        const getFileIdFromUrl = () => {
            const params = new URLSearchParams(window.location.search);
            return params.get('id');
        };

        // Format file size
        const formatSize = (bytes) => {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        };

        // Get unique repositories from chunks
        const uniqueRepos = computed(() => {
            if (!fileInfo.value || !fileInfo.value.chunks) return [];
            const repos = fileInfo.value.chunks.map(c => c.repo);
            return [...new Set(repos)];
        });

        // Count chunks in a repo
        const chunksInRepo = (repoName) => {
            if (!fileInfo.value || !fileInfo.value.chunks) return 0;
            return fileInfo.value.chunks.filter(c => c.repo === repoName).length;
        };

        // Count loaded chunks
        const loadedChunks = computed(() => {
            return chunkLoadStatus.value.filter(c => c.loaded).length;
        });

        // Check file type
        const isImage = computed(() => {
            return fileData.value && fileData.value.mime_type.startsWith('image/');
        });

        const isPDF = computed(() => {
            return fileData.value && fileData.value.mime_type === 'application/pdf';
        });

        const isText = computed(() => {
            return fileData.value && fileData.value.mime_type.startsWith('text/');
        });

        // Get preview type description
        const previewType = computed(() => {
            if (isImage.value) return 'Image Preview';
            if (isPDF.value) return 'PDF Preview';
            if (isText.value) return 'Text Preview';
            return 'Binary File';
        });

        // Decode text if it's a text file
        const decodedText = computed(() => {
            if (!fileData.value || !isText.value) return '';
            try {
                const binary = atob(fileData.value.data);
                return new TextDecoder().decode(new Uint8Array([...binary].map(c => c.charCodeAt(0))));
            } catch (e) {
                return 'Unable to decode text content';
            }
        });

        // Load file by ID
        const loadFileById = async (id = null) => {
            const fileId = id || fileIdInput.value || getFileIdFromUrl();
            
            if (!fileId) {
                loading.value = false;
                return;
            }

            try {
                loading.value = true;
                error.value = null;
                fileData.value = null;
                fileInfo.value = null;

                // First get file info from metadata
                const filesResponse = await fetch('/api/files');
                const filesData = await filesResponse.json();
                const file = filesData.files.find(f => f.id === fileId);
                
                if (!file) {
                    throw new Error('File not found');
                }

                fileInfo.value = file;

                // Initialize chunk loading status
                chunkLoadStatus.value = file.chunks.map(chunk => ({
                    ...chunk,
                    loaded: false,
                    loading: false
                }));

                // Simulate chunk loading (for UI demonstration)
                chunkLoadStatus.value.forEach((chunk, index) => {
                    setTimeout(() => {
                        chunk.loading = true;
                        chunkLoadStatus.value = [...chunkLoadStatus.value];
                        
                        setTimeout(() => {
                            chunk.loading = false;
                            chunk.loaded = true;
                            chunkLoadStatus.value = [...chunkLoadStatus.value];
                        }, 200);
                    }, index * 100);
                });

                // Get file preview data
                const response = await fetch(`/api/file/${fileId}/preview`);
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to load file');
                }

                const data = await response.json();
                fileData.value = data;
                
                // Update URL with file ID
                if (!id) {
                    const newUrl = `${window.location.pathname}?id=${fileId}`;
                    window.history.pushState({}, '', newUrl);
                }

            } catch (err) {
                console.error('Error loading file:', err);
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        };

        // Initialize
        onMounted(() => {
            const fileId = getFileIdFromUrl();
            if (fileId) {
                loadFileById(fileId);
            } else {
                loading.value = false;
            }
        });

        return {
            fileInfo,
            fileData,
            loading,
            error,
            fileIdInput,
            chunkLoadStatus,
            uniqueRepos,
            loadedChunks,
            isImage,
            isPDF,
            isText,
            previewType,
            decodedText,
            formatSize,
            chunksInRepo,
            loadFileById
        };
    }
}).mount('#app');