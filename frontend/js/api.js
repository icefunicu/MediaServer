import { API_BASE, DEFAULT_UI_SETTINGS } from './config.js';
import { state } from './store.js';
import { uniqueStrings } from './utils.js';

export function buildUrl(path, params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === "") return;
        query.set(key, String(value));
    });
    const text = query.toString();
    return text ? `${API_BASE}${path}?${text}` : `${API_BASE}${path}`;
}

export async function fetchJSON(path, params = {}) {
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

export function normalizeCategories(values) {
    const allowed = new Set(state.settings.available_filter_categories || []);
    return uniqueStrings(values).filter((name) => allowed.has(name));
}

export function normalizeUiSettings(raw) {
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

export function getUiSettings() {
    return normalizeUiSettings(state.settings.ui);
}

export function getGroupTvFlag() {
    return getUiSettings().group_tv_by_default ? 1 : 0;
}

export function getHomeRecentLimit() {
    return getUiSettings().home_recent_limit;
}

export function getCategoryPageLimit() {
    return getUiSettings().category_page_limit;
}

export function applySettingsPayload(payload) {
    const available = Array.isArray(payload?.available_filter_categories)
        ? payload.available_filter_categories
        : state.settings.available_filter_categories;
    state.settings = {
        media_root_directory: String(payload?.media_root_directory || state.settings.media_root_directory || ""),
        available_filter_categories: uniqueStrings(available),
        ui: normalizeUiSettings(payload?.ui),
    };
}

export async function fetchSettings() {
    const payload = await fetchJSON("/api/settings");
    applySettingsPayload(payload);
    return state.settings;
}

export async function saveSettings(payload) {
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
    return state.settings;
}
