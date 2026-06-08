"use client";

export type TabKey = "overview" | "positions" | "research" | "config";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "positions", label: "Positions" },
  { key: "research", label: "Research" },
  { key: "config", label: "Config" },
];

export function TabNav({ active, onChange }: { active: TabKey; onChange: (k: TabKey) => void }) {
  return (
    // Full-bleed second sticky bar, flush under the TopBar (sticky top-0, h-14, z-30).
    <div className="sticky top-14 z-20 border-b border-border bg-bg/85 backdrop-blur-md">
      <div
        role="tablist"
        aria-label="Dashboard sections"
        className="mx-auto flex max-w-7xl gap-1 px-6 py-2"
      >
        {TABS.map((t) => {
          const isActive = t.key === active;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={isActive}
              onClick={() => onChange(t.key)}
              className={`px-4 py-1.5 text-xs font-mono uppercase tracking-widest rounded-sm transition-colors ${
                isActive
                  ? "bg-accent-green/10 text-accent-green font-bold"
                  : "text-text-muted hover:text-text-secondary hover:bg-bg-surface"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
