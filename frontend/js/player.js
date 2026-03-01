import { seriesState, comicState, archiveState, ui } from './store.js';
import { buildMeta } from './views.js';
import { buildUrl, fetchJSON, getUiSettings } from './api.js';
import { showLoading, hideLoading, showError, openPlayerScreen, closePlayerScreen, openDetailModal, closeDetailModal, observeImages } from './ui.js';
import { escapeHtml, formatSize } from './utils.js';

export const COMIC_EXTENSIONS = new Set([
    ".cbz", ".zip",
    ".cbr", ".rar",
    ".cb7", ".7z",
    ".cbt", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
]);

export function isComicItem(item) {
    if (!item) return false;
    const ext = String(item.extension || "").toLowerCase();
    if (item.type === "comic") return true;
    if (item.category === "comics" && COMIC_EXTENSIONS.has(ext)) return true;
    return item.type === "archive" && item.category === "comics" && COMIC_EXTENSIONS.has(ext);
}

export function resetDetailStates() {
    if (seriesState.video) {
        seriesState.video.pause();
        seriesState.video.removeAttribute("src");
        seriesState.video.load();
    }

    seriesState.mode = "";
    seriesState.episodes = [];
    seriesState.sections = [];
    seriesState.sectionId = "all";
    seriesState.sectionPages = {};
    seriesState.collapsedSections = new Set();
    seriesState.index = 0;
    seriesState.autoplay = true;
    seriesState.video = null;
    seriesState.currentItem = null;
    seriesState.title = "";
    seriesState.meta = "";
    isProgressDragging = false;
    pendingSeekSeconds = null;

    comicState.item = null;
    comicState.totalPages = 0;
    comicState.page = 1;
    if (comicState.scrollObserver) {
        comicState.scrollObserver.disconnect();
        comicState.scrollObserver = null;
    }

    archiveState.path = "";
    archiveState.entries = [];
}

const NATIVE_PLAYABLE_VIDEO_EXTENSIONS = new Set([".mp4", ".m4v", ".mov", ".webm", ".ogg"]);
const VIDEO_PROGRESS_SCALE = 1000;
const videoDurationCache = new Map();
let isProgressDragging = false;
let pendingSeekSeconds = null;

export function shouldForceCompatPlayback(item) {
    const extension = String(item?.extension || "").toLowerCase();
    if (!extension) return false;
    return !NATIVE_PLAYABLE_VIDEO_EXTENSIONS.has(extension);
}

export function buildVideoUrl(item, options = {}) {
    if (!item?.path) {
        return item?.stream_url || "";
    }
    const useCompat = shouldForceCompatPlayback(item);
    const parsedStart = Number(options.startSeconds);
    const startSeconds = Number.isFinite(parsedStart) ? Math.max(0, parsedStart) : 0;
    return buildUrl("/api/video/stream", {
        path: item.path,
        ios_compat: useCompat ? 1 : null,
        start: useCompat ? startSeconds : null,
    });
}

