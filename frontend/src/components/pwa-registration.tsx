"use client";

import { useEffect } from "react";

export function PwaRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => {
        // The app remains usable if browser policy prevents service workers.
      });
    }
  }, []);
  return null;
}
