const STORAGE_KEY = "sentinel_selected_site";
export const SITE_SELECTION_CHANGED_EVENT = "sentinel:selected-site-changed";

export function getStoredSelectedSite(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredSelectedSite(siteId: string | null): void {
  try {
    if (siteId) {
      sessionStorage.setItem(STORAGE_KEY, siteId);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(
      new CustomEvent(SITE_SELECTION_CHANGED_EVENT, {
        detail: { siteId },
      })
    );
  } catch {
    // Ignore storage failures in restricted environments.
  }
}