function formatPlaybackTime(seconds) {
    const safe = Math.max(0, Math.floor(Number(seconds) || 0));
    const hours = Math.floor(safe / 3600);
    const minutes = Math.floor((safe % 3600) / 60);
    const secs = safe % 60;
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function getEffectiveDuration(video) {
    if (!video) return 0;
    const cachedDuration = Number(video.dataset.totalDuration || 0);
    const streamStart = Number(video.dataset.streamStart || 0);
    const mediaDuration = Number(video.duration);
    const inferredDuration = Number.isFinite(mediaDuration) && mediaDuration > 0
        ? streamStart + mediaDuration
        : 0;
    return Math.max(0, cachedDuration, inferredDuration);
}

function getAbsoluteCurrentTime(video) {
    if (!video) return 0;
    const streamStart = Number(video.dataset.streamStart || 0);
    return Math.max(0, streamStart + Math.max(0, Number(video.currentTime) || 0));
}

function updateDurationInfo(durationSeconds) {
    const info = document.getElementById("playerDurationInfo");
    if (!info) return;
    if (durationSeconds > 0) {
        info.textContent = `总时长：${formatPlaybackTime(durationSeconds)}`;
        return;
    }
    info.textContent = "总时长：--:--";
}

function updatePlayerProgress() {
    const video = seriesState.video;
    if (!video) return;

    const current = getAbsoluteCurrentTime(video);
    const duration = getEffectiveDuration(video);
    const currentNode = document.getElementById("playerCurrentTime");
    const totalNode = document.getElementById("playerTotalTime");
    const slider = document.getElementById("playerSeekRange");

    if (currentNode && !isProgressDragging) currentNode.textContent = formatPlaybackTime(current);
    if (totalNode) {
        totalNode.textContent = duration > 0 ? formatPlaybackTime(duration) : "--:--";
    }
    updateDurationInfo(duration);

    if (!slider) return;
    if (duration <= 0) {
        slider.disabled = true;
        slider.max = "1";
        slider.value = "0";
        return;
    }

    slider.disabled = false;
    const max = Math.max(1, Math.round(duration * VIDEO_PROGRESS_SCALE));
    const value = Math.max(
        0,
        Math.min(
            max,
            Math.round(((isProgressDragging && pendingSeekSeconds !== null) ? pendingSeekSeconds : current) * VIDEO_PROGRESS_SCALE),
        ),
    );
    slider.max = String(max);
    slider.value = String(value);
}

function getCurrentPlaybackItem() {
    return seriesState.currentItem;
}

function seekToAbsoluteTime(seconds) {
    const video = seriesState.video;
    const item = getCurrentPlaybackItem();
    if (!video || !item) return;

    const duration = getEffectiveDuration(video);
    const boundedTarget = duration > 0
        ? Math.min(Math.max(0, seconds), Math.max(0, duration - 0.05))
        : Math.max(0, seconds);
    const useCompat = video.dataset.compatLive === "1";

    if (!useCompat) {
        video.currentTime = boundedTarget;
        updatePlayerProgress();
        return;
    }

    const isPlaying = !video.paused;
    const current = getAbsoluteCurrentTime(video);
    if (Math.abs(current - boundedTarget) < 0.6) return;

    video.dataset.internalSeek = "1";
    loadVideoItem(item, { startSeconds: boundedTarget, autoplay: isPlaying });
    window.setTimeout(() => {
        if (seriesState.video) seriesState.video.dataset.internalSeek = "0";
    }, 1200);
}

function commitPendingSeek() {
    if (pendingSeekSeconds === null) {
        isProgressDragging = false;
        return;
    }
    const target = pendingSeekSeconds;
    pendingSeekSeconds = null;
    isProgressDragging = false;
    seekToAbsoluteTime(target);
}

function bindPlayerProgressControls() {
    const slider = document.getElementById("playerSeekRange");
    if (!slider || slider.dataset.bound === "1") return;
    slider.dataset.bound = "1";

    slider.addEventListener("pointerdown", () => {
        isProgressDragging = true;
    });

    slider.addEventListener("mousedown", () => {
        isProgressDragging = true;
    });

    slider.addEventListener("input", () => {
        isProgressDragging = true;
        const duration = getEffectiveDuration(seriesState.video);
        const currentNode = document.getElementById("playerCurrentTime");
        if (!currentNode || duration <= 0) return;
        const target = Number(slider.value) / VIDEO_PROGRESS_SCALE;
        pendingSeekSeconds = target;
        currentNode.textContent = formatPlaybackTime(target);
    });

    slider.addEventListener("change", () => {
        commitPendingSeek();
    });

    slider.addEventListener("pointerup", () => {
        commitPendingSeek();
    });

    slider.addEventListener("touchend", () => {
        commitPendingSeek();
    });

    slider.addEventListener("blur", () => {
        commitPendingSeek();
    });
}

function bindVideoPlaybackEvents(video) {
    if (!video || video.dataset.bound === "1") return;
    video.dataset.bound = "1";

    const update = () => updatePlayerProgress();
    video.addEventListener("loadedmetadata", update);
    video.addEventListener("durationchange", update);
    video.addEventListener("timeupdate", update);

    video.addEventListener("seeking", () => {
        if (video.dataset.compatLive !== "1") return;
        if (video.dataset.internalSeek === "1") return;
        const target = getAbsoluteCurrentTime(video);
        seekToAbsoluteTime(target);
    });
}

async function getVideoDuration(item) {
    const path = String(item?.path || "");
    if (!path) return 0;
    if (videoDurationCache.has(path)) {
        return videoDurationCache.get(path) || 0;
    }
    try {
        const payload = await fetchJSON("/api/video/metadata", { path });
        const duration = Math.max(0, Number(payload?.duration) || 0);
        videoDurationCache.set(path, duration);
        return duration;
    } catch (error) {
        return 0;
    }
}

function loadVideoItem(item, options = {}) {
    const video = seriesState.video;
    if (!video || !item) return;

    const useCompat = shouldForceCompatPlayback(item);
    const rawStart = Number(options.startSeconds);
    const startSeconds = Number.isFinite(rawStart) ? Math.max(0, rawStart) : 0;
    const autoplay = options.autoplay !== false;

    seriesState.currentItem = item;
    video.dataset.compatLive = useCompat ? "1" : "0";
    video.dataset.streamStart = String(startSeconds);
    video.dataset.totalDuration = String(videoDurationCache.get(item.path) || 0);
    video.classList.toggle("compat-live", useCompat);

    bindVideoPlaybackEvents(video);
    bindPlayerProgressControls();

    const url = buildVideoUrl(item, { startSeconds });
    const expected = new URL(url, window.location.origin).href;
    if (video.src !== expected) {
        video.src = url;
    }
    updatePlayerProgress();

    void getVideoDuration(item).then((duration) => {
        const currentPath = String(seriesState.currentItem?.path || "");
        if (currentPath !== String(item.path || "")) return;
        if (seriesState.video !== video) return;
        video.dataset.totalDuration = String(duration || 0);
        updatePlayerProgress();
    });

    if (autoplay) {
        const playResult = video.play();
        if (playResult && typeof playResult.catch === "function") {
            playResult.catch(() => { });
        }
    }
}

export function openGenericDetail(item) {
    const url = buildUrl("/api/files/raw", { path: item.path });
    openDetailModal(`
        <section class="detail-header">
            <h2 class="detail-title">${escapeHtml(item.name)}</h2>
            <div class="detail-meta"><span>${escapeHtml(buildMeta(item))}</span></div>
        </section>
        <div class="media-actions" style="margin-top: 16px;">
            <a class="mini-btn" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">下载文件</a>
        </div>
    `);
}

export function openVideoDetail(item) {
    seriesState.mode = "video";
    seriesState.title = item.name;
    seriesState.meta = buildMeta(item);
    seriesState.episodes = [{ ...item, __index: 0 }];
    seriesState.sections = [];
    seriesState.sectionId = "all";
    seriesState.sectionPages = {};
    seriesState.collapsedSections = new Set();
    seriesState.index = 0;
    seriesState.autoplay = false;
    seriesState.currentItem = item;

    openPlayerScreen(`
        <div class="player-shell">
            <header class="player-header">
                <button class="mini-btn" data-action="player-close">返回媒体库</button>
                <div class="player-header-meta">
                    <h2 class="player-title">${escapeHtml(item.name)}</h2>
                    <p class="player-subtitle">${escapeHtml(buildMeta(item))}</p>
                </div>
                <div class="player-header-actions">
                    <button class="mini-btn" data-action="player-web-fullscreen">网页全屏</button>
                    <button class="mini-btn" data-action="player-browser-fullscreen">全屏</button>
                </div>
            </header>
            <div class="player-main">
                <section class="player-left">
                    <div class="player-video-wrap" id="playerVideoWrap">
                        <video id="playerVideo" controls playsinline preload="metadata"></video>
                    </div>
                    <div class="player-progress">
                        <input type="range" id="playerSeekRange" min="0" max="1" value="0" step="1" disabled>
                        <div class="player-progress-meta">
                            <span id="playerCurrentTime">00:00</span>
                            <span id="playerTotalTime">--:--</span>
                        </div>
                    </div>
                    <div class="player-now">
                        <strong id="playerNowPlaying">${escapeHtml(item.name)}</strong>
                    </div>
                </section>
                <aside class="player-right">
                    <div class="player-right-header">视频信息</div>
                    <div class="player-media-info">
                        <p>${escapeHtml(item.name)}</p>
                        <p>${escapeHtml(buildMeta(item))}</p>
                        <p id="playerDurationInfo">总时长：--:--</p>
                        <p>${escapeHtml(item.path || "")}</p>
                    </div>
                </aside>
            </div>
        </div>
    `);

    seriesState.video = document.getElementById("playerVideo");
    loadVideoItem(item, { startSeconds: 0, autoplay: true });
}

export function openMusicDetail(item) {
    const url = item.stream_url || buildUrl("/api/files/raw", { path: item.path });
    openDetailModal(`
        <section class="detail-header">
            <h2 class="detail-title">${escapeHtml(item.name)}</h2>
            <div class="detail-meta"><span>${escapeHtml(buildMeta(item))}</span></div>
        </section>
        <div class="detail-preview">
            <audio controls preload="metadata" src="${escapeHtml(url)}"></audio>
        </div>
    `);
}

export function openPhotoDetail(item) {
    const url = item.stream_url || item.thumbnail || buildUrl("/api/files/raw", { path: item.path });
    openDetailModal(`
        <section class="detail-header">
            <h2 class="detail-title">${escapeHtml(item.name)}</h2>
            <div class="detail-meta"><span>${escapeHtml(buildMeta(item))}</span></div>
        </section>
        <div class="detail-preview">
            <img src="${escapeHtml(url)}" alt="${escapeHtml(item.name)}" loading="lazy">
        </div>
    `);
}

// ========================
// Series Logic
// ========================

export function normalizeEpisodes(series) {
    const episodes = Array.isArray(series.episodes) ? series.episodes.map((i) => ({ ...i })) : [];
    episodes.sort((a, b) => {
        const pa = Number(a.play_index) || Number.POSITIVE_INFINITY;
        const pb = Number(b.play_index) || Number.POSITIVE_INFINITY;
        if (pa !== pb) return pa - pb;

        const sa = Number(a.section_order) || 0;
        const sb = Number(b.section_order) || 0;
        if (sa !== sb) return sa - sb;

        const ea = Number(a.episode_no);
        const eb = Number(b.episode_no);
        if (Number.isFinite(ea) && Number.isFinite(eb) && ea !== eb) return ea - eb;

        return String(a.name || "").localeCompare(String(b.name || ""), "zh-CN");
    });
    episodes.forEach((episode, index) => {
        episode.__index = index;
    });
    return episodes;
}

export function episodeLabel(episode, index) {
    const label = episode.episode_label || (Number.isFinite(Number(episode.episode_no)) ? `第${episode.episode_no}集` : `第${index + 1}集`);
    const fileName = String(episode.name || "").replace(/\.[^/.]+$/, "").trim();
    if (!fileName) return label;
    return `${label} · ${fileName.length > 20 ? `${fileName.slice(0, 20)}...` : fileName}`;
}

export function buildSeriesSections(episodes) {
    const sectionMap = new Map();
    episodes.forEach((episode) => {
        const sectionId = episode.section_id || `section-${episode.section_title || "unknown"}`;
        const title = episode.section_title
            || (Number.isFinite(Number(episode.season_no)) ? `第${episode.season_no}季` : "未分组");
        if (!sectionMap.has(sectionId)) {
            sectionMap.set(sectionId, {
                id: sectionId,
                title,
                order: Number(episode.section_order) || 0,
                episodes: [],
            });
        }
        episode.__sectionId = sectionId;
        sectionMap.get(sectionId).episodes.push(episode);
    });

    return Array.from(sectionMap.values()).sort((a, b) => {
        if (a.order !== b.order) return a.order - b.order;
        return String(a.title).localeCompare(String(b.title), "zh-CN");
    });
}

export function getActiveSeriesSection() {
    if (!seriesState.sections.length) return null;
    const found = seriesState.sections.find((section) => section.id === seriesState.sectionId);
    if (found) return found;
    seriesState.sectionId = seriesState.sections[0].id;
    return seriesState.sections[0];
}

export function getSeriesTotalPages(section) {
    return Math.max(1, Math.ceil(section.episodes.length / seriesState.pageSize));
}

export function getSeriesPage(sectionId) {
    const rawPage = Number(seriesState.sectionPages[sectionId] || 1);
    return (!Number.isFinite(rawPage) || rawPage < 1) ? 1 : Math.floor(rawPage);
}

export function setSeriesPage(sectionId, page, totalPages) {
    const maxPage = Math.max(1, Number(totalPages) || 1);
    const normalized = Math.min(maxPage, Math.max(1, Math.floor(Number(page) || 1)));
    seriesState.sectionPages[sectionId] = normalized;
    return normalized;
}

export function resolveSectionPage(section) {
    const totalPages = getSeriesTotalPages(section);
    const currentPage = setSeriesPage(section.id, getSeriesPage(section.id), totalPages);
    const start = (currentPage - 1) * seriesState.pageSize;
    const end = Math.min(section.episodes.length, start + seriesState.pageSize);
    return {
        totalPages,
        currentPage,
        start,
        end,
        episodes: section.episodes.slice(start, end),
    };
}

function renderSectionTabs() {
    return `
        <div class="player-tab-bar">
            ${seriesState.sections
            .map((section) => `
                    <button
                        class="player-tab-item ${seriesState.sectionId === section.id ? "active" : ""}"
                        data-action="player-switch-section"
                        data-section-id="${escapeHtml(section.id)}"
                    >
                        ${escapeHtml(section.title)} (${section.episodes.length})
                    </button>
                `)
            .join("")}
        </div>
    `;
}

function renderEpisodeThumb(episode) {
    if (episode.thumbnail) {
        return `<img data-src="${escapeHtml(episode.thumbnail)}" alt="${escapeHtml(episode.name || "封面")}">`;
    }
    return `<div class="player-episode-thumb-fallback">EP ${episode.__index + 1}</div>`;
}

export function renderSeriesSectionPanel() {
    const activeSection = getActiveSeriesSection();
    if (!activeSection) {
        return `<div class="empty-panel">暂无分集</div>`;
    }

    const collapsed = seriesState.collapsedSections.has(activeSection.id);
    const pageInfo = resolveSectionPage(activeSection);
    const collapsedLabel = collapsed ? "展开当前季" : "收起当前季";

    const rows = collapsed
        ? `<div class="empty-panel">当前分季已收起</div>`
        : pageInfo.episodes
            .map((episode) => {
                const isActive = episode.__index === seriesState.index ? "active" : "";
                return `
                <button class="player-episode-item ${isActive}" data-action="player-play-episode" data-episode-index="${episode.__index}">
                    <div class="player-episode-thumb">${renderEpisodeThumb(episode)}</div>
                    <div class="player-episode-main">
                        <div class="player-episode-title">${escapeHtml(episodeLabel(episode, episode.__index))}</div>
                        <div class="player-episode-sub">${escapeHtml(episode.name || "")}</div>
                    </div>
                </button>
            `;
            })
            .join("");

    return `
        ${renderSectionTabs()}
        <div class="player-list-toolbar">
            <button class="mini-btn" data-action="toggle-season" data-section-id="${escapeHtml(activeSection.id)}">${collapsedLabel}</button>
            <div class="player-pagination">
                <button class="mini-btn" data-action="player-page-prev" ${pageInfo.currentPage <= 1 ? "disabled" : ""}>上一页</button>
                <span>第 ${pageInfo.currentPage} / ${pageInfo.totalPages} 页 · ${pageInfo.start + 1}-${pageInfo.end} / ${activeSection.episodes.length}</span>
                <button class="mini-btn" data-action="player-page-next" ${pageInfo.currentPage >= pageInfo.totalPages ? "disabled" : ""}>下一页</button>
            </div>
        </div>
        <div class="player-episode-list" data-section-content="${escapeHtml(activeSection.id)}">
            ${rows}
        </div>
    `;
}

export function rerenderSeriesPanel() {
    const panel = document.getElementById("playerSeasonList");
    if (!panel) return;
    panel.innerHTML = renderSeriesSectionPanel();
    observeImages();
}

export function updateSeriesEpisodeHighlight() {
    document.querySelectorAll(".player-episode-item[data-episode-index]").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.episodeIndex) === seriesState.index);
    });
    const activeNode = document.querySelector(`.player-episode-item[data-episode-index="${seriesState.index}"]`);
    if (activeNode) {
        activeNode.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
}

