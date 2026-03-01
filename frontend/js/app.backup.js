const API_BASE = "";
const APP_VERSION = "20260301-15";
const FAVORITES_KEY = "media_vault_favorites_v1";
const COMIC_EXTENSIONS = new Set([".cbz", ".cbr", ".zip", ".7z", ".rar"]);

const imageObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const img = entry.target;
            const src = img.getAttribute("data-src");
            if (src) {
                img.src = src;
                img.onload = () => img.classList.add("loaded");
                img.removeAttribute("data-src");
            }
            observer.unobserve(img);
        }
    });
}, { rootMargin: "100px 0px" });

function observeImages() {
    document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
    });
}

const VIEW_META = {
    home: { title: "首页", subtitle: "媒体总览" },
    movies: { title: "电影", subtitle: "电影资源" },
    tv: { title: "剧集", subtitle: "按系列分组" },
    anime: { title: "动漫", subtitle: "动漫剧集" },
    jdrama: { title: "日剧", subtitle: "日剧剧集" },
    music: { title: "音乐", subtitle: "音频资源" },
    photos: { title: "图片", subtitle: "图片资源" },
    comics: { title: "漫画", subtitle: "在线阅读" },
    archives: { title: "压缩包", subtitle: "浏览与提取" },
    recent: { title: "最近新增", subtitle: "最近更新内容" },
    favorites: { title: "我的收藏", subtitle: "收藏列表" },
    settings: { title: "设置", subtitle: "个性化与系统设置" },
    search: { title: "搜索结果", subtitle: "全库检索" },
};

const CATEGORY_LABEL = {
    movies: "电影",
    tv: "剧集",
    anime: "动漫",
    jdrama: "日剧",
    music: "音乐",
    photos: "图片",
    comics: "漫画",
    archives: "压缩包",
    others: "其他",
    recent: "最近新增",
};

const GENRE_LABEL = {
    anime: "动漫",
    anime_comic: "动漫漫画",
    jdrama: "日剧",
};

const DEFAULT_UI_SETTINGS = {
    home_hidden_roots: ["CM", "JMV"],
    home_hidden_categories: [],
    recent_hidden_roots: [],
    recent_hidden_categories: [],
    home_featured_enabled: true,
    default_layout: "grid",
    player_autoplay_default: true,
    group_tv_by_default: true,
    home_recent_limit: 18,
    category_page_limit: 500,
};

const ui = {};
const state = {
    view: "home",
    layout: "grid",
    query: "",
    items: [],
    featuredIndex: null,
    renderId: 0,
    overview: null,
    cache: new Map(),
    favorites: loadFavorites(),
    initialRefresh: true,
    settings: {
        media_root_directory: "",
        ui: { ...DEFAULT_UI_SETTINGS },
        available_filter_categories: ["movies", "tv", "music", "photos", "comics", "archives", "others"],
    },
};

const seriesState = {
    mode: "",
    episodes: [],
    sections: [],
    sectionId: "all",
    sectionPages: {},
    pageSize: 30,
    collapsedSections: new Set(),
    index: 0,
    autoplay: true,
    video: null,
    title: "",
    meta: "",
};

const comicState = {
    item: null,
    totalPages: 0,
    page: 1,
    loadToken: 0,
};

const archiveState = {
    path: "",
    entries: [],
};

let searchTimer = 0;

function loadFavorites() {
    try {
        const raw = localStorage.getItem(FAVORITES_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return new Set(Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : []);
    } catch (error) {
        return new Set();
    }
}

function saveFavorites() {
    try {
        localStorage.setItem(FAVORITES_KEY, JSON.stringify(Array.from(state.favorites)));
    } catch (error) {
        // ignore
    }
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function formatSize(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatTime(timestamp) {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0) return "-";
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function buildUrl(path, params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === "") return;
        query.set(key, String(value));
    });
    const text = query.toString();
    return text ? `${API_BASE}${path}?${text}` : `${API_BASE}${path}`;
}

async function fetchJSON(path, params = {}) {
    const response = await fetch(buildUrl(path, params));
    if (!response.ok) {
        let detail = `请求失败 (${response.status})`;
        try {
            const payload = await response.json();
            if (payload && payload.detail) detail = payload.detail;
        } catch (error) {
            // ignore
        }
        throw new Error(detail);
    }
    return response.json();
}

function showLoading(message = "正在加载...") {
    const textNode = ui.loadingOverlay.querySelector("p");
    textNode.textContent = message;
    ui.loadingOverlay.classList.remove("hidden");
}

function hideLoading() {
    ui.loadingOverlay.classList.add("hidden");
}

function showError(message) {
    ui.errorMessage.textContent = message || "发生未知错误";
    ui.errorToast.classList.remove("hidden");
    window.setTimeout(() => ui.errorToast.classList.add("hidden"), 4500);
}

function closeError() {
    ui.errorToast.classList.add("hidden");
}

function uniqueStrings(values) {
    if (!Array.isArray(values)) return [];
    const seen = new Set();
    const result = [];
    values.forEach((raw) => {
        const value = String(raw || "").trim();
        if (!value) return;
        const key = value.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        result.push(value);
    });
    return result;
}

function normalizeCategories(values) {
    const allowed = new Set(state.settings.available_filter_categories || []);
    return uniqueStrings(values).filter((name) => allowed.has(name));
}

function normalizeUiSettings(raw) {
    const merged = { ...DEFAULT_UI_SETTINGS };
    if (raw && typeof raw === "object") {
        Object.assign(merged, raw);
    }

    merged.home_hidden_roots = uniqueStrings(merged.home_hidden_roots);
    merged.recent_hidden_roots = uniqueStrings(merged.recent_hidden_roots);
    merged.home_hidden_categories = normalizeCategories(merged.home_hidden_categories);
    merged.recent_hidden_categories = normalizeCategories(merged.recent_hidden_categories);
    merged.default_layout = merged.default_layout === "list" ? "list" : "grid";
    merged.home_featured_enabled = Boolean(merged.home_featured_enabled);
    merged.player_autoplay_default = Boolean(merged.player_autoplay_default);
    merged.group_tv_by_default = Boolean(merged.group_tv_by_default);

    const homeRecent = Number(merged.home_recent_limit);
    merged.home_recent_limit = Number.isFinite(homeRecent)
        ? Math.max(1, Math.min(60, Math.floor(homeRecent)))
        : DEFAULT_UI_SETTINGS.home_recent_limit;

    const categoryLimit = Number(merged.category_page_limit);
    merged.category_page_limit = Number.isFinite(categoryLimit)
        ? Math.max(60, Math.min(500, Math.floor(categoryLimit)))
        : DEFAULT_UI_SETTINGS.category_page_limit;

    return merged;
}

function getUiSettings() {
    return normalizeUiSettings(state.settings.ui);
}

function listToCsv(values) {
    return uniqueStrings(values).join(", ");
}

function parseCsvList(text) {
    return uniqueStrings(String(text || "").replace(/，/g, ",").split(","));
}

function containsIgnoreCase(list, value) {
    const target = String(value || "").trim().toLowerCase();
    if (!target) return false;
    return Array.isArray(list) && list.some((entry) => String(entry || "").trim().toLowerCase() === target);
}

