"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useJson, type Loadable } from "@/lib/data";
import type { DemoIndex, TenantEntry } from "@/lib/types";

interface TenantState {
  tenants: TenantEntry[];
  tenantId: string | null;
  setTenantId: (id: string) => void;
  index: Loadable<DemoIndex>;
  /** Path of a file in the export of the selected tenant. */
  path: (file: string) => string | null;
}

const Ctx = createContext<TenantState | null>(null);
const KEY = "fdeops.tenant";

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const manifest = useJson<{ tenants: TenantEntry[] }>("manifest.json");
  const tenants = manifest.state === "ready" ? manifest.data.tenants : [];
  const [tenantId, setTenant] = useState<string | null>(null);

  useEffect(() => {
    if (!tenants.length || tenantId) return;
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(KEY);
    } catch {
      saved = null;
    }
    setTenant(tenants.some((t) => t.id === saved) ? saved : tenants[0]!.id);
  }, [tenants, tenantId]);

  const setTenantId = (id: string) => {
    setTenant(id);
    try {
      window.localStorage.setItem(KEY, id);
    } catch {
      /* private mode: the choice stays for this page only */
    }
  };

  const index = useJson<DemoIndex>(tenantId ? `${tenantId}/index.json` : null);
  const value = useMemo<TenantState>(
    () => ({
      tenants,
      tenantId,
      setTenantId,
      index,
      path: (file: string) => (tenantId ? `${tenantId}/${file}` : null),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tenants, tenantId, index],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTenant(): TenantState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTenant needs a TenantProvider");
  return v;
}
