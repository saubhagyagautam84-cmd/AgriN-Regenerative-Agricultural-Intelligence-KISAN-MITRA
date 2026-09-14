/**
 * Offline mode, part 1: the last successful /api/regenerate report, saved
 * so a farmer who already submitted once and comes back with no signal
 * still sees their last result instead of a dead "could not reach the
 * server" screen. (Part 2 - caching the app shell itself so the wizard's
 * static assets load offline too - is public/sw.js.)
 *
 * Deliberately just localStorage, not a runtime capability or a real
 * database: this is a single-viewer, best-effort convenience (see the
 * platform's own guidance on when localStorage is the right tool), not
 * state that needs to be shared or durable. Every read/write is wrapped in
 * try/catch - a private window, cleared site data, or a disabled storage
 * API must degrade to "no cached report", never crash the app.
 */

import type { FarmInput, RegenAnalyzeResponse } from "./types";

const STORAGE_KEY = "kisan-mitra:last-regen-report";

interface CachedReport {
  pincode: string;
  crop_name: string;
  saved_at: string;
  result: RegenAnalyzeResponse;
}

function cacheKey(farm: { pincode: string; crop_name: string }): string {
  return `${farm.pincode.trim()}::${farm.crop_name.trim().toLowerCase()}`;
}

export function saveLastReport(input: FarmInput, result: RegenAnalyzeResponse): void {
  try {
    const entry: CachedReport = {
      pincode: input.pincode,
      crop_name: input.crop_name,
      saved_at: new Date().toISOString(),
      result,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entry));
  } catch {
    // Storage unavailable/full/blocked - the report just won't be
    // recoverable offline next time. Never block the live result over this.
  }
}

/** Returns the cached report ONLY if it matches this exact farm+crop - never show a stale report for a different field. */
export function loadLastReport(input: FarmInput): { result: RegenAnalyzeResponse; savedAt: string } | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const entry = JSON.parse(raw) as CachedReport;
    if (cacheKey(entry) !== cacheKey(input)) return null;
    return { result: entry.result, savedAt: entry.saved_at };
  } catch {
    return null;
  }
}