export function openSeriesDetail(series) {
    const episodes = normalizeEpisodes(series);
    if (!episodes.length) {
        showError("该系列没有可播放剧集");
        return;
    }

    const sections = buildSeriesSections(episodes);
    seriesState.mode = "series";
    seriesState.title = series.name;
    seriesState.meta = buildMeta(series);
    seriesState.episodes = episodes;
    seriesState.sections = sections;
    seriesState.sectionId = sections[0] ? sections[0].id : "all";
    seriesState.sectionPages = Object.fromEntries(sections.map((section) => [section.id, 1]));
    seriesState.collapsedSections = new Set();
    seriesState.index = 0;
    seriesState.autoplay = getUiSettings().player_autoplay_default;
    seriesState.currentItem = null;

    openPlayerScreen(`
        <div class="player-shell">
            <header class="player-header">
                <button class="mini-btn" data-action="player-close">返回媒体库</button>
                <div class="player-header-meta">
                    <h2 class="player-title">${escapeHtml(series.name)}</h2>
                    <p class="player-subtitle">${escapeHtml(buildMeta(series))}</p>
                </div>
                <div class="player-header-actions">
                    <button class="mini-btn" id="playerPrevEpisode" data-action="player-prev">上一集</button>
                    <button class="mini-btn" id="playerNextEpisode" data-action="player-next">下一集</button>
                    <label class="series-toggle">
                        <input type="checkbox" id="playerAutoplay" ${seriesState.autoplay ? "checked" : ""}>
                        自动连播
                    </label>
                    <button class="mini-btn" data-action="player-web-fullscreen">网页全屏</button>
                    <button class="mini-btn" data-action="player-browser-fullscreen">全屏</button>
                </div>
            </header>
            <div class="player-main">
                <section class="player-left">
                    <div class="player-video-wrap" id="playerVideoWrap">
                        <video id="playerVideo" controls playsinline preload="metadata"></video>
                    </div>
                    <div class="player-progress">
                        <input type="range" id="playerSeekRange" min="0" max="1" value="0" step="1" disabled>
                        <div class="player-progress-meta">
                            <span id="playerCurrentTime">00:00</span>
                            <span id="playerTotalTime">--:--</span>
                        </div>
                    </div>
                    <div class="player-now">
                        <strong id="playerNowPlaying">准备播放...</strong>
                        <span class="player-now-meta" id="playerDurationInfo">总时长：--:--</span>
                    </div>
                </section>
                <aside class="player-right">
                    <div class="player-right-header">选集面板 (${episodes.length} 集)</div>
                    <div class="player-season-list" id="playerSeasonList">
                        ${renderSeriesSectionPanel()}
                    </div>
                </aside>
            </div>
        </div>
    `);

    observeImages();
    seriesState.video = document.getElementById("playerVideo");

    if (seriesState.video) {
        seriesState.video.addEventListener("ended", onSeriesEnded);
    }

    playSeriesEpisode(0);
}

