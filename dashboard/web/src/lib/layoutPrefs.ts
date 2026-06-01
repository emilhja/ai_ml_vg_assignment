const STORAGE_WIDE = "vg-dashboard-wide-screen";

export function loadWideScreen(): boolean {
  try {
    return localStorage.getItem(STORAGE_WIDE) === "1";
  } catch {
    return false;
  }
}

export function saveWideScreen(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_WIDE, enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
}
