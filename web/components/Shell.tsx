"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { TenantProvider, useTenant } from "./TenantContext";

const NAV = [
  { href: "/", label: "Release log" },
  { href: "/releases/", label: "Release gates" },
  { href: "/runs/", label: "Comparisons" },
  { href: "/traces/", label: "Traces" },
  { href: "/diagnosis/", label: "Diagnosis" },
  { href: "/roadmap/", label: "Roadmap" },
  { href: "/impact/", label: "Business value" },
];

function Rail() {
  const pathname = usePathname() || "/";
  const { index } = useTenant();
  return (
    <aside className="rail">
      <Link href="/" className="brand" aria-label="FDE-Ops-AI home">
        <span className="brand-mark">FDE·OPS·AI</span>
        <span className="brand-sub">Release-to-service for AI agents</span>
      </Link>
      <nav className="nav" aria-label="Sections">
        {NAV.map((item) => {
          const current = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className="nav-link"
              aria-current={current ? "page" : undefined}
            >
              <span className="nav-lamp" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="rail-foot">
        {index.state === "ready" && (
          <>
            <span className="mono">fdeops {index.data.fdeops_version}</span>
            <span>Exported {new Date(index.data.generated_at).toLocaleString()}</span>
          </>
        )}
        <span>All companies and data are fictional.</span>
      </div>
    </aside>
  );
}

function TopBar() {
  const { tenants, tenantId, setTenantId, index } = useTenant();
  const provenance = index.state === "ready" ? index.data.provenance : [];
  return (
    <header className="topbar">
      <div className="tenant-switch" role="group" aria-label="Tenant">
        {tenants.map((t) => (
          <button
            key={t.id}
            type="button"
            aria-pressed={t.id === tenantId}
            onClick={() => setTenantId(t.id)}
            title={`${t.display_name} · ${t.pack} pack`}
          >
            {t.display_name.replace(" (fictional)", "")}
          </button>
        ))}
      </div>
      {provenance.includes("pipeline-test") && (
        <span className="provenance" role="note">
          <strong>Pipeline test</strong>
          A rule-based stand-in model made these numbers. They test the platform, not an agent.
        </span>
      )}
    </header>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <TenantProvider>
      <div className="shell">
        <Rail />
        <div className="main">
          <TopBar />
          <main className="page">{children}</main>
        </div>
      </div>
    </TenantProvider>
  );
}
