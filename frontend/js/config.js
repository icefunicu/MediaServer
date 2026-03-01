export const API_BASE = "";
export const APP_VERSION = "20260301-21";
export const FAVORITES_KEY = "media_vault_favorites_v1";
export const COMIC_EXTENSIONS = new Set([".cbz", ".cbr", ".zip", ".7z", ".rar"]);

export const VIEW_META = {
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

export const CATEGORY_LABEL = {
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

export const GENRE_LABEL = {
    anime: "动漫",
    anime_comic: "动漫漫画",
    jdrama: "日剧",
};

export const DEFAULT_UI_SETTINGS = {
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
