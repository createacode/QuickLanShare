/**
 * QuickLanShare web client.
 *
 * Uploads use the resumable chunk API (8 MiB chunks).  All downloads are
 * handed to the browser's native download manager so memory usage stays flat,
 * resume is handled by the browser and Chrome does not classify the download
 * as an automatic "multiple files" download.
 */
class FileTransferApp {
    constructor() {
        this.uploads = new Map();
        this.downloads = new Map();
        this.ws = null;
        this.messages = [];
        this.isHistoryVisible = false;
        this.allFiles = new Map();
        this.downloadedFileIds = new Set();
        this.autoShutdownEnabled = false;
        this.countdownInterval = null;
        this.selectedFiles = new Set();
        this._reconnectAttempts = 0;
        this._reconnectTimer = null;
        this._zipFrame = null;
        this._uploadNonce = this.loadUploadNonce();
        this.serverShuttingDown = false;
        this._largeNoticeTimer = null;
        this._largeNoticeInterval = null;
        this.loadDownloadedRecords();
        this.init();
    }

    loadUploadNonce() {
        try {
            let nonce = sessionStorage.getItem('qlsUploadNonce');
            if (!nonce) {
                nonce = (window.crypto && crypto.randomUUID)
                    ? crypto.randomUUID()
                    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
                sessionStorage.setItem('qlsUploadNonce', nonce);
            }
            return nonce;
        } catch (e) {
            return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
        }
    }

    static CHUNK_SIZE = 8 * 1024 * 1024;
    static MAX_CONCURRENT_UPLOADS = 3;
    static ZIP_LIMIT = 20 * 1024 * 1024 * 1024;
    static LARGE_DOWNLOAD_NOTICE = 1024 * 1024 * 1024; // 1 GiB
    static LARGE_NOTICE_SECONDS = 40;

    // ------------------------------------------------------------- bootstrap
    async init() {
        this.setupEventListeners();
        this.initWebSocket();
        await this.loadRoomInfo();
        await this.loadFileList();
        this.startAutoRefresh();
        this.initAutoShutdown();
        setInterval(() => this.syncAutoShutdownStatus(), 30 * 60 * 1000);
    }

