"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

const cache = new Map<string, Promise<unknown>>();

export function demoUrl(path: string): string {
  return `${BASE}/demo/${path}`;
}

export function fetchJson<T>(path: string): Promise<T> {
  const url = demoUrl(path);
  let p = cache.get(url);
  if (!p) {
    p = fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    });
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return p as Promise<T>;
}

export type Loadable<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; message: string };

/** Loads a JSON file of the export. `path` null means "nothing to load yet". */
export function useJson<T>(path: string | null): Loadable<T> {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    if (path === null) return;
    let live = true;
    setValue({ state: "loading" });
    fetchJson<T>(path)
      .then((data) => live && setValue({ state: "ready", data }))
      .catch((e: Error) => live && setValue({ state: "error", message: e.message }));
    return () => {
      live = false;
    };
  }, [path]);
  return value;
}
