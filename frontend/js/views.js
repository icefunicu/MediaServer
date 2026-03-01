import { state, seriesState, comicState, archiveState, ui } from './store.js';
import { escapeHtml, formatTime, formatSize } from './utils.js';
import { getUiSettings, buildUrl } from './api.js';
import { observeImages } from './ui.js';

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

export function updateHeader(view, subtitle) {
    const meta = VIEW_META[view] || VIEW_META.home;
    ui.pageTitle.textContent = meta.title;
    ui.pageSubtitle.textContent = subtitle || meta.subtitle;
}

export function setActiveNav(view) {
    document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.view === view);
    });
}

function getOpenLabel(item) {
    if (item.type === "tv_series") return "选集";
    if (item.type === "comic") return "阅读"; // Simplified logic for demo
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

export function buildMeta(item) {
    const parts = [];
    parts.push(item.type === "tv_series" ? "剧集系列" : (CATEGORY_LABEL[item.category] || "媒体"));

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

export function renderItems(items, layout) {
    if (!items.length) {
        return `<div class="empty-panel">暂无可展示内容</div>`;
    }

    const containerClass = layout === "list" ? "cards-list" : "cards-grid";
    // We construct the HTML string for injection as it's typically faster in modern V8.
    // Chunking the array using map over join is optimal, no DocumentFragment needed if we just innerHTML once.
    // Since this function returns a string to be injected via innerHTML, we provide early escape.
    return `
        <div class="${containerClass}">
            ${items.map((item, index) => renderCard(item, item.__appIndex, layout)).join("")}
        </div>
    `;
}

function renderCard(item, index, layout) {
    const actionLabel = getOpenLabel(item);
    const favorite = state.favorites.has(item.path);
    const favoriteLabel = favorite ? "取消收藏" : "收藏";

    // Task T4 Lazy load setup
    const cover = item.thumbnail
        ? `<div class="${item.type === "photo" ? "media-cover photo" : "media-cover"}"><img data-src="${escapeHtml(item.thumbnail)}" alt="${escapeHtml(item.name)}"></div>`
        : `<div class="${item.type === "photo" ? "media-cover photo" : "media-cover"}"><div class="media-fallback">${escapeHtml(getIcon(item))}</div></div>`;

    if (layout === "list") {
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
