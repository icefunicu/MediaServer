const API_BASE = '';
const APP_VERSION = '20260227-6';

let currentPath = '/';
let currentFiles = [];
let currentViewer = null;
let currentComic = null;
let currentArchive = null;
let totalComicPages = 0;
let comicReaderState = null;

const READER_SETTINGS_KEY = 'comic_reader_settings_v1';

function loadReaderSettings() {
    try {
        const raw = localStorage.getItem(READER_SETTINGS_KEY);
        if (!raw) {
            return { scale: 100, gap: 16, immersive: false };
        }
        const parsed = JSON.parse(raw);
        return {
            scale: Math.min(130, Math.max(78, Number(parsed.scale) || 100)),
            gap: Math.min(28, Math.max(8, Number(parsed.gap) || 16)),
            immersive: Boolean(parsed.immersive),
        };
    } catch (error) {
        return { scale: 100, gap: 16, immersive: false };
    }
}

function saveReaderSettings(settings) {
    try {
        localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify(settings));
    } catch (error) {
        // Ignore storage failures in private mode.
    }
}

function getReaderProgressKey(path) {
    return `comic_reader_progress_${encodeURIComponent(path)}`;
}

function loadReaderProgress(path) {
    try {
        const raw = localStorage.getItem(getReaderProgressKey(path));
        if (!raw) {
            return { page: 1 };
        }
        const parsed = JSON.parse(raw);
        return { page: Math.max(1, Number(parsed.page) || 1) };
    } catch (error) {
        return { page: 1 };
    }
}

function saveReaderProgress(path, page) {
    try {
        localStorage.setItem(getReaderProgressKey(path), JSON.stringify({ page }));
    } catch (error) {
        // Ignore storage failures in private mode.
    }
}

function applyReaderImmersiveMode(enabled) {
    document.body.classList.toggle('reader-immersive', Boolean(enabled));
}

function cleanupComicReaderState() {
    if (comicReaderState?.persistTimer) {
        window.clearTimeout(comicReaderState.persistTimer);
    }
    if (comicReaderState?.rafId) {
        window.cancelAnimationFrame(comicReaderState.rafId);
    }
    if (comicReaderState?.observer) {
        comicReaderState.observer.disconnect();
    }
    if (comicReaderState?.scrollHandler && comicReaderState?.scrollRoot) {
        comicReaderState.scrollRoot.removeEventListener('scroll', comicReaderState.scrollHandler);
    }
    if (comicReaderState?.keyHandler) {
        window.removeEventListener('keydown', comicReaderState.keyHandler);
    }
    comicReaderState = null;
}

function detectIOSFamily() {
    const ua = navigator.userAgent || '';
    const platform = navigator.platform || '';
    const isIOSUA = /iPad|iPhone|iPod/i.test(ua);
    const isIPadOS = platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return isIOSUA || isIPadOS;
}

const IOS_FAMILY = detectIOSFamily();
const IOS_NATIVE_VIDEO_CONTAINERS = new Set(['.mp4', '.m4v', '.mov']);

function buildVideoStreamUrl(path, forceIOSCompat = false) {
    const query = new URLSearchParams();
    query.set('path', path);
    if (forceIOSCompat) {
        query.set('ios_compat', '1');
    }
    return `${API_BASE}/api/video/stream?${query.toString()}`;
}

function buildComicPageUrl(path, pageNum) {
    const query = new URLSearchParams();
    query.set('path', path);
    query.set('page', String(pageNum));

    const dpr = window.devicePixelRatio || 1;
    const viewport = Math.max(window.innerWidth || 1280, 640);
    if (IOS_FAMILY) {
        const maxWidth = Math.min(2560, Math.max(1280, Math.round(viewport * dpr * 1.15)));
        query.set('max_width', String(maxWidth));
        query.set('quality', '82');
        query.set('format', 'jpeg');
    } else {
        const maxWidth = Math.min(2880, Math.max(1440, Math.round(viewport * dpr * 1.2)));
        query.set('max_width', String(maxWidth));
        query.set('quality', '86');
    }

    return `${API_BASE}/api/comic/page?${query.toString()}`;
}