export function playSeriesEpisode(index) {
    if (!seriesState.video || !seriesState.episodes.length) return;
    if (index < 0 || index >= seriesState.episodes.length) return;

    const episode = seriesState.episodes[index];

    seriesState.index = index;

    if (seriesState.mode === "series" && episode.__sectionId) {
        const matchedSection = seriesState.sections.find((section) => section.id === episode.__sectionId);
        if (matchedSection) {
            seriesState.sectionId = matchedSection.id;
            const sectionEpisodeIndex = matchedSection.episodes.findIndex((entry) => entry.__index === index);
            if (sectionEpisodeIndex >= 0) {
                const targetPage = Math.floor(sectionEpisodeIndex / seriesState.pageSize) + 1;
                setSeriesPage(matchedSection.id, targetPage, getSeriesTotalPages(matchedSection));
            }
            rerenderSeriesPanel();
        }
    }

    loadVideoItem(episode, { startSeconds: 0, autoplay: true });

    const label = document.getElementById("playerNowPlaying");
    if (label) {
        label.textContent = `正在播放：${episodeLabel(episode, index)}`;
    }

    const prevBtn = document.getElementById("playerPrevEpisode");
    const nextBtn = document.getElementById("playerNextEpisode");
    if (prevBtn) prevBtn.disabled = index <= 0;
    if (nextBtn) nextBtn.disabled = index >= seriesState.episodes.length - 1;
    updateSeriesEpisodeHighlight();
}