    async api(path, options = {}) {
        const opts = { method: options.method || 'GET', headers: { ...(options.headers || {}) } };
        if (options.json !== undefined) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(options.json);
        }
        if (options.signal) opts.signal = options.signal;
        const response = await fetch(path, opts);
        let data = null;
        const type = response.headers.get('content-type') || '';
        if (type.includes('application/json')) {
            data = await response.json().catch(() => null);
        } else {
            const text = await response.text().catch(() => '');
            data = text ? { error: text } : null;
        }
        if (!response.ok) {
            const error = new Error((data && data.error) || `HTTP ${response.status}`);
            error.status = response.status;
            error.data = data;
            throw error;
        }
        return data;
    }

    loadDownloadedRecords() {
        try {
            const stored = localStorage.getItem('downloadedFiles');
            if (stored) this.downloadedFileIds = new Set(JSON.parse(stored));
        } catch (e) {
            this.downloadedFileIds = new Set();
        }
    }

    saveDownloadedRecords() {
        const MAX_RECORDS = 500;
        let arr = Array.from(this.downloadedFileIds);
        if (arr.length > MAX_RECORDS) {
            arr = arr.slice(-MAX_RECORDS);
            this.downloadedFileIds = new Set(arr);
        }
        try {
            localStorage.setItem('downloadedFiles', JSON.stringify(arr));
        } catch (e) {
            arr = arr.slice(-Math.floor(MAX_RECORDS / 2));
            this.downloadedFileIds = new Set(arr);
            try {
                localStorage.setItem('downloadedFiles', JSON.stringify(arr));
            } catch (ignored) { /* storage unavailable */ }
        }
    }

    markDownloaded(fileId) {
        this.downloadedFileIds.add(fileId);
        this.saveDownloadedRecords();
    }

    async loadRoomInfo() {
        try {
            const data = await this.api('/api/room-info');
            const qr = document.getElementById('qrCode');
            if (data.qr_code) qr.src = data.qr_code;
            document.getElementById('roomUrl').textContent = data.room_url;
            document.getElementById('clientCount').textContent = data.total_clients || 0;
            document.getElementById('chatCount').textContent = data.chat_messages || 0;
            document.getElementById('fileCount').textContent = data.total_files || 0;
            const version = document.getElementById('appVersion');
            if (version && data.version) version.textContent = `v${data.version}`;
            const copyright = document.getElementById('copyrightInfo');
            if (copyright && data.copyright) copyright.textContent = data.copyright;
            const shutdownWrapper = document.querySelector('.auto-shutdown-wrapper');
            if (shutdownWrapper) {
                shutdownWrapper.style.display = data.local_client ? '' : 'none';
            }
        } catch (e) {
            console.error('加载房间信息失败', e);
        }
    }

    // -------------------------------------------------------------- websocket
    initWebSocket() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${location.host}/ws`);
        this.ws = ws;
        ws.onopen = () => {
            this._reconnectAttempts = 0;
            document.getElementById('status').textContent = '已连接';
            document.getElementById('sharedTextStatus').textContent = '已连接';
            this.loadRoomInfo();
        };
        ws.onmessage = (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (err) {
                return;
            }
            if (data.type === 'welcome') {
                this.addChatHistory(data.chat_history || []);
            } else if (data.type === 'chat_message') {
                this.addMessage(data.message, false);
            } else if (data.type === 'delete_message') {
                this.deleteMessageLocally(data.message_id);
            } else if (data.type === 'error') {
                this.showMessage(data.error || '消息发送失败', 'error');
            } else if (data.type === 'server_shutdown') {
                this.handleServerShutdown(data.reason || 'server');
            }
        };
        ws.onclose = () => {
            this.ws = null;
            if (this.serverShuttingDown) return;
            document.getElementById('status').textContent = '断开，重连中...';
            document.getElementById('sharedTextStatus').textContent = '断开';
            this.scheduleReconnect();
        };
        ws.onerror = () => { /* onclose handles reconnection */ };
    }

    scheduleReconnect() {
        if (this._reconnectTimer) return;
        const delay = Math.min(30000, 1000 * Math.pow(2, this._reconnectAttempts)) + Math.random() * 400;
        this._reconnectAttempts += 1;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.initWebSocket();
        }, delay);
    }

    // -------------------------------------------------------------- chat
    addChatHistory(messages) {
        this.messages = [];
        const historyDiv = document.getElementById('historyContent');
        historyDiv.innerHTML = '';
        messages.forEach((msg) => this.addMessage(msg, true));
        if (messages.length) {
            this.updateLatestMessage(messages[messages.length - 1]);
        } else {
            document.getElementById('latestMessage').innerHTML = '<div class="message-placeholder">等待消息...</div>';
        }
        if (this.isHistoryVisible) this.refreshHistoryList();
    }

    addMessage(msg, isHistory = false) {
        if (!msg || !msg.id) return;
        this.messages.push(msg);
        if (this.messages.length > 100) this.messages.shift();
        this.updateLatestMessage(msg);
        if (this.isHistoryVisible || isHistory) this.addMessageToHistory(msg);
        if (!isHistory) {
            const counter = document.getElementById('chatCount');
            counter.textContent = (parseInt(counter.textContent, 10) || 0) + 1;
        }
    }

    updateLatestMessage(msg) {
        const container = document.getElementById('latestMessage');
        const time = msg.time_str || new Date((msg.timestamp || 0) * 1000).toLocaleTimeString();
        container.innerHTML = `
            <div class="latest-message-content">
                <div class="latest-message-header">
                    <span class="latest-message-sender">${this.escapeHtml(msg.client_name || '')}</span>
                    <span class="latest-message-time">${this.escapeHtml(time)}</span>
                    <button class="btn-copy-message" title="复制消息"><i class="fas fa-copy"></i></button>
                </div>
                <div class="latest-message-text">${this.escapeHtml(msg.message || '')}</div>
            </div>`;
        const copyBtn = container.querySelector('.btn-copy-message');
        if (copyBtn) copyBtn.addEventListener('click', () => this.copyToClipboard(msg.message || ''));
    }

    addMessageToHistory(msg) {
        const historyDiv = document.getElementById('historyContent');
        const empty = historyDiv.querySelector('.empty-history');
        if (empty) empty.remove();
        if (historyDiv.querySelector(`.message-item[data-msg-id="${CSS.escape(msg.id)}"]`)) return;
        const template = document.getElementById('messageItemTemplate');
        const clone = template.content.cloneNode(true);
        const item = clone.querySelector('.message-item');
        item.dataset.msgId = msg.id;
        item.querySelector('.message-sender').textContent = msg.client_name || '';
        item.querySelector('.message-time').textContent = msg.time_str || '';
        item.querySelector('.message-content').textContent = msg.message || '';
        item.querySelector('.btn-msg-delete').addEventListener('click', (event) => {
            event.stopPropagation();
            this.deleteMessageFromBackend(msg.id);
        });
        historyDiv.appendChild(item);
        historyDiv.scrollTop = historyDiv.scrollHeight;
    }

    refreshHistoryList() {
        const historyDiv = document.getElementById('historyContent');
        historyDiv.innerHTML = '';
        if (this.messages.length === 0) {
            historyDiv.innerHTML = '<div class="empty-history">暂无消息历史</div>';
            return;
        }
        this.messages.forEach((msg) => this.addMessageToHistory(msg));
    }

    deleteMessageLocally(msgId) {
        this.messages = this.messages.filter((msg) => msg.id !== msgId);
        const element = document.querySelector(`.message-item[data-msg-id="${CSS.escape(msgId)}"]`);
        if (element) element.remove();
        const latest = this.messages[this.messages.length - 1];
        if (latest) this.updateLatestMessage(latest);
        else document.getElementById('latestMessage').innerHTML = '<div class="message-placeholder">等待消息...</div>';
        const counter = document.getElementById('chatCount');
        const value = (parseInt(counter.textContent, 10) || 0) - 1;
        counter.textContent = Math.max(0, value);
    }

    async deleteMessageFromBackend(msgId) {
        try {
            await this.api(`/api/chat/message/${encodeURIComponent(msgId)}`, { method: 'DELETE' });
            this.deleteMessageLocally(msgId);
            this.showMessage('消息已删除', 'success');
        } catch (e) {
            this.showMessage(e.message || '删除失败', 'error');
        }
    }

    sendText() {
        const input = document.getElementById('sharedTextInput');
        const msg = input.value.trim();
        if (!msg) return;
        input.value = '';
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'chat_message', message: msg }));
        } else {
            this.api('/api/chat/send', { method: 'POST', json: { message: msg } })
                .then((data) => { if (data && data.message) this.addMessage(data.message, false); })
                .catch((e) => this.showMessage(e.message || '发送失败', 'error'));
        }
    }

    async copyToClipboard(text, quiet = false) {
        let copied = false;
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await Promise.race([
                    navigator.clipboard.writeText(text),
                    new Promise((_, reject) => setTimeout(() => reject(new Error('clipboard timeout')), 800)),
                ]);
                copied = true;
            } catch (e) {
                copied = false;
            }
        }
        if (!copied) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                copied = document.execCommand('copy');
            } catch (e) {
                copied = false;
            }
            document.body.removeChild(textarea);
        }
        if (!quiet) {
            if (copied) this.showMessage('已复制', 'success');
            else this.showMessage('复制失败，请手动复制', 'error');
        }
        return copied;
    }

    // --------------------------------------------------------------- files
    async loadFileList() {
        try {
            const data = await this.api('/api/files');
            this.allFiles.clear();
            (data.files || []).forEach((file) => this.allFiles.set(file.id, file));

            const uploadedDiv = document.getElementById('uploadedFilesList');
            const uploadedFiles = (data.files || []).filter((file) => !this.downloadedFileIds.has(file.id));
            const preservedUploads = [];
            uploadedDiv.querySelectorAll('.file-item').forEach((item) => {
                if (item.id && item.id.startsWith('upload-')) preservedUploads.push(item);
            });

            if (uploadedFiles.length === 0 && preservedUploads.length === 0) {
                uploadedDiv.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>暂无文件</p></div>';
            } else {
                uploadedDiv.innerHTML = '';
                preservedUploads.forEach((item) => uploadedDiv.appendChild(item));
                uploadedFiles.forEach((file) => this.addUploadedFileItem(file));
            }

            const downloadedDiv = document.getElementById('downloadedFilesList');
            const downloadedFiles = (data.files || []).filter((file) => this.downloadedFileIds.has(file.id));
            if (downloadedFiles.length === 0) {
                downloadedDiv.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>暂无已下载文件</p></div>';
            } else {
                downloadedDiv.innerHTML = '';
                downloadedFiles.forEach((file) => this.addDownloadedFileItem(file));
            }
            this.syncSelection(new Set(uploadedFiles.map((file) => file.id)));
            this.updateCheckboxLimits();
        } catch (e) {
            console.error('加载文件列表失败', e);
            this.showMessage(e.message || '加载文件列表失败', 'error');
        }
    }

    addUploadedFileItem(file) {
        const template = document.getElementById('fileItemTemplate');
        const clone = template.content.cloneNode(true);
        const item = clone.querySelector('.file-item');
        item.dataset.fileId = file.id;
        const checkbox = item.querySelector('.file-checkbox');
        checkbox.dataset.fileId = file.id;
        checkbox.checked = this.selectedFiles.has(file.id);
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) this.selectedFiles.add(file.id);
            else this.selectedFiles.delete(file.id);
            this.updateCheckboxLimits();
        });
        item.querySelector('.file-name').textContent = file.name;
        item.querySelector('.file-size').textContent = this.formatSize(file.size);
        item.querySelector('.file-date').textContent = new Date(file.modified * 1000).toLocaleString();
        item.querySelector('.download-count').innerHTML = `⬇️ ${file.download_count || 0}`;
        item.querySelector('.btn-download').addEventListener('click', () => this.downloadFile(file.id, item));
        item.querySelector('.btn-copy').addEventListener('click', () => this.copyLink(file.url));
        item.querySelector('.btn-delete').addEventListener('click', () => this.confirmDelete(file.id));
        document.getElementById('uploadedFilesList').appendChild(item);
    }

    addDownloadedFileItem(file) {
        const template = document.getElementById('downloadedItemTemplate');
        const clone = template.content.cloneNode(true);
        const item = clone.querySelector('.file-item');
        item.dataset.fileId = file.id;
        item.querySelector('.file-name').textContent = file.name;
        item.querySelector('.file-size').textContent = this.formatSize(file.size);
        item.querySelector('.file-date').textContent = new Date(file.modified * 1000).toLocaleString();
        item.querySelector('.download-count').innerHTML = `⬇️ ${file.download_count || 0}`;
        item.querySelector('.btn-redownload').addEventListener('click', () => this.downloadFile(file.id, item));
        item.querySelector('.btn-restore').addEventListener('click', () => this.restoreFileFromDownloaded(file.id));
        item.querySelector('.btn-delete').addEventListener('click', () => this.confirmDelete(file.id));
        document.getElementById('downloadedFilesList').appendChild(item);
    }

    syncSelection(validIds) {
        const valid = validIds || new Set(this.allFiles.keys());
        this.selectedFiles = new Set(Array.from(this.selectedFiles).filter((id) => valid.has(id)));
        document.querySelectorAll('.file-checkbox').forEach((checkbox) => {
            checkbox.checked = this.selectedFiles.has(checkbox.dataset.fileId);
        });
    }

    updateCheckboxLimits() {
        let totalSize = 0;
        for (const id of this.selectedFiles) {
            const file = this.allFiles.get(id);
            if (file) totalSize += file.size;
        }
        const overLimit = totalSize > FileTransferApp.ZIP_LIMIT;
        const hint = document.getElementById('zipLimitHint');
        document.querySelectorAll('.file-checkbox').forEach((checkbox) => {
            checkbox.disabled = overLimit && !checkbox.checked;
        });
        if (overLimit) {
            hint.textContent = '已超20GB限制，请取消部分文件';
            hint.style.color = '#f44336';
        } else {
            hint.textContent = `限20GB以内 (当前${this.formatSize(totalSize)})`;
            hint.style.color = '';
        }
    }

    toggleSelectAll() {
        const checkboxes = document.querySelectorAll('.file-checkbox:not(:disabled)');
        const allChecked = checkboxes.length > 0 && Array.from(checkboxes).every((cb) => cb.checked);
        checkboxes.forEach((checkbox) => {
            checkbox.checked = !allChecked;
            if (allChecked) this.selectedFiles.delete(checkbox.dataset.fileId);
            else this.selectedFiles.add(checkbox.dataset.fileId);
        });
        this.updateCheckboxLimits();
    }

    copyLink(url) {
        const absolute = new URL(url, window.location.origin).href;
        this.copyToClipboard(absolute);
    }

    // ------------------------------------------------------------ download
    //
    // Downloads are intentionally handed to the browser's native download
    // manager.  Fetching first and then clicking a blob URL is an *automatic*
    // download from Chrome's point of view (user activation is gone after the
    // await), so downloading more than one small file triggers Chrome's
    // "download multiple files" permission prompt.  A direct anchor click is
    // user-initiated, works for any size and lets the browser resume on its
    // own.  Progress and speed are shown in the browser's download bubble.
    downloadFile(fileId) {
        const file = this.allFiles.get(fileId);
        if (!file) return;
        const isLarge = file.size >= FileTransferApp.LARGE_DOWNLOAD_NOTICE;
        this.nativeDownload(file, isLarge);
        if (isLarge) this.showLargeDownloadNotice(file);
    }

    nativeDownload(file, silent = false) {
        const anchor = document.createElement('a');
        anchor.href = file.url;
        anchor.download = file.name;
        anchor.rel = 'noopener';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        this.markDownloaded(file.id);
        if (!silent) {
            this.showMessage(`已开始下载：${file.name}（进度见浏览器下载栏）`, 'success');
        }
        setTimeout(() => this.loadFileList(), 1500);
    }

    getDownloadsInfo() {
        const ua = navigator.userAgent || '';
        if (/Edg\//.test(ua)) {
            return { browser: 'Edge', downloads: 'edge://downloads/', newTab: 'edge://newtab/' };
        }
        if (/Firefox\//.test(ua)) {
            return { browser: 'Firefox', downloads: 'about:downloads', newTab: 'about:newtab' };
        }
        return { browser: 'Chrome', downloads: 'chrome://downloads/', newTab: 'chrome://newtab/' };
    }

    showLargeDownloadNotice(file) {
        const modal = document.getElementById('largeDownloadModal');
        if (!modal) return;
        document.getElementById('largeDownloadName').textContent = file.name;
        document.getElementById('largeDownloadSize').textContent = this.formatSize(file.size);
        const info = this.getDownloadsInfo();
        document.getElementById('downloadsUrlLabel').textContent = info.downloads;
        document.getElementById('largeDownloadCountdown').textContent = FileTransferApp.LARGE_NOTICE_SECONDS;
        modal.style.display = 'flex';
        if (this._largeNoticeInterval) clearInterval(this._largeNoticeInterval);
        this._largeNoticeInterval = setInterval(() => {
            const label = document.getElementById('largeDownloadCountdown');
            const remaining = Math.max(0, (parseInt(label.textContent, 10) || 0) - 1);
            label.textContent = remaining;
            if (remaining <= 0) this.closeLargeDownloadNotice();
        }, 1000);
    }

    closeLargeDownloadNotice() {
        if (this._largeNoticeInterval) {
            clearInterval(this._largeNoticeInterval);
            this._largeNoticeInterval = null;
        }
        const modal = document.getElementById('largeDownloadModal');
        if (modal) modal.style.display = 'none';
    }

    async openDownloads() {
        const info = this.getDownloadsInfo();
        let opened = false;
        try {
            opened = Boolean(window.open(info.downloads, '_blank'));
        } catch (e) {
            opened = false;
        }
        const copied = await this.copyToClipboard(info.downloads, true);
        if (opened) {
            this.showMessage(`已尝试打开 ${info.downloads}；若无反应，请按 Ctrl+J`, 'info');
        } else if (copied) {
            this.showMessage(`浏览器不允许网页直接打开 ${info.downloads}，已复制；请按 Ctrl+J 或粘贴到地址栏`, 'info');
        } else {
            this.showMessage(`请按 Ctrl+J 打开下载列表，或手动复制 ${info.downloads}`, 'info');
        }
    }

    restoreFileFromDownloaded(fileId) {
        this.downloadedFileIds.delete(fileId);
        this.saveDownloadedRecords();
        this.loadFileList();
        this.showMessage('已移回已上传列表', 'success');
    }

    confirmDelete(fileId) {
        this.showConfirm('确定要删除该文件吗？删除后不可恢复。', async () => {
            try {
                await this.api(`/api/delete/${encodeURIComponent(fileId)}`, { method: 'DELETE' });
                this.downloadedFileIds.delete(fileId);
                this.selectedFiles.delete(fileId);
                this.saveDownloadedRecords();
                this.showMessage('文件已删除', 'success');
                this.loadFileList();
            } catch (e) {
                this.showMessage(e.message || '删除失败', 'error');
            }
        });
    }

    async batchDelete() {
        if (this.selectedFiles.size === 0) {
            this.showMessage('请至少选择一个文件', 'info');
            return;
        }
        this.showConfirm(`确定要删除选中的 ${this.selectedFiles.size} 个文件吗？`, async () => {
            const names = Array.from(this.selectedFiles)
                .map((id) => this.allFiles.get(id))
                .filter(Boolean)
                .map((file) => file.name);
            try {
                const result = await this.api('/api/batch-delete', { method: 'POST', json: { files: names } });
                const failed = (result && result.failed) || [];
                if (failed.length) {
                    this.showMessage(`已删除 ${(result.deleted || []).length} 个，失败 ${failed.length} 个`, 'error');
                } else {
                    this.showMessage('批量删除成功', 'success');
                }
                names.forEach((name) => this.downloadedFileIds.delete(name));
                this.selectedFiles.clear();
                this.saveDownloadedRecords();
                this.loadFileList();
            } catch (e) {
                this.showMessage(e.message || '批量删除失败', 'error');
            }
        });
    }

    downloadZip() {
        if (this.selectedFiles.size === 0) {
            this.showMessage('请至少选择一个文件', 'info');
            return;
        }
        const files = Array.from(this.selectedFiles)
            .map((id) => this.allFiles.get(id))
            .filter(Boolean);
        const totalSize = files.reduce((sum, file) => sum + file.size, 0);
        if (totalSize > FileTransferApp.ZIP_LIMIT) {
            this.showMessage('所选文件总大小超过20GB，无法打包', 'error');
            return;
        }
        if (!this._zipFrame) {
            const frame = document.createElement('iframe');
            frame.name = 'zipFrame';
            frame.id = 'zipFrame';
            frame.title = '打包下载';
            frame.src = '/client/zip-frame.html';
            frame.style.display = 'none';
            document.body.appendChild(frame);
            this._zipFrame = frame;
        }
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/api/zip-download';
        form.target = 'zipFrame';
        form.style.display = 'none';
        files.forEach((file) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'files';
            input.value = file.name;
            form.appendChild(input);
        });
        document.body.appendChild(form);
        form.submit();
        form.remove();
        this.showMessage('已开始打包，浏览器将自动保存 ZIP', 'success');
    }

    clearDownloadedRecords() {
        this.showConfirm('清空已下载记录不会删除实际文件，确定清空？', () => {
            this.downloadedFileIds.clear();
            this.saveDownloadedRecords();
            this.selectedFiles.clear();
            this.loadFileList();
            this.showMessage('已清空下载记录', 'success');
        });
    }

    // -------------------------------------------------------------- upload
    setupEventListeners() {
        const zone = document.getElementById('uploadZone');
        const fileInput = document.getElementById('fileInput');
        const refreshBtn = document.getElementById('refreshBtn');
        const sendBtn = document.getElementById('sharedTextSendBtn');
        const textInput = document.getElementById('sharedTextInput');
        const toggleHistoryBtn = document.getElementById('toggleHistory');
        const clearDownloadedBtn = document.getElementById('clearDownloadedBtn');
        const toggleSelectBtn = document.getElementById('toggleSelectBtn');
        const downloadZipBtn = document.getElementById('downloadZipBtn');
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');

        zone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (event) => {
            this.handleFileSelect(event.target.files);
            event.target.value = '';
        });
        zone.addEventListener('dragover', (event) => {
            event.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', (event) => {
            event.preventDefault();
            zone.classList.remove('dragover');
            if (event.dataTransfer.files.length) this.handleFileSelect(event.dataTransfer.files);
        });
        refreshBtn.addEventListener('click', () => this.loadFileList());
        sendBtn.addEventListener('click', () => this.sendText());
        textInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.sendText();
            }
        });
        toggleHistoryBtn.addEventListener('click', () => {
            const content = document.getElementById('historyContent');
            const button = document.getElementById('toggleHistory');
            this.isHistoryVisible = !this.isHistoryVisible;
            if (this.isHistoryVisible) {
                content.classList.add('active');
                button.classList.add('active');
                button.innerHTML = '<i class="fas fa-chevron-up"></i>';
                this.refreshHistoryList();
            } else {
                content.classList.remove('active');
                button.classList.remove('active');
                button.innerHTML = '<i class="fas fa-chevron-down"></i>';
            }
        });
        clearDownloadedBtn.addEventListener('click', () => this.clearDownloadedRecords());
        toggleSelectBtn.addEventListener('click', () => this.toggleSelectAll());
        downloadZipBtn.addEventListener('click', () => this.downloadZip());
        batchDeleteBtn.addEventListener('click', () => this.batchDelete());
        document.getElementById('closeLargeDownloadBtn').addEventListener('click', () => this.closeLargeDownloadNotice());
        document.getElementById('openDownloadsBtn').addEventListener('click', () => this.openDownloads());
        document.getElementById('copyDownloadsUrlBtn').addEventListener('click', () => this.copyToClipboard(this.getDownloadsInfo().downloads));
        window.addEventListener('beforeunload', (event) => {
            if (this.uploads.size > 0) {
                event.preventDefault();
                event.returnValue = '';
            }
        });
    }

    async handleFileSelect(files) {
        const queue = Array.from(files);
        const workers = [];
        const workerCount = Math.min(FileTransferApp.MAX_CONCURRENT_UPLOADS, queue.length);
        for (let i = 0; i < workerCount; i++) {
            workers.push(this._uploadWorker(queue));
        }
        await Promise.all(workers);
    }

    async _uploadWorker(queue) {
        while (queue.length > 0) {
            const file = queue.shift();
            if (file) await this.uploadFile(file);
        }
    }

    async uploadFile(file) {
        const taskId = `upload_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const upload = {
            id: taskId,
            file,
            offset: 0,
            initialOffset: 0,
            chunkLoaded: 0,
            startTime: Date.now(),
            speed: 0,
            sessionId: null,
            xhr: null,
            cancelled: false,
        };
        this.uploads.set(taskId, upload);
        this.addUploadUI(taskId, file);
        try {
            const init = await this.api('/api/upload/init', {
                method: 'POST',
                json: {
                    filename: file.name,
                    size: file.size,
                    mtime: file.lastModified || 0,
                    nonce: this._uploadNonce,
                },
            });
            upload.sessionId = init.upload_id;
            upload.offset = init.offset || 0;
            upload.initialOffset = upload.offset;
            upload.startTime = Date.now();
            if (upload.offset > 0) {
                this.showMessage(`继续上传 ${file.name}（已完成 ${this.formatSize(upload.offset)}）`, 'info');
            }
            this.updateUploadProgress(upload);
            while (upload.offset < file.size) {
                if (upload.cancelled) return;
                const start = upload.offset;
                const end = Math.min(start + FileTransferApp.CHUNK_SIZE, file.size);
                let attempt = 0;
                let progressed = false;
                while (!progressed) {
                    if (upload.cancelled) return;
                    try {
                        const next = await this.putChunk(upload, file.slice(start, end), start);
                        upload.offset = next;
                        upload.chunkLoaded = 0;
                        progressed = true;
                    } catch (err) {
                        if (upload.cancelled) return;
                        if (err.status === 409 && err.data && typeof err.data.offset === 'number') {
                            upload.offset = err.data.offset;
                            upload.chunkLoaded = 0;
                            progressed = true;
                            break;
                        }
                        attempt += 1;
                        if (attempt >= 3) throw err;
                        await new Promise((resolve) => setTimeout(resolve, 800 * attempt));
                    }
                }
                this.updateUploadProgress(upload);
            }
            const done = await this.api(`/api/upload/complete/${upload.sessionId}`, { method: 'POST' });
            this.showMessage(`文件 ${done.filename || file.name} 上传成功`, 'success');
            await this.loadFileList();
        } catch (err) {
            if (!upload.cancelled) {
                this.showMessage(`文件 ${file.name} 上传失败: ${err.message}`, 'error');
            }
        } finally {
            this.uploads.delete(taskId);
            const item = document.getElementById(`upload-${taskId}`);
            if (item) item.remove();
            this.refreshGlobalUploadStats();
        }
    }

    putChunk(upload, blob, offset) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            upload.xhr = xhr;
            xhr.open('PUT', `/api/upload/chunk/${upload.sessionId}?offset=${offset}`);
            xhr.setRequestHeader('Content-Type', 'application/octet-stream');
            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    upload.chunkLoaded = event.loaded;
                    this.updateUploadProgress(upload);
                }
            };
            xhr.onload = () => {
                upload.xhr = null;
                let data = null;
                try {
                    data = JSON.parse(xhr.responseText);
                } catch (e) { /* empty body */ }
                if (xhr.status === 200) {
                    resolve(data ? data.offset : offset + blob.size);
                } else {
                    const error = new Error((data && data.error) || `HTTP ${xhr.status}`);
                    error.status = xhr.status;
                    error.data = data;
                    reject(error);
                }
            };
            xhr.onerror = () => {
                upload.xhr = null;
                const error = new Error('网络错误');
                error.status = 0;
                reject(error);
            };
            xhr.onabort = () => {
                upload.xhr = null;
                const error = new Error('上传已取消');
                error.name = 'AbortError';
                reject(error);
            };
            xhr.send(blob);
        });
    }

    addUploadUI(taskId, file) {
        const listDiv = document.getElementById('uploadedFilesList');
        const empty = listDiv.querySelector('.empty-state');
        if (empty) empty.remove();
        const item = document.createElement('div');
        item.className = 'file-item';
        item.id = `upload-${taskId}`;
        item.innerHTML = `
            <div class="file-icon"><i class="fas fa-file"></i></div>
            <div class="file-info">
                <div class="file-name">${this.escapeHtml(file.name)}</div>
                <div class="file-meta"><span class="file-size">${this.formatSize(file.size)}</span><span class="file-date">上传中...</span></div>
                <div class="file-progress"><div class="progress-bar"><div class="progress-fill"></div></div><span class="progress-text">0%</span><span class="progress-size"></span></div>
                <div class="transfer-info"><span class="transfer-speed"></span><span class="transfer-time"></span></div>
            </div>
            <div class="file-actions"><button class="btn-action btn-cancel" title="取消上传"><i class="fas fa-times"></i></button></div>
        `;
        item.querySelector('.btn-cancel').addEventListener('click', async () => {
            const upload = this.uploads.get(taskId);
            if (!upload) return;
            upload.cancelled = true;
            if (upload.xhr) upload.xhr.abort();
            if (upload.sessionId) {
                try {
                    await this.api(`/api/upload/${upload.sessionId}`, { method: 'DELETE' });
                } catch (e) { /* session may already be gone */ }
            }
            this.uploads.delete(taskId);
            item.remove();
            this.refreshGlobalUploadStats();
            this.showMessage('上传已取消', 'info');
        });
        listDiv.prepend(item);
    }

    updateUploadProgress(upload) {
        const item = document.getElementById(`upload-${upload.id}`);
        if (!item) return;
        const total = upload.file.size;
        const loaded = Math.min(upload.offset + (upload.chunkLoaded || 0), total);
        const percent = total > 0 ? (loaded / total) * 100 : 100;
        item.querySelector('.progress-fill').style.width = `${percent}%`;
        item.querySelector('.progress-text').textContent = `${percent.toFixed(1)}%`;
        const size = item.querySelector('.progress-size');
        if (size) size.textContent = `${this.formatSize(loaded)} / ${this.formatSize(total)}`;
        const elapsed = (Date.now() - upload.startTime) / 1000;
        const transferred = Math.max(0, loaded - upload.initialOffset);
        const speed = elapsed > 0 ? transferred / elapsed : 0;
        upload.speed = speed;
        item.querySelector('.transfer-speed').textContent = this.formatSpeed(speed);
        const elapsedStr = this.formatTime(elapsed);
        if (speed > 0) {
            const remaining = (total - loaded) / speed;
            item.querySelector('.transfer-time').textContent = `${this.formatTime(remaining)} / ${elapsedStr}`;
        } else {
            item.querySelector('.transfer-time').textContent = `--s / ${elapsedStr}`;
        }
        this.refreshGlobalUploadStats();
    }

    refreshGlobalUploadStats() {
        let speed = 0;
        let remaining = 0;
        let active = 0;
        for (const upload of this.uploads.values()) {
            if (upload.speed > 0) {
                speed += upload.speed;
                remaining += Math.max(0, (upload.file.size - upload.offset) / upload.speed);
                active += 1;
            }
        }
        document.getElementById('uploadSpeed').textContent = this.formatSpeed(speed);
        document.getElementById('uploadTime').textContent = active ? this.formatTime(remaining / active) : '0s';
    }

    // --------------------------------------------------------- auto shutdown
    async initAutoShutdown() {
        const toggle = document.getElementById('autoShutdownToggle');
        const extendBtn = document.getElementById('extendShutdownBtn');
        toggle.checked = true;
        try {
            const data = await this.api('/api/auto-shutdown/status');
            this.applyShutdownStatus(data);
        } catch (e) {
            console.error(e);
        }
        toggle.addEventListener('change', () => {
            if (!toggle.checked) this.confirmServerShutdown(toggle);
        });
        extendBtn.addEventListener('click', () => this.extendShutdown());
    }

    applyShutdownStatus(data) {
        const toggle = document.getElementById('autoShutdownToggle');
        if (!this.serverShuttingDown) toggle.checked = !!data.enabled;
        this.autoShutdownEnabled = !!data.enabled;
        if (data.enabled) {
            this.startCountdown(data.remain_seconds);
        } else {
            if (this.countdownInterval) clearInterval(this.countdownInterval);
            this.countdownInterval = null;
            document.getElementById('countdownDisplay').textContent = '未开启';
        }
    }

    async extendShutdown() {
        const button = document.getElementById('extendShutdownBtn');
        button.disabled = true;
        try {
            const data = await this.api('/api/auto-shutdown/extend', {
                method: 'POST',
                json: { hours: 3 },
            });
            this.applyShutdownStatus(data);
            const addedHours = Math.round((data.added_seconds || 0) / 3600);
            const maxHours = Math.max(1, Math.round((data.max_seconds || 0) / 3600));
            let message;
            if (data.capped) {
                message = addedHours > 0 ? `已达到 ${maxHours} 小时上限（本次延长 ${addedHours} 小时）` : `已达到 ${maxHours} 小时上限`;
            } else {
                message = `已延长 ${addedHours || 3} 小时`;
            }
            this.showMessage(message, data.capped ? 'info' : 'success');
        } catch (e) {
            this.showMessage(e.message || '延长自动关闭失败', 'error');
        } finally {
            button.disabled = false;
        }
    }

    confirmServerShutdown(toggle) {
        this.showConfirm(
            '关闭服务器会停止后端服务，并断开所有用户。确定要关闭吗？',
            () => this.requestShutdown(toggle),
            () => { toggle.checked = true; }
        );
    }

    async requestShutdown(toggle) {
        try {
            await this.api('/api/shutdown', {
                method: 'POST',
                json: { confirm: true, force: false },
            });
            this.handleServerShutdown('manual');
        } catch (e) {
            if (e.status === 409 && e.data && e.data.active_downloads) {
                const count = e.data.active_downloads;
                this.showConfirm(
                    `当前有 ${count} 个文件正在下载，关闭服务器会中断下载。仍要关闭吗？`,
                    async () => {
                        try {
                            await this.api('/api/shutdown', {
                                method: 'POST',
                                json: { confirm: true, force: true },
                            });
                            this.handleServerShutdown('manual');
                        } catch (err) {
                            toggle.checked = true;
                            this.showMessage(err.message || '关闭服务器失败', 'error');
                        }
                    },
                    () => { toggle.checked = true; }
                );
                return;
            }
            toggle.checked = true;
            this.showMessage(e.message || '关闭服务器失败', 'error');
        }
    }

    handleServerShutdown(reason) {
        if (this.serverShuttingDown) return;
        this.serverShuttingDown = true;
        this.closeLargeDownloadNotice();
        if (this.countdownInterval) {
            clearInterval(this.countdownInterval);
            this.countdownInterval = null;
        }
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        const toggle = document.getElementById('autoShutdownToggle');
        const extendBtn = document.getElementById('extendShutdownBtn');
        if (toggle) toggle.disabled = true;
        if (extendBtn) extendBtn.disabled = true;
        if (this.ws) {
            try {
                this.ws.onclose = null;
                this.ws.close();
            } catch (e) { /* ignore */ }
            this.ws = null;
        }
        const overlay = document.getElementById('serverClosedOverlay');
        const reasonLabel = document.getElementById('serverClosedReason');
        if (reasonLabel) {
            reasonLabel.textContent = reason === 'auto-shutdown'
                ? '自动关闭时间已到。'
                : '服务器已被关闭。';
        }
        if (overlay) overlay.style.display = 'flex';
        setTimeout(() => this.leavePage(), 1800);
    }

    leavePage() {
        try {
            window.close();
        } catch (e) { /* browsers only allow closing script-opened tabs */ }
        setTimeout(() => {
            let newTab = 'about:blank';
            try {
                newTab = this.getDownloadsInfo().newTab;
                window.location.replace(newTab);
            } catch (e) { /* chrome:// navigation from a web page is blocked */ }
            setTimeout(() => {
                try {
                    window.location.replace('about:blank');
                } catch (e) { /* ignore */ }
            }, 300);
        }, 250);
    }

    async syncAutoShutdownStatus() {
        if (this.serverShuttingDown) return;
        try {
            const data = await this.api('/api/auto-shutdown/status');
            this.applyShutdownStatus(data);
        } catch (e) { /* ignore transient errors */ }
    }

    startCountdown(seconds) {
        if (this.countdownInterval) clearInterval(this.countdownInterval);
        const display = document.getElementById('countdownDisplay');
        let remaining = Math.max(0, Number(seconds) || 0);
        const update = () => {
            if (remaining <= 0) {
                clearInterval(this.countdownInterval);
                this.countdownInterval = null;
                display.textContent = '已到期';
                return;
            }
            const hours = Math.floor(remaining / 3600);
            const minutes = Math.floor((remaining % 3600) / 60);
            const secs = remaining % 60;
            display.textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            remaining -= 1;
        };
        update();
        this.countdownInterval = setInterval(update, 1000);
    }

    // -------------------------------------------------------------- dialogs
    showConfirm(message, onConfirm, onCancel) {
        const modal = document.getElementById('customConfirm');
        document.getElementById('confirmMessage').textContent = message;
        modal.style.display = 'flex';
        const yesBtn = document.getElementById('confirmYes');
        const noBtn = document.getElementById('confirmNo');
        noBtn.focus();
        const onKeydown = (event) => {
            const inside = modal.contains(document.activeElement);
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                yesBtn.focus();
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                noBtn.focus();
            } else if (event.key === 'Enter' && inside) {
                event.preventDefault();
                document.activeElement.click();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                cancel();
            }
        };
        const close = () => {
            modal.style.display = 'none';
            document.removeEventListener('keydown', onKeydown);
            yesBtn.removeEventListener('click', onYes);
            noBtn.removeEventListener('click', cancel);
        };
        const cancel = () => {
            close();
            if (onCancel) {
                try {
                    onCancel();
                } catch (e) {
                    console.error(e);
                }
            }
        };
        const onYes = () => {
            close();
            try {
                onConfirm();
            } catch (e) {
                console.error(e);
            }
        };
        yesBtn.addEventListener('click', onYes);
        noBtn.addEventListener('click', cancel);
        document.addEventListener('keydown', onKeydown);
    }

    // --------------------------------------------------------------- helpers
    formatSize(bytes) {
        if (!bytes || bytes <= 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        return `${parseFloat((bytes / Math.pow(1024, index)).toFixed(1))} ${units[index]}`;
    }

    formatSpeed(bytesPerSecond) {
        if (!bytesPerSecond || bytesPerSecond <= 0) return '0 B/s';
        if (bytesPerSecond < 1024) return `${bytesPerSecond.toFixed(0)} B/s`;
        if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`;
        if (bytesPerSecond < 1024 * 1024 * 1024) return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`;
        return `${(bytesPerSecond / (1024 * 1024 * 1024)).toFixed(2)} GB/s`;
    }

    formatTime(seconds) {
        if (!isFinite(seconds) || seconds <= 0) return '--s';
        if (seconds < 60) return `${seconds.toFixed(0)}s`;
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (minutes < 60) return `${minutes}m${secs}s`;
        const hours = Math.floor(minutes / 60);
        return `${hours}h${minutes % 60}m`;
    }

    escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    showMessage(message, type) {
        const element = document.createElement('div');
        element.className = 'message-notification';
        element.textContent = message;
        element.style.background = type === 'error' ? '#f44336' : (type === 'info' ? '#2196F3' : '#4CAF50');
        document.body.appendChild(element);
        setTimeout(() => {
            element.style.animation = 'slideOut 0.3s forwards';
            setTimeout(() => element.remove(), 300);
        }, 3000);
    }

    startAutoRefresh() {
        setInterval(() => {
            if (this.uploads.size === 0) {
                this.loadFileList();
            }
            this.loadRoomInfo();
        }, 30000);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new FileTransferApp();
});
