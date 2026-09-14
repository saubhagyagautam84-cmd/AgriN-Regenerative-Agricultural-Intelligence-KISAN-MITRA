"use client";

/** Registers public/sw.js (app-shell caching) once, client-side only. Renders nothing. */

import { useEffect } from "react";

export default function PwaRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Offline-shell caching just won't be available this session - the
      // rest of the app (including the lib/offlineCache.ts report fallback)
      // works fine without it.
    });
  }, []);

  return null;
}