function isHiddenByScope(item, scope) {
    if (!item) return true;
    const uiSettings = getUiSettings();
    const hiddenRoots = scope === "recent" ? uiSettings.recent_hidden_roots : uiSettings.home_hidden_roots;
    const hiddenCategories = scope === "recent" ? uiSettings.recent_hidden_categories : uiSettings.home_hidden_categories;
    const rootFolder = String(item.root_folder || "").trim();
    const category = String(item.category || "").trim();
    if (rootFolder && containsIgnoreCase(hiddenRoots, rootFolder)) return true;
    if (category && containsIgnoreCase(hiddenCategories, category)) return true;
    return false;
}

function filterByScope(items, scope) {
    return Array.isArray(items) ? items.filter((item) => !isHiddenByScope(item, scope)) : [];
}

function getGroupTvFlag() {
    return getUiSettings().group_tv_by_default ? 1 : 0;
}

function getHomeRecentLimit() {
    return getUiSettings().home_recent_limit;
}

function getCategoryPageLimit() {
    return getUiSettings().category_page_limit;
}

function applyLayoutWithoutRender(layout) {
    state.layout = layout === "list" ? "list" : "grid";
    ui.viewGrid.classList.toggle("active", state.layout === "grid");
    ui.viewList.classList.toggle("active", state.layout === "list");
}

function applySettingsPayload(payload) {
    const available = Array.isArray(payload?.available_filter_categories)
        ? payload.available_filter_categories
        : state.settings.available_filter_categories;
    state.settings = {
        media_root_directory: String(payload?.media_root_directory || state.settings.media_root_directory || ""),
        available_filter_categories: uniqueStrings(available),
        ui: normalizeUiSettings(payload?.ui),
    };
}

async function fetchSettings() {
    const payload = await fetchJSON("/api/settings");
    applySettingsPayload(payload);
    applyLayoutWithoutRender(getUiSettings().default_layout);
    return state.settings;
}

async function saveSettings(payload) {
    const response = await fetch(buildUrl("/api/settings"), {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        let detail = `保存设置失败 (${response.status})`;
        try {
            const body = await response.json();
            if (body && body.detail) detail = body.detail;
        } catch (error) {
            // ignore
        }
        throw new Error(detail);
    }
    const data = await response.json();
    applySettingsPayload(data);
    applyLayoutWithoutRender(getUiSettings().default_layout);
    return state.settings;
}

function updateHeader(view, subtitle) {
    const meta = VIEW_META[view] || VIEW_META.home;
    ui.pageTitle.textContent = meta.title;
    ui.pageSubtitle.textContent = subtitle || meta.subtitle;
}

function setActiveNav(view) {
    document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.view === view);
    });
}

function setLayout(layout, options = {}) {
    if (layout !== "grid" && layout !== "list") return;
    if (state.layout === layout) return;
    state.layout = layout;
    ui.viewGrid.classList.toggle("active", layout === "grid");
    ui.viewList.classList.toggle("active", layout === "list");
    if (options.render !== false) {
        void renderView(false);
    }
}

async function switchView(view, refresh = false) {
    closePlayerScreen();
    const normalized = view in VIEW_META ? view : "home";
    state.view = normalized;
    setActiveNav(normalized);
    if (normalized !== "search") {
        updateHeader(normalized, VIEW_META[normalized].subtitle);
    }
    await renderView(refresh);
}

function handleSearchInput() {
    if (state.view === "settings") return;
    state.query = (ui.searchInput.value || "").trim();
    ui.clearSearch.classList.toggle("hidden", !state.query);

    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
        if (state.view === "home" && state.query) {
            void switchView("search");
            return;
        }
        if (state.view !== "home" || state.view === "search") {
            void renderView(false);
        }
    }, 280);
}

function handleSearchKeydown(event) {
    if (state.view === "settings") return;
    if (event.key !== "Enter") return;
    state.query = (ui.searchInput.value || "").trim();
    ui.clearSearch.classList.toggle("hidden", !state.query);

    if (!state.query) {
        if (state.view === "search") void switchView("home");
        return;
    }

    if (state.view === "home") {
        void switchView("search");
        return;
    }
    void renderView(false);
}

function clearSearch() {
    state.query = "";
    ui.searchInput.value = "";
    ui.clearSearch.classList.add("hidden");
    if (state.view === "settings") return;
    if (state.view === "search") {
        void switchView("home");
        return;
    }
    if (state.view !== "home") {
        void renderView(false);
    }
}

function cacheElements() {
    ui.sidebar = document.getElementById("sidebar");
    ui.sidebarToggle = document.getElementById("sidebarToggle");
    ui.pageTitle = document.getElementById("pageTitle");
    ui.pageSubtitle = document.getElementById("pageSubtitle");
    ui.searchInput = document.getElementById("searchInput");
    ui.clearSearch = document.getElementById("clearSearch");
    ui.viewGrid = document.getElementById("viewGrid");
    ui.viewList = document.getElementById("viewList");
    ui.contentArea = document.getElementById("contentArea");
    ui.playerScreen = document.getElementById("playerScreen");
    ui.playerScreenBody = document.getElementById("playerScreenBody");
    ui.detailModal = document.getElementById("detailModal");
    ui.detailBackdrop = document.getElementById("detailBackdrop");
    ui.detailClose = document.getElementById("detailClose");
    ui.detailBody = document.getElementById("detailBody");
    ui.loadingOverlay = document.getElementById("loadingOverlay");
    ui.errorToast = document.getElementById("errorToast");
    ui.errorMessage = document.getElementById("errorMessage");
    ui.errorClose = document.getElementById("errorClose");
    ui.storageBar = document.getElementById("storageBar");
    ui.storageMeta = document.getElementById("storageMeta");
}

function bindEvents() {
    document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
        button.addEventListener("click", () => void switchView(String(button.dataset.view || "home")));
    });

    ui.sidebarToggle.addEventListener("click", () => {
        ui.sidebar.classList.toggle("collapsed");
        ui.sidebarToggle.textContent = ui.sidebar.classList.contains("collapsed") ? "▶" : "◀";
    });

    ui.searchInput.addEventListener("input", handleSearchInput);
    ui.searchInput.addEventListener("keydown", handleSearchKeydown);
    ui.clearSearch.addEventListener("click", clearSearch);

    ui.viewGrid.addEventListener("click", () => setLayout("grid"));
    ui.viewList.addEventListener("click", () => setLayout("list"));

    ui.contentArea.addEventListener("click", onContentAreaClick);
    ui.playerScreen.addEventListener("click", onPlayerScreenClick);
    ui.playerScreen.addEventListener("change", onPlayerScreenChange);

    ui.detailClose.addEventListener("click", closeDetailModal);
    ui.detailBackdrop.addEventListener("click", closeDetailModal);
    ui.detailBody.addEventListener("click", onDetailBodyClick);
    ui.detailBody.addEventListener("change", onDetailBodyChange);
    ui.detailBody.addEventListener("keydown", onDetailBodyKeydown);

    ui.errorClose.addEventListener("click", closeError);
    window.addEventListener("keydown", onGlobalKeydown);
}