export function onSeriesEnded() {
    if (!seriesState.autoplay) return;
    const nextIndex = seriesState.index + 1;
    if (nextIndex < seriesState.episodes.length) {
        playSeriesEpisode(nextIndex);
    }
}

export function toggleWebFullscreen() {
    if (!ui.playerScreen) return;
    ui.playerScreen.classList.toggle("web-fullscreen");
}

export async function toggleBrowserFullscreen() {
    const target = document.getElementById("playerVideoWrap") || ui.playerScreen;
    if (!target) return;

    try {
        if (document.fullscreenElement) {
            await document.exitFullscreen();
            return;
        }
        await target.requestFullscreen();
    } catch (error) {
        showError(`全屏切换失败: ${error.message}`);
    }
}

// Comic Loading
export function comicPageUrl(path, page) {
    const dpr = window.devicePixelRatio || 1;
    const viewport = Math.max(window.innerWidth || 1280, 960);
    const maxWidth = Math.min(2800, Math.round(viewport * dpr * 1.25));
    return buildUrl("/api/comic/page", {
        path,
        page,
        max_width: maxWidth,
        quality: 84,
    });
}

function updateComicStatus(page) {
    const safePage = Math.min(comicState.totalPages, Math.max(1, Number(page) || 1));
    comicState.page = safePage;

    const input = document.getElementById("comicPageInput");
    const status = document.getElementById("comicPageStatus");
    const prevBtn = document.getElementById("comicPrevBtn");
    const nextBtn = document.getElementById("comicNextBtn");

    if (input) input.value = String(safePage);
    if (status) status.textContent = `第 ${safePage} / ${comicState.totalPages} 页`;
    if (prevBtn) prevBtn.disabled = safePage <= 1;
    if (nextBtn) nextBtn.disabled = safePage >= comicState.totalPages;
}

