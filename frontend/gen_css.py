import os

css_content = """
:root {
    --primary-color: #3b82f6;
    --primary-hover: #60a5fa;
    --bg-color: #0b1120; /* Deep dark blue */
    --card-bg: #1e293b;
    --card-hover: #334155;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --border-color: rgba(255, 255, 255, 0.08);
    --success-color: #10b981;
    --error-color: #ef4444;
    --warning-color: #f59e0b;
    --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    --shadow-lg: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    --shadow-glow: 0 0 20px rgba(59, 130, 246, 0.35);
    --radius: 12px;
    --radius-lg: 16px;
    --radius-sm: 8px;
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background-color: var(--bg-color);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    overflow-x: hidden;
}

/* 滚动条美化 */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}
::-webkit-scrollbar-track {
    background: var(--bg-color);
}
::-webkit-scrollbar-thumb {
    background: #334155;
    border-radius: 5px;
}
::-webkit-scrollbar-thumb:hover {
    background: #475569;
}

/* Header Navbar (Glassmorphism) */
.header {
    background: rgba(11, 17, 32, 0.85);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-color);
    padding: 1rem 2rem;
    position: sticky;
    top: 0;
    z-index: 100;
}

.header-content {
    max-width: 1600px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
}

.logo {
    font-size: 1.5rem;
    font-weight: 700;
    cursor: pointer;
    color: var(--text-primary);
    user-select: none;
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: var(--transition);
}
.logo:hover {
    color: var(--primary-color);
    text-shadow: var(--shadow-glow);
}

.search-box {
    display: flex;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
    border-radius: 999px;
    padding: 0.25rem 0.25rem 0.25rem 1.25rem;
    transition: var(--transition);
    align-items: center;
}
.search-box:focus-within {
    border-color: var(--primary-color);
    background: rgba(0, 0, 0, 0.2);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.search-box input {
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-size: 0.95rem;
    width: 240px;
    outline: none;
    transition: width 0.3s ease;
}
.search-box input:focus {
    width: 320px;
}
.search-box input::placeholder {
    color: var(--text-secondary);
}

.btn-search {
    padding: 0.5rem 1.25rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 999px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 600;
    transition: var(--transition);
}
.btn-search:hover {
    background: var(--primary-hover);
    box-shadow: var(--shadow-glow);
}

.main-content {
    flex: 1;
    max-width: 1600px;
    margin: 0 auto;
    padding: 2rem;
    width: 100%;
}

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
    font-size: 1.05rem;
    font-weight: 500;
}

.breadcrumb-item {
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.2rem 0.6rem;
    border-radius: var(--radius-sm);
    transition: var(--transition);
}

.breadcrumb-item:hover {
    color: var(--text-primary);
    background: rgba(255, 255, 255, 0.1);
}
.breadcrumb-item:last-child {
    color: var(--primary-color);
    font-weight: 600;
}
.breadcrumb-item::after {
    content: "›";
    color: var(--text-secondary);
    margin-left: 0.8rem;
    font-size: 1.2rem;
    opacity: 0.5;
}
.breadcrumb-item:last-child::after {
    display: none;
}

/* File Cards Grid */
.file-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 1.5rem;
}

.file-item {
    background: transparent;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    group: relative;
    border-radius: var(--radius);
    transition: var(--transition);
}

.file-cover {
    width: 100%;
    aspect-ratio: 16 / 10;
    border-radius: var(--radius);
    background: var(--card-bg);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    margin-bottom: 0.75rem;
    border: 1px solid var(--border-color);
    transition: var(--transition);
}

.file-item:hover .file-cover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-lg);
    border-color: var(--primary-hover);
}

.file-icon-wrapper {
    font-size: 3.5rem;
    transition: var(--transition);
    z-index: 2;
}
.file-item:hover .file-icon-wrapper {
    transform: scale(1.1);
}

.video-thumbnail-img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    z-index: 1;
    transition: var(--transition);
}
.file-item:hover .video-thumbnail-img {
    transform: scale(1.05);
}

.file-hover-play {
    position: absolute;
    bottom: 10px;
    right: 10px;
    width: 36px;
    height: 36px;
    background: var(--primary-color);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 1.2rem;
    opacity: 0;
    transform: translateY(10px);
    transition: var(--transition);
    z-index: 3;
    padding-left: 4px; /* visually center play icon */
}
.file-item:hover .file-hover-play {
    opacity: 1;
    transform: translateY(0);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.5);
}

/* Background gradients for card types */
.file-type-video-cover {
    background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
}
.file-type-comic-cover {
    background: linear-gradient(135deg, #4c1d95 0%, #701a75 100%);
    aspect-ratio: 3 / 4; /* Comics look better tall */
}
.file-type-archive-cover {
    background: linear-gradient(135deg, #78350f 0%, #9a3412 100%);
}
.file-type-folder-cover {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
}

.file-meta {
    padding: 0 0.25rem;
}

.file-name {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-primary);
    word-break: break-word;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    margin-bottom: 0.25rem;
    line-height: 1.4;
    transition: color 0.2s;
}
.file-item:hover .file-name {
    color: var(--primary-hover);
}

.file-info {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.file-type-video { color: #a78bfa; }
.file-type-comic { color: #f472b6; }
.file-type-archive { color: #fbbf24; }
.file-type-folder { color: #94a3b8; }

/* Media Viewer UI */
.view-container {
    position: relative;
}

.media-viewer {
    background: #000;
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
    animation: scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes scaleIn {
    from { opacity: 0; transform: scale(0.98) translateY(10px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
}

.viewer-header {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 1.25rem 2rem;
    background: linear-gradient(to bottom, rgba(0,0,0,0.8), rgba(0,0,0,0));
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    z-index: 20;
    transition: opacity 0.3s;
}
.media-viewer:hover .viewer-header {
    opacity: 1;
}

.btn-back {
    padding: 0.5rem 1rem;
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(8px);
    color: white;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    cursor: pointer;
    font-size: 0.95rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: var(--transition);
}
.btn-back:hover {
    background: white;
    color: black;
}

.viewer-title {
    flex: 1;
    font-size: 1.25rem;
    font-weight: 600;
    text-shadow: 0 2px 4px rgba(0,0,0,0.8);
    color: white;
}

.viewer-content {
    min-height: 50vh;
    display: flex;
    flex-direction: column;
}

/* Video Layout Updates */
.video-view-layout {
    display: flex;
    gap: 0;
    height: 100%;
    align-items: stretch;
    background: #000;
}

.video-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    position: relative;
    background: #000;
}

.video-player {
    width: 100%;
    max-height: 80vh;
    background: #000;
    object-fit: contain;
}

.video-playlist {
    width: 320px;
    background: #0f172a;
    border-left: 1px solid var(--border-color);
    overflow-y: auto;
    max-height: 80vh;
}

.playlist-header {
    font-weight: 600;
    padding: 1.25rem;
    border-bottom: 1px solid var(--border-color);
    background: #1e293b;
    position: sticky;
    top: 0;
    font-size: 1.1rem;
    z-index: 5;
}

.playlist-item {
    padding: 1rem 1.25rem;
    cursor: pointer;
    font-size: 0.95rem;
    transition: var(--transition);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
}

.playlist-item:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
}

.playlist-item.active {
    background: rgba(59, 130, 246, 0.15);
    color: var(--primary-color);
    font-weight: 500;
    border-left: 4px solid var(--primary-color);
}

.video-controls-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.25rem;
    background: #0f172a;
    border-top: 1px solid var(--border-color);
}

.btn-video-ctrl {
    padding: 0.5rem 1rem;
    background: #1e293b;
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: var(--transition);
    font-size: 0.95rem;
    font-weight: 500;
}

.btn-video-ctrl:hover:not(:disabled) {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
}

.btn-video-ctrl:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.check-auto-play {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    color: var(--text-secondary);
    cursor: pointer;
    margin-left: auto;
    user-select: none;
}
.check-auto-play input {
    accent-color: var(--primary-color);
    width: 16px; height: 16px;
}

.video-countdown {
    position: absolute;
    bottom: 90px;
    right: 30px;
    background: rgba(0, 0, 0, 0.85);
    color: white;
    padding: 1rem 1.5rem;
    border-radius: var(--radius);
    border: 1px solid rgba(255,255,255,0.1);
    backdrop-filter: blur(8px);
    z-index: 10;
    font-size: 1.1rem;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes slideUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Comic Mode Overrides */
.media-viewer.comic-mode {
    background: var(--bg-color);
    box-shadow: none;
    border-radius: 0;
}
.media-viewer.comic-mode .viewer-header {
    background: rgba(11, 17, 32, 0.85);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-color);
    position: sticky;
}

.comic-reader-toolbar {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
}
.comic-progress-track {
    background: rgba(255,255,255,0.1);
}
.comic-progress-bar {
    background: var(--primary-color);
    box-shadow: 0 0 10px var(--primary-color);
}
.btn-reader-toggle {
    background: rgba(255,255,255,0.05);
    color: var(--text-primary);
    border-color: var(--border-color);
}
.btn-reader-toggle:hover {
    background: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
}
.comic-page-frame {
    background: #000;
    border-color: var(--border-color);
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
}
.comic-page-frame.is-active {
    border-color: var(--primary-color);
    box-shadow: 0 0 20px rgba(59, 130, 246, 0.2);
}

/* Error/Loading Utils */
.loading-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(11, 17, 32, 0.8);
    backdrop-filter: blur(4px);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    z-index: 1000;
}

.spinner {
    width: 60px;
    height: 60px;
    border: 4px solid rgba(255, 255, 255, 0.1);
    border-top-color: var(--primary-color);
    border-bottom-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 1s cubic-bezier(0.68, -0.55, 0.265, 1.55) infinite;
}

.loading-overlay p {
    color: var(--primary-color);
    margin-top: 1.5rem;
    font-size: 1.1rem;
    font-weight: 500;
    letter-spacing: 1px;
}

.error-toast {
    position: fixed;
    bottom: 2rem;
    left: 50%;
    transform: translateX(-50%);
    background: var(--error-color);
    color: white;
    padding: 1rem 2rem;
    border-radius: 999px;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    z-index: 1001;
    box-shadow: 0 10px 25px rgba(239, 68, 68, 0.4);
    font-weight: 500;
    animation: slideUp 0.3s ease;
}

.error-toast button {
    background: rgba(255, 255, 255, 0.2);
    color: white;
    border: none;
    padding: 0.4rem 1rem;
    border-radius: 999px;
    cursor: pointer;
    font-weight: bold;
    transition: var(--transition);
}
.error-toast button:hover {
    background: white;
    color: var(--error-color);
}

.hidden { display: none !important; }

.empty-state {
    grid-column: 1 / -1;
    text-align: center;
    padding: 5rem 2rem;
    color: var(--text-secondary);
    font-size: 1.2rem;
    background: rgba(255,255,255,0.02);
    border-radius: var(--radius-lg);
    border: 1px dashed var(--border-color);
}
.empty-state p { margin-bottom: 0.5rem; }

.footer {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
    background: var(--card-bg);
    border-top: 1px solid var(--border-color);
    margin-top: auto;
}

@media (max-width: 768px) {
    .header-content { flex-direction: column; align-items: stretch; }
    .search-box { width: 100%; border-radius: var(--radius-sm); }
    .search-box input { width: 100%; }
    .search-box input:focus { width: 100%; }
    .main-content { padding: 1rem; }
    
    .file-list { grid-template-columns: repeat(2, 1fr); gap: 1rem; }
    .file-cover { aspect-ratio: 1; }
    .file-icon-wrapper { font-size: 2.5rem; }
    
    .video-view-layout { flex-direction: column; }
    .video-playlist { width: 100%; max-height: 250px; border-left: none; border-top: 1px solid var(--border-color); }
    .video-countdown { bottom: auto; top: 80px; right: 10px; }
}

@media (max-width: 480px) {
    .file-list { grid-template-columns: 1fr; }
    .file-cover { aspect-ratio: 16/9; }
}
"""

with open(r"e:\Project\MediaServer\frontend\styles.css", "w", encoding="utf-8") as f:
    f.write(css_content)

print("styles.css generated successfully.")