function buildComicFallbackPageUrl(path, pageNum) {
    const query = new URLSearchParams();
    query.set('path', path);
    query.set('page', String(pageNum));

    const dpr = window.devicePixelRatio || 1;
    const viewport = Math.max(window.innerWidth || 1280, 640);
    const maxWidth = IOS_FAMILY
        ? Math.min(2560, Math.max(1280, Math.round(viewport * dpr * 1.15)))
        : Math.min(2880, Math.max(1440, Math.round(viewport * dpr * 1.2)));
    query.set('max_width', String(maxWidth));
    query.set('quality', '82');
    query.set('format', 'png');

    return `${API_BASE}/api/comic/page?${query.toString()}`;
}

async function fetchAPI(url) {
    try {
        const response = await fetch(url);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '请求失败');
        }
        return await response.json();
    } catch (error) {
        showError(error.message);
        throw error;
    }
}

function showLoading() {
    const overlay = document.getElementById('loadingOverlay');
    const message = overlay.querySelector('p');
    message.textContent = '加载中...';
    overlay.classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

function showError(message) {
    const errorToast = document.getElementById('errorToast');
    document.getElementById('errorMessage').textContent = message;
    errorToast.classList.remove('hidden');
    setTimeout(() => closeError(), 5000);
}

function closeError() {
    document.getElementById('errorToast').classList.add('hidden');
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
}

function getFileIcon(file) {
    if (file.is_directory) return '📁';
    switch (file.type) {
        case 'video': return '🎬';
        case 'comic': return '📚';
        case 'archive': return '🗜️';
        default: return '📄';
    }
}

function getFileTypeClass(file) {
    if (file.is_directory) return 'file-type-folder';
    return `file-type-${file.type}`;
}

function updateBreadcrumb(path) {
    const breadcrumb = document.getElementById('breadcrumb');
    const parts = path.split('/').filter(p => p);
    breadcrumb.innerHTML = '';

    const rootNode = document.createElement('span');
    rootNode.className = 'breadcrumb-item';
    rootNode.textContent = '根目录';
    rootNode.addEventListener('click', goHome);
    breadcrumb.appendChild(rootNode);

    let currentBuild = '';
    for (const part of parts) {
        currentBuild += '/' + part;
        const node = document.createElement('span');
        node.className = 'breadcrumb-item';
        node.textContent = part;
        const targetPath = currentBuild;
        node.addEventListener('click', () => navigateTo(targetPath));
        breadcrumb.appendChild(node);
    }
}

function renderFileList(files) {
    const fileList = document.getElementById('fileList');
    
    if (files.length === 0) {
        fileList.innerHTML = '<div class="empty-state"><p>📂 目录为空</p></div>';
        return;
    }

    const sortedFiles = [...files].sort((a, b) => {
        if (a.is_directory && !b.is_directory) return -1;
        if (!a.is_directory && b.is_directory) return 1;
        return a.name.localeCompare(b.name, 'zh-CN');
    });

    fileList.innerHTML = sortedFiles.map((file, index) => `
        <div class="file-item" data-index="${index}">
            <div class="file-icon">${getFileIcon(file)}</div>
            <div class="file-name">${escapeHtml(file.name)}</div>
            <div class="file-info ${getFileTypeClass(file)}">${file.is_directory ? '文件夹' : formatSize(file.size)}</div>
        </div>
    `).join('');

    fileList.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', () => {
            const index = Number(item.dataset.index);
            const file = sortedFiles[index];
            if (!file) return;

            if (file.is_directory) {
                navigateTo(`${currentPath}/${file.name}`.replace('//', '/'));
            } else {
                openFile(file.path);
            }
        });
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadDirectory(path) {
    showLoading();
    try {
        const data = await fetchAPI(`${API_BASE}/api/files?path=${encodeURIComponent(path)}`);
        currentPath = path;
        currentFiles = data.files;
        updateBreadcrumb(path);
        renderFileList(data.files);
        closeViewer();
    } catch (error) {
        console.error('加载目录失败:', error);
    } finally {
        hideLoading();
    }
}