function setupComicScrollObserver() {
    const scroller = document.getElementById("comicReaderScroller");
    if (!scroller) return;

    if (comicState.scrollObserver) {
        comicState.scrollObserver.disconnect();
        comicState.scrollObserver = null;
    }

    const observer = new IntersectionObserver(
        (entries) => {
            let best = null;
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                const page = Number(entry.target.dataset.page || 0);
                if (!Number.isFinite(page) || page <= 0) return;
                if (!best || entry.intersectionRatio > best.ratio) {
                    best = { page, ratio: entry.intersectionRatio };
                }
            });
            if (best) {
                updateComicStatus(best.page);
            }
        },
        {
            root: scroller,
            threshold: [0.25, 0.5, 0.75],
        },
    );

    scroller.querySelectorAll(".comic-scroll-item[data-page]").forEach((node) => observer.observe(node));
    comicState.scrollObserver = observer;
}

function renderComicScrollPages(itemPath, totalPages, title) {
    let html = "";
    for (let page = 1; page <= totalPages; page += 1) {
        html += `
            <article class="comic-scroll-item" data-page="${page}">
                <img
                    data-src="${escapeHtml(comicPageUrl(itemPath, page))}"
                    alt="${escapeHtml(`${title} - 第${page}页`)}"
                    loading="lazy"
                    decoding="async"
                >
                <div class="comic-scroll-index">#${page}</div>
            </article>
        `;
    }
    return html;
}

