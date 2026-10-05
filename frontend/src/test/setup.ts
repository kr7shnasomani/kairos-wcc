import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL auto-cleanup only registers itself when vitest runs with globals: true.
// This project does not, so renders accumulated across tests in a file and
// getBy* queries could match leftovers from an earlier case.
afterEach(cleanup);

// jsdom has no IntersectionObserver; the landing page's scroll reveal uses it.
// Never fires, which is the right default: components must render their content
// before any observer callback, not because of one.
window.IntersectionObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds = [];
} as unknown as typeof window.IntersectionObserver;

// jsdom has no matchMedia; useReducedMotion (lib/motion.ts) requires it.
window.matchMedia = ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;