function navigateTo(path) {
    loadDirectory(path);
}

function goHome() {
    loadDirectory('/');
}

async function searchFiles() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;

    showLoading();
    try {
        const data = await fetchAPI(`${API_BASE}/api/files/search?query=${encodeURIComponent(query)}`);
        currentPath = '/search';
        currentFiles = data.files;
        updateBreadcrumb('/search');
        document.getElementById('breadcrumb').innerHTML = '<span class="breadcrumb-item">搜索结果</span>';
        renderFileList(data.files);
        closeViewer();
    } catch (error) {
        console.error('搜索失败:', error);
    } finally {
        hideLoading();
    }
}

function handleSearch(event) {
    if (event.key === 'Enter') {
        searchFiles();
    }
}

async function openFile(path) {
    const file = currentFiles.find(f => f.path === path);
    if (!file) return;

    switch (file.type) {
        case 'video':
            openVideoPlayer(path, file.name);
            break;
        case 'comic':
            if (file.extension === '.zip' || file.extension === '.7z') {
                try {
                    const metadata = await fetchAPI(`${API_BASE}/api/comic/metadata?path=${encodeURIComponent(path)}`);
                    if (metadata.page_count > 0) {
                        openComicReader(path, file.name, metadata);
                    } else {
                        openArchiveBrowser(path, file.name);
                    }
                } catch (error) {
                    openArchiveBrowser(path, file.name);
                }
            } else {
                openComicReader(path, file.name);
            }
            break;
        case 'archive':
            openArchiveBrowser(path, file.name);
            break;
        default:
            showError('不支持的文件类型');
    }
}

function openVideoPlayer(path, name) {
    currentViewer = 'video';
    const viewer = document.getElementById('mediaViewer');
    const viewerContent = document.getElementById('viewerContent');
    const viewerTitle = document.getElementById('viewerTitle');
    const fileBrowser = document.getElementById('fileBrowser');

    cleanupComicReaderState();
    applyReaderImmersiveMode(false);
    viewer.classList.remove('comic-mode');
    viewerContent.classList.remove('comic-content');

    const lowerName = (name || '').toLowerCase();
    const ext = lowerName.includes('.') ? lowerName.slice(lowerName.lastIndexOf('.')) : '';
    const startWithIOSCompat = IOS_FAMILY && ext && !IOS_NATIVE_VIDEO_CONTAINERS.has(ext);
    const iosHint = startWithIOSCompat
        ? '<p style="color: var(--warning-color); text-align: center; margin-bottom: 0.75rem;">已为 iOS 自动启用兼容播放模式，首次加载可能稍慢。</p>'
        : '';
    const autoplayAttr = IOS_FAMILY ? '' : 'autoplay';
    const streamUrl = buildVideoStreamUrl(path, startWithIOSCompat);

    viewerTitle.textContent = name;
    viewerContent.innerHTML = `
        ${iosHint}
        <video id="activeVideoPlayer" class="video-player" controls playsinline webkit-playsinline x-webkit-airplay="allow" preload="metadata" ${autoplayAttr} src="${streamUrl}">
            您的浏览器不支持视频播放
        </video>
    `;

    fileBrowser.classList.add('hidden');
    viewer.classList.remove('hidden');

    const video = document.getElementById('activeVideoPlayer');
    if (!video) {
        return;
    }

    let fallbackTried = startWithIOSCompat;
    video.addEventListener('error', () => {
        if (!IOS_FAMILY) {
            showError('视频播放失败，请检查文件或网络。');
            return;
        }

        if (fallbackTried) {
            showError('当前视频在 iOS 上无法播放，请确认已安装 FFmpeg 并重试。');
            return;
        }

        fallbackTried = true;
        video.src = buildVideoStreamUrl(path, true);
        video.load();
        const playPromise = video.play();
        if (playPromise && typeof playPromise.catch === 'function') {
            playPromise.catch(() => {
                // iOS may block autoplay after source switch; user can tap play.
            });
        }
        showError('检测到 iOS 兼容性问题，已自动切换兼容流。');
    });
}

