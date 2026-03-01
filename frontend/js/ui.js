import { state, ui } from './store.js';

export function cacheElements() {
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

export function showLoading(message = "正在加载...") {
    const textNode = ui.loadingOverlay.querySelector("p");
    textNode.textContent = message;
    ui.loadingOverlay.classList.remove("hidden");
}

export function hideLoading() {
    ui.loadingOverlay.classList.add("hidden");
}

export function openPlayerScreen(htmlContent) {
    ui.playerScreenBody.innerHTML = htmlContent;
    ui.playerScreen.classList.remove("hidden");
    document.body.style.overflow = "hidden";
}

export function closePlayerScreen() {
    ui.playerScreen.classList.add("hidden");
    ui.playerScreen.classList.remove("web-fullscreen");
    ui.playerScreenBody.innerHTML = "";
    document.body.style.overflow = "";
}

export function openDetailModal(htmlContent) {
    ui.detailBody.innerHTML = htmlContent;
    ui.detailModal.classList.remove("hidden");
    ui.detailModal.scrollTop = 0;
}

export function closeDetailModal() {
    ui.detailModal.classList.add("hidden");
    ui.detailBody.innerHTML = "";
}

export function showError(message) {
    ui.errorMessage.textContent = message || "发生未知错误";
    ui.errorToast.classList.remove("hidden");
    window.setTimeout(() => ui.errorToast.classList.add("hidden"), 4500);
}

export function closeError() {
    ui.errorToast.classList.add("hidden");
}

// Global Image Observer for Lazy Loading
export let imageObserver = null;

export function observeImages() {
    if (!imageObserver && typeof IntersectionObserver !== "undefined") {
        imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.removeAttribute("data-src");
                    img.onload = () => img.classList.add("loaded");
                    observer.unobserve(img);
                }
            });
        }, {
            rootMargin: "50px 0px",
            threshold: 0.01
        });
    }

    if (!imageObserver) return;
    document.querySelectorAll("img[data-src]").forEach((img) => imageObserver.observe(img));
}

export function renderSkeleton() {
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