function renderSkeleton() {
    const isList = state.layout === "list";
    const count = 12; // Render 12 skeleton items
    const itemsHTML = Array(count).fill(0).map(() => {
        if (isList) {
            return `
                <article class="media-list-item skeleton-item">
                    <div class="media-cover skeleton-box" style="width: 126px;"></div>
                    <div class="media-list-content">
                        <div class="media-title skeleton-text w-60"></div>
                        <div class="media-meta skeleton-text w-40 mt-2"></div>
                        <div class="media-meta skeleton-text w-80 mt-2"></div>
                    </div>
                </article>
            `;
        }
        return `
            <article class="media-card skeleton-item">
                <div class="media-cover skeleton-box"></div>
                <div class="media-info">
                    <div class="media-title skeleton-text w-80"></div>
                    <div class="media-meta skeleton-text w-50 mt-2"></div>
                </div>
            </article>
        `;
    }).join("");

    return `
        <div class="${isList ? 'cards-list' : 'cards-grid'}">
            ${itemsHTML}
        </div>
    `;
}

async function renderView(forceRefresh = false) {
    const rid = ++state.renderId;

    if (forceRefresh) {
        state.overview = null;
        state.cache.clear();
    }

    if (state.view !== "settings" && state.view !== "favorites") {
        ui.contentArea.innerHTML = renderSkeleton();
    } else {
        showLoading("正在加载...");
    }

    try {
        if (state.view === "home") {
            await renderHome(rid, forceRefresh || state.initialRefresh);
        } else if (state.view === "settings") {
            await renderSettings(rid);
        } else if (state.view === "favorites") {
            await renderFavorites(rid, forceRefresh);
        } else {
            await renderCategory(rid, forceRefresh);
        }
    } catch (error) {
        if (rid !== state.renderId) return;
        ui.contentArea.innerHTML = `<div class="empty-panel">${escapeHtml(error.message)}</div>`;
        showError(error.message);
    } finally {
        if (rid === state.renderId) {
            hideLoading();
            state.initialRefresh = false;
        }
    }
}

function resetItems() {
    state.items = [];
    state.featuredIndex = null;
}

function pushItem(item) {
    state.items.push(item);
    return state.items.length - 1;
}

async function fetchOverview(forceRefresh = false) {
    if (state.overview && !forceRefresh) return state.overview;
    const payload = await fetchJSON("/api/library/overview", {
        refresh: forceRefresh ? 1 : 0,
        group_tv: getGroupTvFlag(),
        recent_limit: getHomeRecentLimit(),
    });
    state.overview = payload;
    return payload;
}

async function fetchCategoryAll(category, query = "", forceRefresh = false) {
    const normalizedQuery = String(query || "").trim();
    const key = `${category}::${normalizedQuery}`;
    if (!forceRefresh && state.cache.has(key)) {
        return state.cache.get(key).map((item) => ({ ...item }));
    }

    const sort = category === "recent" ? "recent" : "name";
    const limit = getCategoryPageLimit();
    let offset = 0;
    let total = Number.POSITIVE_INFINITY;
    const all = [];

    while (all.length < total) {
        const payload = await fetchJSON(`/api/library/category/${encodeURIComponent(category)}`, {
            query: normalizedQuery,
            sort,
            limit,
            offset,
            refresh: forceRefresh && offset === 0 ? 1 : 0,
            group_tv: getGroupTvFlag(),
        });
        const batch = Array.isArray(payload.items) ? payload.items : [];
        total = Number.isFinite(Number(payload.total)) ? Number(payload.total) : batch.length;
        if (!batch.length) break;

        all.push(...batch);
        offset += batch.length;
        if (batch.length < limit) break;
    }

    state.cache.set(key, all);
    return all.map((item) => ({ ...item }));
}

function updateStorage(overview) {
    const used = Number(overview.storage_used_bytes) || 0;
    const total = Number(overview.storage_total_bytes) || 0;
    if (total > 0) {
        const ratio = Math.min(100, Math.max(0, (used / total) * 100));
        ui.storageBar.style.width = `${ratio.toFixed(1)}%`;
        ui.storageMeta.textContent = `${formatSize(used)} / ${formatSize(total)} (${ratio.toFixed(1)}%)`;
        return;
    }
    ui.storageBar.style.width = "0%";
    ui.storageMeta.textContent = `已扫描 ${formatSize(used)}`;
}

async function renderHome(rid, forceRefresh) {
    const overview = await fetchOverview(forceRefresh);
    if (rid !== state.renderId) return;

    resetItems();
    updateStorage(overview);
    const uiSettings = getUiSettings();

    const recentItems = Array.isArray(overview.recent_items) ? overview.recent_items : [];
    const recents = filterByScope(recentItems, "home");

    const rawFeatured = overview.featured_item || null;
    const featured = !uiSettings.home_featured_enabled
        ? null
        : (!isHiddenByScope(rawFeatured, "home")
            ? rawFeatured
            : (recents[0] || null));

    if (featured) state.featuredIndex = pushItem(featured);
    const recentHtml = recents.length ? renderItems(recents) : `<div class="empty-panel">暂无最近新增媒体</div>`;

    ui.contentArea.innerHTML = `
        ${renderHero(featured)}
        ${renderStats(overview)}
        <section>
            <div class="section-header">
                <h3 class="section-title">最近新增</h3>
                <button class="section-action" data-action="goto-view" data-view="recent">查看全部</button>
            </div>
            ${recentHtml}
        </section>
    `;

    updateHeader("home", `共 ${Number(overview.total_items) || 0} 项，最近更新 ${formatTime(overview.generated_at)}`);
}

function renderHero(item) {
    if (!item) {
        return `
            <section class="hero-card">
                <div class="hero-content">
                    <span class="tag primary">MediaVault</span>
                    <h2 class="hero-title">媒体库已就绪</h2>
                    <p class="hero-text">进入左侧分类查看并点播你的本地媒体。</p>
                    <div class="hero-actions">
                        <button class="btn-primary" data-action="goto-view" data-view="recent">查看最近新增</button>
                    </div>
                </div>
            </section>
        `;
    }

    const cover = item.thumbnail
        ? `<div class="hero-media"><img src="${escapeHtml(item.thumbnail)}" alt="${escapeHtml(item.name)}"></div>`
        : "";

    return `
        <section class="hero-card">
            ${cover}
            <div class="hero-content">
                <span class="tag primary">推荐 · ${escapeHtml(CATEGORY_LABEL[item.category] || "媒体")}</span>
                <h2 class="hero-title">${escapeHtml(item.name)}</h2>
                <p class="hero-text">${escapeHtml(buildMeta(item))}</p>
                <div class="hero-actions">
                    <button class="btn-primary" data-action="open-featured">${escapeHtml(getOpenLabel(item))}</button>
                    <button class="btn-ghost" data-action="goto-view" data-view="recent">查看最近新增</button>
                </div>
            </div>
        </section>
    `;
    observeImages();
}