function getComicPageNode(page) {
    const safePage = Math.min(comicState.totalPages, Math.max(1, Number(page) || 1));
    return document.querySelector(`.comic-scroll-item[data-page="${safePage}"]`);
}

export async function showComicPage(page) {
    if (!comicState.item || comicState.totalPages <= 0) return;

    const targetNode = getComicPageNode(page);
    if (!targetNode) return;
    targetNode.scrollIntoView({ behavior: "smooth", block: "start" });
    updateComicStatus(Number(targetNode.dataset.page || 1));

    const image = targetNode.querySelector("img[data-src]");
    if (image) {
        image.src = image.dataset.src;
        image.removeAttribute("data-src");
    }
}

export function stepComicPage(delta) {
    if (!comicState.item) return;
    void showComicPage(comicState.page + delta);
}

export async function openComicDetail(item) {
    showLoading("正在加载漫画...");
    try {
        const meta = await fetchJSON("/api/comic/metadata", { path: item.path });
        comicState.item = item;
        comicState.totalPages = Number(meta.page_count) || 0;
        comicState.page = 1;
        comicState.loadToken += 1;

        if (!comicState.totalPages) throw new Error("漫画没有可读取页面");

        openPlayerScreen(`
            <div class="comic-reader-shell">
                <header class="comic-reader-header">
                    <button class="mini-btn" data-action="player-close">返回媒体库</button>
                    <div class="comic-reader-meta">
                        <h2 class="player-title">${escapeHtml(item.name)}</h2>
                        <p class="player-subtitle">${escapeHtml(buildMeta(item))} · 共 ${comicState.totalPages} 页</p>
                    </div>
                    <div class="comic-reader-actions">
                        <button class="mini-btn" data-action="comic-prev" id="comicPrevBtn">上一页</button>
                        <button class="mini-btn" data-action="comic-next" id="comicNextBtn">下一页</button>
                        <label class="comic-page-jump">
                            <span>第</span>
                            <input type="number" id="comicPageInput" min="1" max="${comicState.totalPages}" value="1">
                            <span>/ ${comicState.totalPages}</span>
                        </label>
                        <button class="mini-btn" data-action="comic-jump">跳转</button>
                        <span class="media-meta" id="comicPageStatus">第 1 / ${comicState.totalPages} 页</span>
                    </div>
                </header>
                <section class="comic-reader-body" id="comicReaderScroller">
                    ${renderComicScrollPages(item.path, comicState.totalPages, item.name)}
                </section>
            </div>
        `);

        observeImages();
        setupComicScrollObserver();
        await showComicPage(1);
    } catch (error) {
        showError(`漫画加载失败: ${error.message}`);
    } finally {
        hideLoading();
    }
}
export async function openArchiveDetail(item) {
    openDetailModal(`
        <section class="detail-header">
            <h2 class="detail-title">${escapeHtml(item.name)}</h2>
            <div class="detail-meta"><span>${escapeHtml(buildMeta(item))}</span></div>
        </section>
        <div class="empty-panel">正在读取压缩包目录...</div>
    `);

    try {
        const payload = await fetchJSON("/api/archive/contents", { path: item.path });
        const entries = Array.isArray(payload.entries) ? payload.entries.filter((entry) => !entry.is_directory) : [];

        archiveState.path = item.path;
        archiveState.entries = entries;

        ui.detailBody.innerHTML = `
            <section class="detail-header">
                <h2 class="detail-title">${escapeHtml(item.name)}</h2>
                <div class="detail-meta"><span>${escapeHtml(buildMeta(item))}</span><span>${entries.length} 个文件</span></div>
            </section>
            ${entries.length ? `
                <div class="archive-list">
                    ${entries
                    .map((entry, index) => `
                            <div class="archive-item">
                                <div>${escapeHtml(entry.filename)}</div>
                                <div>${escapeHtml(formatSize(entry.size || 0))}</div>
                                <button class="mini-btn" data-action="archive-download" data-entry-index="${index}">下载</button>
                            </div>
                        `)
                    .join("")}
                </div>
            ` : `<div class="empty-panel">压缩包中没有文件</div>`}
        `;
    } catch (error) {
        ui.detailBody.innerHTML = `<div class="empty-panel">压缩包读取失败：${escapeHtml(error.message)}</div>`;
        showError(`压缩包读取失败：${error.message}`);
    }
}

