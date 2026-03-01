import { FAVORITES_KEY, DEFAULT_UI_SETTINGS } from './config.js';

export const ui = {};

function loadFavorites() {
    try {
        const raw = localStorage.getItem(FAVORITES_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return new Set(Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : []);
    } catch (error) {
        return new Set();
    }
}

export const state = {
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

export function saveFavorites() {
    try {
        localStorage.setItem(FAVORITES_KEY, JSON.stringify(Array.from(state.favorites)));
    } catch (error) {
        // ignore
    }
}

export const seriesState = {
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
    currentItem: null,
    title: "",
    meta: "",
};

export const comicState = {
    item: null,
    totalPages: 0,
    page: 1,
    loadToken: 0,
    scrollObserver: null,
};

export const archiveState = {
    path: "",
    entries: [],
};