function renderStats(overview) {
    const counts = overview.counts || {};
    const cards = [
        ["总媒体数", Number(overview.total_items) || 0],
        ["电影", Number(counts.movies) || 0],
        ["剧集", Number(counts.tv) || 0],
        ["漫画", Number(counts.comics) || 0],
        ["压缩包", Number(counts.archives) || 0],
    ];
    return `
        <section class="stats-grid">
            ${cards
            .map(([label, value]) => `
                    <article class="stat-card">
                        <p class="stat-label">${escapeHtml(label)}</p>
                        <p class="stat-value">${escapeHtml(String(value))}</p>
                    </article>
                `)
            .join("")}
        </section>
    `;
}

async function renderFavorites(rid, forceRefresh) {
    const paths = Array.from(state.favorites);
    if (!paths.length) {
        if (rid !== state.renderId) return;
        resetItems();
        ui.contentArea.innerHTML = `<div class="empty-panel">你还没有收藏媒体</div>`;
        updateHeader("favorites", "点击卡片上的收藏按钮即可加入");
        return;
    }

    const all = await fetchCategoryAll("all", "", forceRefresh || state.initialRefresh);
    if (rid !== state.renderId) return;

    const map = new Map(all.map((item) => [item.path, item]));
    const picked = paths.map((path) => map.get(path)).filter(Boolean);

    resetItems();
    ui.contentArea.innerHTML = picked.length ? renderItems(picked) : `<div class="empty-panel">收藏内容不存在或已移动</div>`;
    observeImages();
    updateHeader("favorites", `共 ${picked.length} 项收藏`);
}

async function renderCategory(rid, forceRefresh) {
    const category = state.view === "search" ? "all" : state.view;
    const query = String(state.query || "").trim();
    const rawItems = await fetchCategoryAll(category, query, forceRefresh);
    if (rid !== state.renderId) return;

    resetItems();
    const items = state.view === "recent" ? filterByScope(rawItems, "recent") : rawItems;

    let body = "";
    if (state.view === "tv") {
        body = renderTvGroups(items);
    } else if (state.view === "anime") {
        body = items.length ? renderItems(items) : `<div class="empty-panel">暂无动漫内容</div>`;
    } else if (state.view === "jdrama") {
        body = items.length ? renderItems(items) : `<div class="empty-panel">暂无日剧内容</div>`;
    } else if (state.view === "comics") {
        body = renderComicGroups(items);
    } else {
        body = items.length ? renderItems(items) : `<div class="empty-panel">当前分类暂无内容</div>`;
    }

    ui.contentArea.innerHTML = body;
    observeImages();

    if (state.view === "search") {
        updateHeader("search", query ? `关键词“${query}” 共 ${items.length} 条` : "请输入关键词开始搜索");
    } else {
        const subtitle = query
            ? `${VIEW_META[state.view].subtitle} · 关键词“${query}” · ${items.length} 条`
            : `${VIEW_META[state.view].subtitle} · ${items.length} 条`;
        updateHeader(state.view, subtitle);
    }
}

function renderCategoryCheckboxGroup(name, selectedValues) {
    const selected = new Set(Array.isArray(selectedValues) ? selectedValues : []);
    const categories = Array.isArray(state.settings.available_filter_categories)
        ? state.settings.available_filter_categories
        : [];
    return `
        <div class="settings-checkbox-grid">
            ${categories.map((category) => `
                <label class="settings-check">
                    <input type="checkbox" name="${escapeHtml(name)}" value="${escapeHtml(category)}" ${selected.has(category) ? "checked" : ""}>
                    <span>${escapeHtml(CATEGORY_LABEL[category] || category)}</span>
                </label>
            `).join("")}
        </div>
    `;
}

async function renderSettings(rid) {
    if (!state.settings.media_root_directory) {
        await fetchSettings();
        if (rid !== state.renderId) return;
    }

    resetItems();
    const uiSettings = getUiSettings();
    const mediaRoot = state.settings.media_root_directory || "";

    ui.contentArea.innerHTML = `
        <section class="settings-page">
            <article class="settings-card">
                <h3 class="settings-title">媒体根目录</h3>
                <p class="settings-help">修改后将立即重新扫描媒体库。目录不存在时可勾选自动创建。</p>
                <label class="settings-field">
                    <span>根目录路径</span>
                    <input id="settingsMediaRoot" type="text" value="${escapeHtml(mediaRoot)}" placeholder="例如：E:\\\\NewFolder">
                </label>
                <label class="settings-check">
                    <input id="settingsCreateRoot" type="checkbox">
                    <span>目录不存在时自动创建</span>
                </label>
            </article>

            <article class="settings-card">
                <h3 class="settings-title">首页展示</h3>
                <label class="settings-check">
                    <input id="settingsHomeFeaturedEnabled" type="checkbox" ${uiSettings.home_featured_enabled ? "checked" : ""}>
                    <span>显示首页推荐横幅</span>
                </label>
                <label class="settings-field">
                    <span>首页隐藏根目录（英文逗号分隔）</span>
                    <input id="settingsHomeHiddenRoots" type="text" value="${escapeHtml(listToCsv(uiSettings.home_hidden_roots))}" placeholder="例如：CM, JMV">
                </label>
                <div class="settings-field">
                    <span>首页隐藏分类</span>
                    ${renderCategoryCheckboxGroup("home_hidden_categories", uiSettings.home_hidden_categories)}
                </div>
            </article>

            <article class="settings-card">
                <h3 class="settings-title">最近推荐展示</h3>
                <label class="settings-field">
                    <span>最近推荐隐藏根目录（英文逗号分隔）</span>
                    <input id="settingsRecentHiddenRoots" type="text" value="${escapeHtml(listToCsv(uiSettings.recent_hidden_roots))}" placeholder="例如：CM">
                </label>
                <div class="settings-field">
                    <span>最近推荐隐藏分类</span>
                    ${renderCategoryCheckboxGroup("recent_hidden_categories", uiSettings.recent_hidden_categories)}
                </div>
            </article>

            <article class="settings-card">
                <h3 class="settings-title">播放与浏览默认项</h3>
                <div class="settings-grid">
                    <label class="settings-field">
                        <span>默认布局</span>
                        <select id="settingsDefaultLayout">
                            <option value="grid" ${uiSettings.default_layout === "grid" ? "selected" : ""}>网格</option>
                            <option value="list" ${uiSettings.default_layout === "list" ? "selected" : ""}>列表</option>
                        </select>
                    </label>
                    <label class="settings-field">
                        <span>首页最近新增数量</span>
                        <input id="settingsHomeRecentLimit" type="number" min="1" max="60" value="${uiSettings.home_recent_limit}">
                    </label>
                    <label class="settings-field">
                        <span>分类分页批量大小</span>
                        <input id="settingsCategoryPageLimit" type="number" min="60" max="500" value="${uiSettings.category_page_limit}">
                    </label>
                </div>
                <div class="settings-toggle-row">
                    <label class="settings-check">
                        <input id="settingsPlayerAutoplayDefault" type="checkbox" ${uiSettings.player_autoplay_default ? "checked" : ""}>
                        <span>剧集播放器默认自动连播</span>
                    </label>
                    <label class="settings-check">
                        <input id="settingsGroupTvDefault" type="checkbox" ${uiSettings.group_tv_by_default ? "checked" : ""}>
                        <span>剧集默认按系列聚合</span>
                    </label>
                </div>
            </article>

            <div class="settings-actions">
                <button class="btn-primary" data-action="settings-save">保存设置</button>
                <button class="btn-ghost" data-action="settings-reset">恢复默认过滤</button>
                <button class="mini-btn" data-action="settings-reload">从服务器重载</button>
            </div>
        </section>
    `;

    updateHeader("settings", `当前媒体根目录：${mediaRoot || "-"}`);
}