async function openComicReader(path, name, prefetchedMetadata = null) {
    currentViewer = 'comic';
    currentComic = path;

    const viewer = document.getElementById('mediaViewer');
    const viewerContent = document.getElementById('viewerContent');
    const viewerTitle = document.getElementById('viewerTitle');
    const fileBrowser = document.getElementById('fileBrowser');

    cleanupComicReaderState();
    viewer.classList.add('comic-mode');
    viewerContent.classList.add('comic-content');
    viewerTitle.textContent = name;
    fileBrowser.classList.add('hidden');
    viewer.classList.remove('hidden');

    showLoading();
    try {
        const metadata = prefetchedMetadata || await fetchAPI(`${API_BASE}/api/comic/metadata?path=${encodeURIComponent(path)}`);
        if (!metadata.page_count || metadata.page_count < 1) {
            viewerContent.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">压缩包中未检测到可阅读图片</p>';
            return;
        }
        totalComicPages = metadata.page_count;
        renderComicReader(path, metadata.page_count);
    } catch (error) {
        console.error('加载漫画失败:', error);
        viewerContent.innerHTML = '<p style="text-align: center; color: var(--error-color);">加载失败: ' + error.message + '</p>';
    } finally {
        hideLoading();
    }
}

function renderComicReader(path, totalPages) {
    const viewerContent = document.getElementById('viewerContent');
    const readerSettings = loadReaderSettings();
    const savedProgress = loadReaderProgress(path);
    const initialPage = Math.min(totalPages, Math.max(1, savedProgress.page || 1));

    const pagesHtml = Array.from({ length: totalPages }, (_, i) => {
        const pageNum = i + 1;
        const imageUrl = buildComicPageUrl(path, pageNum);
        const fallbackUrl = buildComicFallbackPageUrl(path, pageNum);
        return `
            <article class="comic-page-frame" data-page="${pageNum}">
                <div class="comic-page-index">第 ${pageNum} 页 / 共 ${totalPages} 页</div>
                <div class="comic-page-placeholder"></div>
                <img class="comic-page comic-page-pending" data-src="${imageUrl}" data-fallback-src="${fallbackUrl}" alt="第 ${pageNum} 页" decoding="async">
            </article>
        `;
    }).join('');

    viewerContent.innerHTML = `
        <div class="comic-reader" id="comicReader">
            <div class="comic-reader-toolbar" id="comicReaderToolbar">
                <div class="comic-progress-wrap">
                    <div class="comic-progress-text" id="comicProgressText">第 ${initialPage} 页 / 共 ${totalPages} 页</div>
                    <div class="comic-progress-track">
                        <div class="comic-progress-bar" id="comicProgressBar"></div>
                    </div>
                </div>
                <div class="comic-toolbar-controls">
                    <label class="reader-control">
                        宽度
                        <input id="readerScaleRange" type="range" min="78" max="130" step="2" value="${readerSettings.scale}">
                    </label>
                    <label class="reader-control">
                        间距
                        <input id="readerGapRange" type="range" min="8" max="28" step="1" value="${readerSettings.gap}">
                    </label>
                    <button type="button" class="btn-reader-toggle" id="readerImmersiveBtn">沉浸阅读</button>
                    <button type="button" class="btn-reader-toggle" id="readerTopBtn">回到顶部</button>
                </div>
            </div>
            <div class="comic-reader-header">连续下拉阅读 · 快捷键 J/K 翻滚，F 沉浸，T 顶部</div>
            <div class="comic-scroll" id="comicScroll">
                ${pagesHtml}
            </div>
        </div>
    `;

    const scrollRoot = document.getElementById('comicScroll');
    const progressText = document.getElementById('comicProgressText');
    const progressBar = document.getElementById('comicProgressBar');
    const scaleRange = document.getElementById('readerScaleRange');
    const gapRange = document.getElementById('readerGapRange');
    const immersiveBtn = document.getElementById('readerImmersiveBtn');
    const topBtn = document.getElementById('readerTopBtn');
    const imageNodes = Array.from(scrollRoot.querySelectorAll('img[data-src]'));
    const pageFrames = Array.from(scrollRoot.querySelectorAll('.comic-page-frame'));
    const loadTimeoutMs = IOS_FAMILY ? 42000 : 30000;
    const maxConcurrentLoads = IOS_FAMILY ? 2 : 4;
    const prefetchAhead = IOS_FAMILY ? 2 : 3;
    const pendingQueue = [];
    const queuedImages = new Set();
    let activeLoads = 0;
    let currentPage = initialPage;
    const readerState = {
        observer: null,
        scrollRoot,
        scrollHandler: null,
        keyHandler: null,
        persistTimer: 0,
        rafId: 0,
    };

    const updateReaderLayout = () => {
        const maxWidth = Math.min(1400, Math.max(720, Math.round(980 * (readerSettings.scale / 100))));
        scrollRoot.style.setProperty('--reader-max-width', `${maxWidth}px`);
        scrollRoot.style.setProperty('--reader-gap', `${readerSettings.gap}px`);
        if (immersiveBtn) {
            immersiveBtn.textContent = readerSettings.immersive ? '退出沉浸' : '沉浸阅读';
        }
        applyReaderImmersiveMode(readerSettings.immersive);
    };

    const setCurrentPage = (pageNum) => {
        const clampedPage = Math.min(totalPages, Math.max(1, Number(pageNum) || 1));
        currentPage = clampedPage;

        if (progressText) {
            progressText.textContent = `第 ${clampedPage} 页 / 共 ${totalPages} 页`;
        }
        if (progressBar) {
            progressBar.style.width = `${(clampedPage / totalPages) * 100}%`;
        }

        pageFrames.forEach((frame, idx) => {
            frame.classList.toggle('is-active', idx + 1 === clampedPage);
        });

        if (readerState.persistTimer) {
            window.clearTimeout(readerState.persistTimer);
        }
        readerState.persistTimer = window.setTimeout(() => {
            saveReaderProgress(path, clampedPage);
        }, 250);
    };

    const clearImageTimer = (img) => {
        const timerId = Number(img?.dataset?.timerId || '');
        if (!Number.isNaN(timerId)) {
            window.clearTimeout(timerId);
        }
        if (img?.dataset) {
            delete img.dataset.timerId;
        }
    };

    const pumpQueue = () => {
        while (activeLoads < maxConcurrentLoads && pendingQueue.length > 0) {
            const img = pendingQueue.shift();
            queuedImages.delete(img);
            if (!img) {
                continue;
            }
            if (img.dataset.state === 'loading' || img.dataset.state === 'loaded' || img.dataset.state === 'error') {
                continue;
            }
            const src = img.dataset.src;
            if (!src) {
                continue;
            }
            startImageLoad(img, src, false, false);
        }
    };

    const finishImageLoad = (img) => {
        if (img?.dataset?.inflight !== '1') {
            return;
        }
        img.dataset.inflight = '0';
        activeLoads = Math.max(0, activeLoads - 1);
        pumpQueue();
    };

    const startImageLoad = (img, targetUrl, isRetry, reuseSlot) => {
        if (!img || !targetUrl) return;
        clearImageTimer(img);

        if (!reuseSlot) {
            img.dataset.inflight = '1';
            activeLoads += 1;
        }
        img.dataset.state = 'loading';
        img.dataset.retry = isRetry ? '1' : '0';
        img.dataset.currentUrl = targetUrl;
        img.dataset.loadError = '';

        const timerId = window.setTimeout(() => {
            if (img.dataset.state === 'loaded' || img.dataset.state === 'error') {
                return;
            }
            const fallback = img.dataset.fallbackSrc || '';
            if (!isRetry && fallback && fallback !== targetUrl) {
                startImageLoad(img, fallback, true, true);
                return;
            }
            img.dataset.loadError = '加载超时';
            img.dispatchEvent(new Event('error'));
        }, loadTimeoutMs);
        img.dataset.timerId = String(timerId);

        const requestUrl = isRetry
            ? `${targetUrl}${targetUrl.includes('?') ? '&' : '?'}retry_ts=${Date.now()}`
            : targetUrl;
        img.src = requestUrl;
    };

    const enqueueImage = (img, priority = false) => {
        if (!img) {
            return;
        }
        if (img.dataset.state === 'loading' || img.dataset.state === 'loaded' || img.dataset.state === 'error') {
            return;
        }
        if (queuedImages.has(img)) {
            return;
        }
        if (priority) {
            pendingQueue.unshift(img);
        } else {
            pendingQueue.push(img);
        }
        queuedImages.add(img);
        pumpQueue();
    };

    const activateImage = (img, priority = false) => {
        enqueueImage(img, priority);
    };

    const activateImageInFrame = (frame, priority = false) => {
        if (!frame) return;
        const img = frame.querySelector('img[data-src]');
        activateImage(img, priority);
    };

    const activateNearbyFrames = (centerPage) => {
        const basePage = Math.min(totalPages, Math.max(1, Number(centerPage) || 1));
        for (let offset = 1; offset <= prefetchAhead; offset += 1) {
            activateImageInFrame(pageFrames[basePage - 1 + offset], false);
        }
    };

    const handleImageState = (img) => {
        const frame = img.closest('.comic-page-frame');
        const placeholder = frame?.querySelector('.comic-page-placeholder');

        img.addEventListener('load', () => {
            clearImageTimer(img);
            img.dataset.state = 'loaded';
            if (placeholder) {
                placeholder.remove();
            }
            img.classList.remove('comic-page-pending');
            finishImageLoad(img);
        });

        img.addEventListener('error', () => {
            clearImageTimer(img);

            const fallback = img.dataset.fallbackSrc || '';
            const currentUrl = img.dataset.currentUrl || '';
            const isRetry = img.dataset.retry === '1';
            if (!isRetry && fallback && fallback !== currentUrl) {
                startImageLoad(img, fallback, true, true);
                return;
            }

            img.dataset.state = 'error';
            if (placeholder) {
                placeholder.remove();
            }
            img.remove();
            finishImageLoad(img);
            if (frame) {
                const errorBlock = document.createElement('div');
                errorBlock.className = 'comic-page-error';
                const reason = img.dataset.loadError || '图片解码失败';
                errorBlock.textContent = `第 ${frame.dataset.page} 页加载失败：${reason}`;
                frame.appendChild(errorBlock);
            }
        });
    };

    imageNodes.forEach(handleImageState);

    const visibilityMap = new Map();
    const updateCurrentPageFromVisibility = () => {
        let bestFrame = null;
        let bestRatio = 0;
        pageFrames.forEach((frame) => {
            const ratio = visibilityMap.get(frame) || 0;
            if (ratio > bestRatio) {
                bestRatio = ratio;
                bestFrame = frame;
            }
        });
        if (bestFrame) {
            setCurrentPage(Number(bestFrame.dataset.page));
        }
    };

    const updateCurrentPageByPosition = () => {
        const pivot = scrollRoot.scrollTop + scrollRoot.clientHeight * 0.25;
        let bestFrame = pageFrames[0];
        let bestDistance = Number.POSITIVE_INFINITY;
        pageFrames.forEach((frame) => {
            const distance = Math.abs(frame.offsetTop - pivot);
            if (distance < bestDistance) {
                bestDistance = distance;
                bestFrame = frame;
            }
        });
        if (bestFrame) {
            setCurrentPage(Number(bestFrame.dataset.page));
        }
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            visibilityMap.set(entry.target, entry.isIntersecting ? entry.intersectionRatio : 0);
            if (entry.isIntersecting) {
                const pageNum = Number(entry.target.dataset.page);
                activateImageInFrame(entry.target, true);
                activateNearbyFrames(pageNum);
            }
        });
        updateCurrentPageFromVisibility();
    }, {
        root: scrollRoot,
        rootMargin: '500px 0px 500px 0px',
        threshold: [0.2, 0.45, 0.7],
    });

    pageFrames.forEach((frame) => {
        visibilityMap.set(frame, 0);
        observer.observe(frame);
    });
    pageFrames.slice(0, Math.min(totalPages, prefetchAhead + 2)).forEach((frame) => activateImageInFrame(frame, true));

    const scrollHandler = () => {
        if (readerState.rafId) return;
        readerState.rafId = window.requestAnimationFrame(() => {
            readerState.rafId = 0;
            updateCurrentPageByPosition();
            activateNearbyFrames(currentPage);
        });
    };
    scrollRoot.addEventListener('scroll', scrollHandler, { passive: true });

    if (scaleRange) {
        scaleRange.addEventListener('input', () => {
            readerSettings.scale = Number(scaleRange.value);
            updateReaderLayout();
            saveReaderSettings(readerSettings);
        });
    }

    if (gapRange) {
        gapRange.addEventListener('input', () => {
            readerSettings.gap = Number(gapRange.value);
            updateReaderLayout();
            saveReaderSettings(readerSettings);
        });
    }

    if (immersiveBtn) {
        immersiveBtn.addEventListener('click', () => {
            readerSettings.immersive = !readerSettings.immersive;
            updateReaderLayout();
            saveReaderSettings(readerSettings);
        });
    }

    if (topBtn) {
        topBtn.addEventListener('click', () => {
            scrollRoot.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    const keyHandler = (event) => {
        if (currentViewer !== 'comic') return;
        const target = event.target;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
            return;
        }
        if (event.key === 'j' || event.key === 'J' || event.key === 'ArrowDown') {
            event.preventDefault();
            scrollRoot.scrollBy({ top: Math.round(scrollRoot.clientHeight * 0.86), behavior: 'smooth' });
        } else if (event.key === 'k' || event.key === 'K' || event.key === 'ArrowUp') {
            event.preventDefault();
            scrollRoot.scrollBy({ top: -Math.round(scrollRoot.clientHeight * 0.86), behavior: 'smooth' });
        } else if (event.key === 'f' || event.key === 'F') {
            event.preventDefault();
            readerSettings.immersive = !readerSettings.immersive;
            updateReaderLayout();
            saveReaderSettings(readerSettings);
        } else if (event.key === 't' || event.key === 'T') {
            event.preventDefault();
            scrollRoot.scrollTo({ top: 0, behavior: 'smooth' });
        }
    };
    window.addEventListener('keydown', keyHandler);

    updateReaderLayout();
    setCurrentPage(initialPage);
    const restoreFrame = pageFrames[initialPage - 1];
    if (restoreFrame) {
        window.requestAnimationFrame(() => {
            scrollRoot.scrollTop = Math.max(0, restoreFrame.offsetTop - 12);
            activateNearbyFrames(initialPage);
        });
    } else {
        scrollRoot.scrollTop = 0;
    }

    readerState.observer = observer;
    readerState.scrollHandler = scrollHandler;
    readerState.keyHandler = keyHandler;
    comicReaderState = readerState;
}

function prevComicPage() {
    showError('当前为下拉阅读模式，无需翻页');
}

function nextComicPage() {
    showError('当前为下拉阅读模式，无需翻页');
}

async function openArchiveBrowser(path, name) {
    currentViewer = 'archive';
    currentArchive = path;

    const viewer = document.getElementById('mediaViewer');
    const viewerContent = document.getElementById('viewerContent');
    const viewerTitle = document.getElementById('viewerTitle');
    const fileBrowser = document.getElementById('fileBrowser');

    cleanupComicReaderState();
    applyReaderImmersiveMode(false);
    viewer.classList.remove('comic-mode');
    viewerContent.classList.remove('comic-content');

    viewerTitle.textContent = name;
    fileBrowser.classList.add('hidden');
    viewer.classList.remove('hidden');

    showLoading();
    try {
        const archiveInfo = await fetchAPI(`${API_BASE}/api/archive/contents?path=${encodeURIComponent(path)}`);
        renderArchiveContents(archiveInfo.entries);
    } catch (error) {
        console.error('加载压缩包失败:', error);
        viewerContent.innerHTML = '<p style="text-align: center; color: var(--error-color);">加载失败</p>';
    } finally {
        hideLoading();
    }
}

function renderArchiveContents(entries) {
    const viewerContent = document.getElementById('viewerContent');
    
    const files = entries.filter(e => !e.is_directory);
    
    if (files.length === 0) {
        viewerContent.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">压缩包为空</p>';
        return;
    }

    viewerContent.innerHTML = `
        <div class="archive-browser">
            <div class="archive-list">
                ${files.map((entry, index) => `
                    <div class="archive-item" data-index="${index}">
                        <span class="file-icon">📄</span>
                        <div>
                            <div class="file-name">${escapeHtml(entry.filename)}</div>
                            <div class="file-info">${formatSize(entry.size)}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    viewerContent.querySelectorAll('.archive-item').forEach(item => {
        item.addEventListener('click', () => {
            const index = Number(item.dataset.index);
            const entry = files[index];
            if (!entry) return;
            extractFile(entry.filename);
        });
    });
}

async function extractFile(filename) {
    showLoading();
    try {
        const url = `${API_BASE}/api/archive/extract?path=${encodeURIComponent(currentArchive)}&entry=${encodeURIComponent(filename)}`;
        const response = await fetch(url);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '解压失败');
        }

        const blob = await response.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename.split('/').pop();
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(downloadUrl);
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
}

