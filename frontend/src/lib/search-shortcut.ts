export function getSearchShortcut(platform?: string): string {
  return /Mac|iPhone|iPad|iPod/.test(platform ?? "") ? "⌘ K" : "Ctrl K";
}