function renderTvGroups(items) {
    const anime = [];
    const jdrama = [];
    const others = [];

    items.forEach((item) => {
        if (item.genre === "anime") {
            anime.push(item);
        } else if (item.genre === "jdrama" || item.root_folder === "JMV") {
            jdrama.push(item);
        } else {
            others.push(item);
        }
    });

    const blocks = [];
    if (anime.length) blocks.push(renderGroupSection("动漫系列", anime, "含蜡笔小新、齐木楠雄等"));
    if (jdrama.length) blocks.push(renderGroupSection("日剧", jdrama, "来自 JMV 目录"));
    if (others.length) blocks.push(renderGroupSection("其他剧集", others));

    return blocks.length ? blocks.join("") : `<div class="empty-panel">暂无剧集内容</div>`;
}

function renderComicGroups(items) {
    const cm = items.filter((item) => item.root_folder === "CM");
    const others = items.filter((item) => item.root_folder !== "CM");

    const blocks = [];
    if (cm.length) blocks.push(renderGroupSection("CM 动漫漫画库", cm, "支持在线分页阅读"));
    if (others.length) blocks.push(renderGroupSection("其他漫画", others));

    return blocks.length ? blocks.join("") : `<div class="empty-panel">暂无漫画内容</div>`;
}

function renderGroupSection(title, items, helper = "") {
    return `
        <section>
            <div class="section-header">
                <h3 class="section-title">${escapeHtml(title)}</h3>
                <span class="section-action">${items.length} 项</span>
            </div>
            ${helper ? `<p class="media-meta">${escapeHtml(helper)}</p>` : ""}
            ${renderItems(items)}
        </section>
    `;
}
function renderItems(items) {
    if (!items.length) {
        return `<div class="empty-panel">暂无可展示内容</div>`;
    }

    const containerClass = state.layout === "list" ? "cards-list" : "cards-grid";
    return `
        <div class="${containerClass}">
            ${items.map((item) => renderCard(item, pushItem(item))).join("")}
        </div>
    `;
}

function renderCard(item, index) {
    const actionLabel = getOpenLabel(item);
    const favorite = state.favorites.has(item.path);
    const favoriteLabel = favorite ? "取消收藏" : "收藏";

    const cover = item.thumbnail
        ? `<div class="${item.type === "photo" ? "media-cover photo" : "media-cover"}"><img data-src="${escapeHtml(item.thumbnail)}" alt="${escapeHtml(item.name)}"></div>`
        : `<div class="${item.type === "photo" ? "media-cover photo" : "media-cover"}"><div class="media-fallback">${escapeHtml(getIcon(item))}</div></div>`;

    if (state.layout === "list") {
        return `
            <article class="media-list-item" data-item-index="${index}">
                ${cover}
                <div class="media-list-content">
                    <div class="media-title">${escapeHtml(item.name)}</div>
                    <div class="media-meta">${escapeHtml(buildMeta(item))}</div>
                    <div class="media-meta">${escapeHtml(item.path || "")}</div>
                </div>
                <div class="media-actions">
                    <button class="mini-btn" data-action="open-item" data-item-index="${index}">${escapeHtml(actionLabel)}</button>
                    <button class="mini-btn" data-action="toggle-favorite" data-item-index="${index}">${escapeHtml(favoriteLabel)}</button>
                </div>
            </article>
        `;
    }

    return `
        <article class="media-card" data-item-index="${index}">
            ${cover}
            <div class="media-info">
                <div class="media-title">${escapeHtml(item.name)}</div>
                <div class="media-meta">${escapeHtml(buildMeta(item))}</div>
                <div class="media-actions">
                    <button class="mini-btn" data-action="open-item" data-item-index="${index}">${escapeHtml(actionLabel)}</button>
                    <button class="mini-btn" data-action="toggle-favorite" data-item-index="${index}">${escapeHtml(favoriteLabel)}</button>
                </div>
            </div>
        </article>
    `;
}

function getOpenLabel(item) {
    if (item.type === "tv_series") return "选集";
    if (isComicItem(item)) return "阅读";
    if (item.type === "video" || item.type === "music") return "播放";
    if (item.type === "archive") return "查看";
    return "打开";
}

function getIcon(item) {
    if (item.type === "tv_series") return "📺";
    if (item.type === "video") return "🎬";
    if (item.type === "music") return "🎵";
    if (item.type === "photo") return "🖼️";
    if (item.type === "comic") return "📚";
    if (item.type === "archive") return "🗜️";
    return "📄";
}

function buildMeta(item) {
    const parts = [];
    parts.push(item.type === "tv_series" ? "剧集系列" : (CATEGORY_LABEL[item.category] || "媒体"));

    if (item.genre && GENRE_LABEL[item.genre]) {
        parts.push(GENRE_LABEL[item.genre]);
    }

    if (item.type === "tv_series") {
        const sectionCount = Number(item.season_count) || (Array.isArray(item.sections) ? item.sections.length : 0);
        const episodeCount = Number(item.episode_count) || (Array.isArray(item.episodes) ? item.episodes.length : 0);
        if (sectionCount > 0) parts.push(`${sectionCount} 分区`);
        if (episodeCount > 0) parts.push(`${episodeCount} 集`);
    } else if (Number(item.size) > 0) {
        parts.push(formatSize(item.size));
    }

    if (item.root_folder) parts.push(item.root_folder);
    if (item.modified_time) parts.push(formatTime(item.modified_time));
    return parts.join(" · ");
}

