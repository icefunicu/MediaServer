import { API_BASE, APP_VERSION, VIEW_META, CATEGORY_LABEL, GENRE_LABEL, DEFAULT_UI_SETTINGS } from './config.js';
import { state, seriesState, comicState, archiveState, saveFavorites, ui } from './store.js';
import { uniqueStrings, escapeHtml, formatTime, formatSize, listToCsv, parseCsvList, containsIgnoreCase } from './utils.js';
import { buildUrl, fetchJSON, normalizeCategories, normalizeUiSettings, getUiSettings, getGroupTvFlag, getHomeRecentLimit, getCategoryPageLimit, applySettingsPayload, fetchSettings, saveSettings } from './api.js';
import { cacheElements, showLoading, hideLoading, showError, closeError, imageObserver, observeImages, renderSkeleton, closePlayerScreen, closeDetailModal } from './ui.js';
import { updateHeader, setActiveNav, buildMeta, renderItems } from './views.js';
import { isComicItem, resetDetailStates, openGenericDetail, openVideoDetail, openMusicDetail, openPhotoDetail, openSeriesDetail, showComicPage, openComicDetail, openArchiveDetail, stepComicPage, toggleWebFullscreen, toggleBrowserFullscreen, playSeriesEpisode, rerenderSeriesPanel, updateSeriesEpisodeHighlight, setSeriesPage, getSeriesPage, getSeriesTotalPages, getActiveSeriesSection } from './player.js';

let searchTimer = 0;

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

function applyLayoutWithoutRender(layout) {
    state.layout = layout === "list" ? "list" : "grid";
    ui.viewGrid.classList.toggle("active", state.layout === "grid");
    ui.viewList.classList.toggle("active", state.layout === "list");
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
    ui.playerScreen.addEventListener("keydown", onPlayerScreenKeydown);

    ui.detailClose.addEventListener("click", closeDetailModal);
    ui.detailBackdrop.addEventListener("click", closeDetailModal);
    ui.detailBody.addEventListener("click", onDetailBodyClick);
    ui.detailBody.addEventListener("change", onDetailBodyChange);
    ui.detailBody.addEventListener("keydown", onDetailBodyKeydown);

    ui.errorClose.addEventListener("click", closeError);
    window.addEventListener("keydown", onGlobalKeydown);
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
    item.__appIndex = state.items.length;
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

function getOpenLabel(item) {
    if (item.type === "tv_series") return "选集";
    if (item.type === "comic") return "阅读";
    if (item.type === "video" || item.type === "music") return "播放";
    if (item.type === "archive") return "查看";
    return "打开";
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

    // Convert to item format expected by renderItems, adding __appIndex
    recents.forEach(item => pushItem(item));

    const recentHtml = recents.length ? renderItems(recents, state.layout) : `<div class="empty-panel">暂无最近新增媒体</div>`;

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

    observeImages();
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
        ? `<div class="hero-media"><img data-src="${escapeHtml(item.thumbnail)}" alt="${escapeHtml(item.name)}"></div>`
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
    picked.forEach(item => pushItem(item));
    ui.contentArea.innerHTML = picked.length ? renderItems(picked, state.layout) : `<div class="empty-panel">收藏内容不存在或已移动</div>`;
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
    items.forEach(item => pushItem(item));

    let body = "";
    if (state.view === "tv") {
        body = renderTvGroups(items);
    } else if (state.view === "anime") {
        body = items.length ? renderItems(items, state.layout) : `<div class="empty-panel">暂无动漫内容</div>`;
    } else if (state.view === "jdrama") {
        body = items.length ? renderItems(items, state.layout) : `<div class="empty-panel">暂无日剧内容</div>`;
    } else if (state.view === "comics") {
        body = renderComicGroups(items);
    } else {
        body = items.length ? renderItems(items, state.layout) : `<div class="empty-panel">当前分类暂无内容</div>`;
    }

    // Task T3 optimizations done inside renderItems mapping DOM Fragment logic, but we inject final HTML here

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
            ${renderItems(items, state.layout)}
        </section>
    `;
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


async function openItem(item) {
    if (!item) return;
    closePlayerScreen();
    resetDetailStates();

    // Debounce T3 logic applied globally due to async fetching
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

function onPlayerScreenClick(event) {
    const actionNode = event.target.closest("[data-action]");
    if (!actionNode) return;

    const action = actionNode.dataset.action;
    if (action === "player-close") {
        closePlayerScreen();
        resetDetailStates();
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
        return;
    }
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
    }
}

function onPlayerScreenChange(event) {
    if (event.target && event.target.id === "playerAutoplay") {
        seriesState.autoplay = Boolean(event.target.checked);
    }
}

function onPlayerScreenKeydown(event) {
    if (!event.target || event.target.id !== "comicPageInput") return;
    if (event.key === "Enter") {
        event.preventDefault();
        void showComicPage(Number(event.target.value));
    }
}

function onDetailBodyClick(event) {
    const actionNode = event.target.closest("[data-action]");
    if (!actionNode) return;

    const action = actionNode.dataset.action;
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
    // Reserved for future controls.
}

function onGlobalKeydown(event) {
    if (event.key === "Escape" && ui.playerScreen && !ui.playerScreen.classList.contains("hidden")) {
        closePlayerScreen();
        resetDetailStates();
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

        if (comicState.item) {
            if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                event.preventDefault();
                stepComicPage(-1);
                return;
            }
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                event.preventDefault();
                stepComicPage(1);
                return;
            }
        } else {
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
    bootstrap().catch(error => {
        showError(`启动失败：${error.message}`);
    });
});