function closeViewer() {
    cleanupComicReaderState();
    applyReaderImmersiveMode(false);

    currentViewer = null;
    currentComic = null;
    currentArchive = null;

    const viewer = document.getElementById('mediaViewer');
    const fileBrowser = document.getElementById('fileBrowser');
    const viewerContent = document.getElementById('viewerContent');

    viewerContent.querySelectorAll('img[data-timer-id]').forEach((img) => {
        const timerId = Number(img.dataset.timerId || '');
        if (!Number.isNaN(timerId)) {
            window.clearTimeout(timerId);
        }
    });

    viewer.classList.remove('comic-mode');
    viewerContent.classList.remove('comic-content');
    viewer.classList.add('hidden');
    fileBrowser.classList.remove('hidden');
    viewerContent.innerHTML = '';
}

document.addEventListener('DOMContentLoaded', () => {
    const versionNode = document.getElementById('appVersion');
    if (versionNode) {
        versionNode.textContent = APP_VERSION;
    }
    loadDirectory('/');
});

window.goHome = goHome;
window.navigateTo = navigateTo;
window.searchFiles = searchFiles;
window.handleSearch = handleSearch;
window.openFile = openFile;
window.closeViewer = closeViewer;
window.prevComicPage = prevComicPage;
window.nextComicPage = nextComicPage;
window.extractFile = extractFile;
window.closeError = closeError;