function getCheckedValues(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`))
        .map((node) => String(node.value || "").trim())
        .filter(Boolean);
}

function readSettingsFromForm() {
    const mediaRootInput = document.getElementById("settingsMediaRoot");
    const createRootInput = document.getElementById("settingsCreateRoot");
    const homeFeaturedInput = document.getElementById("settingsHomeFeaturedEnabled");
    const homeRootsInput = document.getElementById("settingsHomeHiddenRoots");
    const recentRootsInput = document.getElementById("settingsRecentHiddenRoots");
    const defaultLayoutInput = document.getElementById("settingsDefaultLayout");
    const playerAutoplayInput = document.getElementById("settingsPlayerAutoplayDefault");
    const groupTvInput = document.getElementById("settingsGroupTvDefault");
    const homeRecentLimitInput = document.getElementById("settingsHomeRecentLimit");
    const categoryPageLimitInput = document.getElementById("settingsCategoryPageLimit");

    const uiPayload = {
        home_hidden_roots: parseCsvList(homeRootsInput?.value || ""),
        home_hidden_categories: getCheckedValues("home_hidden_categories"),
        recent_hidden_roots: parseCsvList(recentRootsInput?.value || ""),
        recent_hidden_categories: getCheckedValues("recent_hidden_categories"),
        home_featured_enabled: Boolean(homeFeaturedInput?.checked),
        default_layout: String(defaultLayoutInput?.value || "grid") === "list" ? "list" : "grid",
        player_autoplay_default: Boolean(playerAutoplayInput?.checked),
        group_tv_by_default: Boolean(groupTvInput?.checked),
        home_recent_limit: Number(homeRecentLimitInput?.value || DEFAULT_UI_SETTINGS.home_recent_limit),
        category_page_limit: Number(categoryPageLimitInput?.value || DEFAULT_UI_SETTINGS.category_page_limit),
    };

    const mediaRoot = String(mediaRootInput?.value || "").trim();
    const createMediaRoot = Boolean(createRootInput?.checked);
    return { uiPayload, mediaRoot, createMediaRoot };
}

function defaultUiSettings() {
    return normalizeUiSettings({ ...DEFAULT_UI_SETTINGS });
}

async function handleSaveSettings() {
    const { uiPayload, mediaRoot, createMediaRoot } = readSettingsFromForm();
    const currentRoot = String(state.settings.media_root_directory || "").trim();
    const payload = { ui: normalizeUiSettings(uiPayload) };

    if (mediaRoot && mediaRoot !== currentRoot) {
        payload.media_root_directory = mediaRoot;
        payload.create_media_root_if_missing = createMediaRoot;
    }

    await saveSettings(payload);
    state.overview = null;
    state.cache.clear();
    await renderView(true);
}

async function handleResetSettings() {
    const payload = { ui: defaultUiSettings() };
    await saveSettings(payload);
    state.overview = null;
    state.cache.clear();
    await renderView(true);
}

async function handleReloadSettings() {
    await fetchSettings();
    state.overview = null;
    state.cache.clear();
    await renderView(true);
}

function onContentAreaClick(event) {
    const actionNode = event.target.closest("[data-action]");
    if (actionNode) {
        const action = actionNode.dataset.action;
        if (action === "open-item") {
            openItemByIndex(Number(actionNode.dataset.itemIndex));
            return;
        }
        if (action === "toggle-favorite") {
            toggleFavorite(Number(actionNode.dataset.itemIndex));
            return;
        }
        if (action === "goto-view") {
            void switchView(String(actionNode.dataset.view || "home"));
            return;
        }
        if (action === "open-featured") {
            if (state.featuredIndex !== null) openItemByIndex(state.featuredIndex);
            return;
        }
        if (action === "settings-save") {
            showLoading("正在保存设置...");
            handleSaveSettings()
                .then(() => updateHeader("settings", "设置已保存并生效"))
                .catch((error) => showError(error.message))
                .finally(() => hideLoading());
            return;
        }
        if (action === "settings-reset") {
            showLoading("正在恢复默认设置...");
            handleResetSettings()
                .then(() => updateHeader("settings", "已恢复默认过滤设置"))
                .catch((error) => showError(error.message))
                .finally(() => hideLoading());
            return;
        }
        if (action === "settings-reload") {
            showLoading("正在重载设置...");
            handleReloadSettings()
                .then(() => updateHeader("settings", "已从服务器重新加载设置"))
                .catch((error) => showError(error.message))
                .finally(() => hideLoading());
            return;
        }
    }

    const card = event.target.closest("[data-item-index]");
    if (card) {
        openItemByIndex(Number(card.dataset.itemIndex));
    }
}

function toggleFavorite(index) {
    const item = state.items[index];
    if (!item || !item.path) return;

    if (state.favorites.has(item.path)) {
        state.favorites.delete(item.path);
    } else {
        state.favorites.add(item.path);
    }
    saveFavorites();
    void renderView(false);
}

function openItemByIndex(index) {
    if (!Number.isInteger(index) || index < 0 || index >= state.items.length) return;
    const item = state.items[index];
    void openItem(item);
}

function isComicItem(item) {
    if (!item) return false;
    const ext = String(item.extension || "").toLowerCase();
    if (item.type === "comic") return true;
    if (item.category === "comics" && COMIC_EXTENSIONS.has(ext)) return true;
    return item.type === "archive" && item.category === "comics" && COMIC_EXTENSIONS.has(ext);
}

function resetDetailStates() {
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
    seriesState.title = "";
    seriesState.meta = "";

    comicState.item = null;
    comicState.totalPages = 0;
    comicState.page = 1;

    archiveState.path = "";
    archiveState.entries = [];
}

function openPlayerScreen(html) {
    ui.playerScreenBody.innerHTML = html;
    ui.playerScreen.classList.remove("hidden");
}

function closePlayerScreen() {
    if (ui.playerScreen) {
        ui.playerScreen.classList.remove("web-fullscreen");
        ui.playerScreen.classList.add("hidden");
        ui.playerScreenBody.innerHTML = "";
    }
    if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => { });
    }
    resetPlayerVideoOnly();
}

function resetPlayerVideoOnly() {
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
    seriesState.title = "";
    seriesState.meta = "";
}

function openDetailModal(html) {
    ui.detailBody.innerHTML = html;
    ui.detailModal.classList.remove("hidden");
}

function closeDetailModal() {
    resetDetailStates();
    ui.detailModal.classList.add("hidden");
    ui.detailBody.innerHTML = "";
}

async function openItem(item) {
    if (!item) return;
    closePlayerScreen();
    resetDetailStates();

    if (item.type === "tv_series") {
        openSeriesDetail(item);
        return;
    }
    if (isComicItem(item)) {
        await openComicDetail(item);
        return;
    }
    if (item.type === "video") {
        openVideoDetail(item);
        return;
    }
    if (item.type === "music") {
        openMusicDetail(item);
        return;
    }
    if (item.type === "photo") {
        openPhotoDetail(item);
        return;
    }
    if (item.type === "archive") {
        await openArchiveDetail(item);
        return;
    }

    openGenericDetail(item);
}

const NATIVE_PLAYABLE_VIDEO_EXTENSIONS = new Set([".mp4", ".m4v", ".mov", ".webm", ".ogg"]);

function shouldForceCompatPlayback(item) {
    const extension = String(item?.extension || "").toLowerCase();
    if (!extension) return false;
    return !NATIVE_PLAYABLE_VIDEO_EXTENSIONS.has(extension);
}

function buildVideoUrl(item) {
    if (!item?.path) {
        return item?.stream_url || "";
    }
    return buildUrl("/api/video/stream", {
        path: item.path,
        ios_compat: shouldForceCompatPlayback(item) ? 1 : null,
    });
}

function openVideoDetail(item) {
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
                        <video id="playerVideo" controls playsinline preload="metadata" src="${escapeHtml(buildVideoUrl(item))}"></video>
                    </div>
                </section>
                <aside class="player-right">
                    <div class="player-right-header">视频信息</div>
                    <div class="player-media-info">
                        <p>${escapeHtml(item.name)}</p>
                        <p>${escapeHtml(buildMeta(item))}</p>
                        <p>${escapeHtml(item.path || "")}</p>
                    </div>
                </aside>
            </div>
        </div>
    `);

    seriesState.video = document.getElementById("playerVideo");
    if (seriesState.video) {
        const playResult = seriesState.video.play();
        if (playResult && typeof playResult.catch === "function") {
            playResult.catch(() => { });
        }
    }
}

