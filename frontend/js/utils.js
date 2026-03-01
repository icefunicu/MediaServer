export function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

export function formatSize(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function formatTime(timestamp) {
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

export function uniqueStrings(values) {
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

export function listToCsv(values) {
    return uniqueStrings(values).join(", ");
}

export function parseCsvList(text) {
    return uniqueStrings(String(text || "").replace(/，/g, ",").split(","));
}

export function containsIgnoreCase(list, value) {
    const target = String(value || "").trim().toLowerCase();
    if (!target) return false;
    return Array.isArray(list) && list.some((entry) => String(entry || "").trim().toLowerCase() === target);
}