function openMusicDetail(item) {
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

function openPhotoDetail(item) {
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

function normalizeEpisodes(series) {
    const episodes = Array.isArray(series.episodes) ? series.episodes.map((item) => ({ ...item })) : [];
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

function episodeLabel(episode, index) {
    const label = episode.episode_label || (Number.isFinite(Number(episode.episode_no)) ? `第${episode.episode_no}集` : `第${index + 1}集`);
    const fileName = String(episode.name || "").replace(/\.[^/.]+$/, "").trim();
    if (!fileName) return label;
    return `${label} · ${fileName.length > 20 ? `${fileName.slice(0, 20)}...` : fileName}`;
}
function buildSeriesSections(episodes) {
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

function getActiveSeriesSection() {
    if (!seriesState.sections.length) {
        return null;
    }
    const found = seriesState.sections.find((section) => section.id === seriesState.sectionId);
    if (found) {
        return found;
    }
    seriesState.sectionId = seriesState.sections[0].id;
    return seriesState.sections[0];
}

function getSeriesTotalPages(section) {
    return Math.max(1, Math.ceil(section.episodes.length / seriesState.pageSize));
}

function getSeriesPage(sectionId) {
    const rawPage = Number(seriesState.sectionPages[sectionId] || 1);
    if (!Number.isFinite(rawPage) || rawPage < 1) {
        return 1;
    }
    return Math.floor(rawPage);
}

function setSeriesPage(sectionId, page, totalPages) {
    const maxPage = Math.max(1, Number(totalPages) || 1);
    const normalized = Math.min(maxPage, Math.max(1, Math.floor(Number(page) || 1)));
    seriesState.sectionPages[sectionId] = normalized;
    return normalized;
}

function resolveSectionPage(section) {
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

function renderSeriesSectionPanel() {
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
            .map((episode) => `
                <button class="player-episode-item" data-action="player-play-episode" data-episode-index="${episode.__index}">
                    <div class="player-episode-thumb">${renderEpisodeThumb(episode)}</div>
                    <div class="player-episode-main">
                        <div class="player-episode-title">${escapeHtml(episodeLabel(episode, episode.__index))}</div>
                        <div class="player-episode-sub">${escapeHtml(episode.name || "")}</div>
                    </div>
                    <div class="player-episode-end">${episode.__index + 1}</div>
                </button>
            `)
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

function rerenderSeriesPanel() {
    const panel = document.getElementById("playerSeasonList");
    if (!panel) {
        return;
    }
    panel.innerHTML = renderSeriesSectionPanel();
    observeImages();
}

function updateSeriesEpisodeHighlight() {
    document.querySelectorAll(".player-episode-item[data-episode-index]").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.episodeIndex) === seriesState.index);
    });
    const activeNode = document.querySelector(`.player-episode-item[data-episode-index="${seriesState.index}"]`);
    if (activeNode) {
        activeNode.scrollIntoView({ block: "nearest" });
    }
}

function openSeriesDetail(series) {
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
                    <div class="player-now">
                        <strong id="playerNowPlaying">准备播放...</strong>
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

function playSeriesEpisode(index) {
    if (!seriesState.video || !seriesState.episodes.length) return;
    if (index < 0 || index >= seriesState.episodes.length) return;

    const episode = seriesState.episodes[index];
    const url = buildVideoUrl(episode);
    const expected = new URL(url, window.location.origin).href;

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

    if (seriesState.video.src !== expected) {
        seriesState.video.src = url;
    }

    const playResult = seriesState.video.play();
    if (playResult && typeof playResult.catch === "function") {
        playResult.catch(() => { });
    }

    const label = document.getElementById("playerNowPlaying");
    if (label) {
        label.textContent = `正在播放：${episodeLabel(episode, index)}`;
    }

    document.querySelectorAll(".player-episode-item[data-episode-index]").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.episodeIndex) === index);
    });

    const prevBtn = document.getElementById("playerPrevEpisode");
    const nextBtn = document.getElementById("playerNextEpisode");
    if (prevBtn) prevBtn.disabled = index <= 0;
    if (nextBtn) nextBtn.disabled = index >= seriesState.episodes.length - 1;
    updateSeriesEpisodeHighlight();
}

function onSeriesEnded() {
    if (!seriesState.autoplay) return;
    const nextIndex = seriesState.index + 1;
    if (nextIndex < seriesState.episodes.length) {
        playSeriesEpisode(nextIndex);
    }
}

function toggleWebFullscreen() {
    if (!ui.playerScreen) return;
    ui.playerScreen.classList.toggle("web-fullscreen");
}

async function toggleBrowserFullscreen() {
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

function onPlayerScreenClick(event) {
    const actionNode = event.target.closest("[data-action]");
    if (!actionNode) return;

    const action = actionNode.dataset.action;
    if (action === "player-close") {
        closePlayerScreen();
        return;
    }
    if (action === "player-prev") {
        playSeriesEpisode(seriesState.index - 1);
        return;
    }
    if (action === "player-next") {
        playSeriesEpisode(seriesState.index + 1);
        return;
    }
    if (action === "player-play-episode") {
        playSeriesEpisode(Number(actionNode.dataset.episodeIndex));
        return;
    }
    if (action === "player-switch-section") {
        const sectionId = String(actionNode.dataset.sectionId || "");
        if (!sectionId) return;
        const targetSection = seriesState.sections.find((section) => section.id === sectionId);
        if (!targetSection) return;
        seriesState.sectionId = sectionId;
        setSeriesPage(sectionId, getSeriesPage(sectionId), getSeriesTotalPages(targetSection));
        rerenderSeriesPanel();
        updateSeriesEpisodeHighlight();
        return;
    }
    if (action === "player-page-prev" || action === "player-page-next") {
        const activeSection = getActiveSeriesSection();
        if (!activeSection) return;
        const delta = action === "player-page-prev" ? -1 : 1;
        const nextPage = getSeriesPage(activeSection.id) + delta;
        setSeriesPage(activeSection.id, nextPage, getSeriesTotalPages(activeSection));
        rerenderSeriesPanel();
        updateSeriesEpisodeHighlight();
        return;
    }
    if (action === "player-web-fullscreen") {
        toggleWebFullscreen();
        return;
    }
    if (action === "player-browser-fullscreen") {
        void toggleBrowserFullscreen();
        return;
    }
    if (action === "toggle-season") {
        const sectionId = String(actionNode.dataset.sectionId || "");
        if (!sectionId) return;

        if (seriesState.collapsedSections.has(sectionId)) {
            seriesState.collapsedSections.delete(sectionId);
        } else {
            seriesState.collapsedSections.add(sectionId);
        }
        rerenderSeriesPanel();
        updateSeriesEpisodeHighlight();
    }
}

function onPlayerScreenChange(event) {
    if (event.target && event.target.id === "playerAutoplay") {
        seriesState.autoplay = Boolean(event.target.checked);
    }
}

async function openComicDetail(item) {
    showLoading("正在读取漫画...");
    try {
        const meta = await fetchJSON("/api/comic/metadata", { path: item.path });
        comicState.item = item;
        comicState.totalPages = Number(meta.page_count) || 0;
        comicState.page = 1;

        if (!comicState.totalPages) {
            throw new Error("漫画没有可读取页面");
        }

        openDetailModal(`
            <section class="detail-header">
                <h2 class="detail-title">${escapeHtml(item.name)}</h2>
                <div class="detail-meta"><span>${escapeHtml(buildMeta(item))}</span><span>${comicState.totalPages} 页</span></div>
            </section>
            <div class="detail-preview">
                <div class="comic-toolbar">
                    <button class="mini-btn" data-action="comic-prev" id="comicPrevBtn">上一页</button>
                    <button class="mini-btn" data-action="comic-next" id="comicNextBtn">下一页</button>
                    <span class="media-meta">第</span>
                    <input type="number" id="comicPageInput" min="1" max="${comicState.totalPages}" value="1">
                    <span class="media-meta">/ ${comicState.totalPages} 页</span>
                    <button class="mini-btn" data-action="comic-jump">跳转</button>
                    <span class="media-meta" id="comicPageStatus">加载中...</span>
                </div>
                <div class="comic-page-wrap">
                    <img id="comicPageImage" alt="漫画页" loading="lazy">
                </div>
            </div>
        `);

        await showComicPage(1);
    } catch (error) {
        showError(`漫画加载失败：${error.message}`);
    } finally {
        hideLoading();
    }
}

function comicPageUrl(path, page) {
    const dpr = window.devicePixelRatio || 1;
    const viewport = Math.max(window.innerWidth || 1280, 960);
    const maxWidth = Math.min(2800, Math.round(viewport * dpr * 1.2));
    return buildUrl("/api/comic/page", {
        path,
        page,
        max_width: maxWidth,
        quality: 86,
    });
}

async function showComicPage(page) {
    if (!comicState.item || comicState.totalPages <= 0) return;

    const target = Math.min(comicState.totalPages, Math.max(1, Number(page) || 1));
    const session = {
        token: ++comicState.loadToken,
        firstPage: target,
        tried: new Set(),
    };
    await showComicPageWithFallback(target, session);
}

async function showComicPageWithFallback(page, session) {
    if (!comicState.item || comicState.totalPages <= 0) return;
    if (!session || comicState.loadToken !== session.token) return;

    const target = Math.min(comicState.totalPages, Math.max(1, Number(page) || 1));
    if (session.tried.has(target)) return;
    session.tried.add(target);

    comicState.page = target;

    const image = document.getElementById("comicPageImage");
    const input = document.getElementById("comicPageInput");
    const status = document.getElementById("comicPageStatus");
    const prevBtn = document.getElementById("comicPrevBtn");
    const nextBtn = document.getElementById("comicNextBtn");

    if (!image || !input || !status) return;

    input.value = String(target);
    const skippedCount = session.tried.size - 1;
    if (skippedCount > 0) {
        status.textContent = `第 ${target} / ${comicState.totalPages} 页（已跳过 ${skippedCount} 张损坏页）`;
    } else {
        status.textContent = `第 ${target} / ${comicState.totalPages} 页`;
    }

    if (prevBtn) prevBtn.disabled = target <= 1;
    if (nextBtn) nextBtn.disabled = target >= comicState.totalPages;

    image.src = comicPageUrl(comicState.item.path, target);
    image.alt = `${comicState.item.name} - 第${target}页`;
    image.onerror = () => {
        if (comicState.loadToken !== session.token) {
            return;
        }

        const nextCandidate = findNextComicCandidate(target + 1, session.tried);
        if (nextCandidate !== null) {
            void showComicPageWithFallback(nextCandidate, session);
            return;
        }

        status.textContent = `从第 ${session.firstPage} 页起未找到可显示图片`;
        showError(`第 ${session.firstPage} 页及后续图片损坏，无法显示`);
    };

    const next = target + 1;
    if (next <= comicState.totalPages) {
        const preload = new Image();
        preload.src = comicPageUrl(comicState.item.path, next);
    }
}

function findNextComicCandidate(startPage, tried) {
    const begin = Math.max(1, Number(startPage) || 1);
    for (let page = begin; page <= comicState.totalPages; page += 1) {
        if (!tried.has(page)) {
            return page;
        }
    }
    return null;
}

function stepComicPage(delta) {
    if (!comicState.item) return;
    void showComicPage(comicState.page + delta);
}

async function openArchiveDetail(item) {
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

function openGenericDetail(item) {
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

function onDetailBodyClick(event) {
    const actionNode = event.target.closest("[data-action]");
    if (!actionNode) return;

    const action = actionNode.dataset.action;
    if (action === "comic-prev") {
        stepComicPage(-1);
        return;
    }
    if (action === "comic-next") {
        stepComicPage(1);
        return;
    }
    if (action === "comic-jump") {
        const input = document.getElementById("comicPageInput");
        if (input) void showComicPage(Number(input.value));
        return;
    }
    if (action === "archive-download") {
        const index = Number(actionNode.dataset.entryIndex);
        if (Number.isInteger(index) && index >= 0 && index < archiveState.entries.length) {
            const entry = archiveState.entries[index];
            const url = buildUrl("/api/archive/extract", {
                path: archiveState.path,
                entry: entry.filename,
            });
            window.open(url, "_blank", "noopener,noreferrer");
        }
    }
}

function onDetailBodyChange(event) {
    // Reserved for future controls.
}

function onDetailBodyKeydown(event) {
    if (!event.target || event.target.id !== "comicPageInput") return;
    if (event.key === "Enter") {
        event.preventDefault();
        void showComicPage(Number(event.target.value));
    }
}

function onGlobalKeydown(event) {
    if (event.key === "Escape" && ui.playerScreen && !ui.playerScreen.classList.contains("hidden")) {
        closePlayerScreen();
        return;
    }

    if (event.key === "Escape" && !ui.detailModal.classList.contains("hidden")) {
        closeDetailModal();
        return;
    }

    if (ui.playerScreen && !ui.playerScreen.classList.contains("hidden")) {
        const target = event.target;
        const tagName = String(target?.tagName || "").toLowerCase();
        const isTyping = tagName === "input" || tagName === "textarea" || Boolean(target?.isContentEditable);
        if (isTyping) return;

        if (event.key === "ArrowLeft") {
            event.preventDefault();
            playSeriesEpisode(seriesState.index - 1);
            return;
        }
        if (event.key === "ArrowRight") {
            event.preventDefault();
            playSeriesEpisode(seriesState.index + 1);
            return;
        }
    }

    if (ui.detailModal.classList.contains("hidden")) return;

    const target = event.target;
    const tagName = String(target?.tagName || "").toLowerCase();
    const isTyping = tagName === "input" || tagName === "textarea" || Boolean(target?.isContentEditable);

    if (!isTyping && comicState.item) {
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            stepComicPage(-1);
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            stepComicPage(1);
        }
    }
}

async function bootstrap() {
    cacheElements();
    bindEvents();

    try {
        await fetchSettings();
    } catch (error) {
        showError(`设置加载失败，已使用默认设置：${error.message}`);
        applyLayoutWithoutRender(DEFAULT_UI_SETTINGS.default_layout);
    }

    updateHeader("home", `${VIEW_META.home.subtitle} · v${APP_VERSION}`);
    await switchView("home", true);
}

document.addEventListener("DOMContentLoaded", () => {
    void bootstrap();
});
