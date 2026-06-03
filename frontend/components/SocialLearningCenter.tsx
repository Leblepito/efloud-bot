"use client";

import React, { useEffect, useState } from "react";

interface DoctrineItem {
  feed_id: string;
  source: "telegram" | "twitter";
  symbols: string[];
  timeframes: string[];
  bias: "bullish" | "bearish" | "neutral" | "educational";
  structure_terms: string[];
  zones: string[];
  liquidity_terms: string[];
  risk_terms: string[];
  levels: number[];
  setup_recipe: string[];
  confidence: number;
}

interface HypothesisItem {
  id: string;
  title: string;
  rationale: string;
  doctrine_tags: string[];
  candidate_config_patch: Record<string, any>;
  metrics_to_watch: string[];
  risk: string;
}

type Verdict = "PASS" | "WARN" | "REJECT" | "UNKNOWN";

interface ResearchRunEntry {
  verdict: Verdict;
  gates: Record<string, string>;
  doctrine_tags: string[];
  run_dir: string;
  run_date: string;
  deltas: Record<string, any>;
}

interface ResearchSnapshot {
  archive_count: number;
  doctrine: DoctrineItem[];
  hypotheses: HypothesisItem[];
  research_runs?: Record<string, ResearchRunEntry>;
  research_only: boolean;
}

const VERDICT_STYLES: Record<Verdict | "NONE", { label: string; cls: string }> = {
  PASS:    { label: "180D BACKTEST: PASS",   cls: "border-accent-green/30 bg-accent-green/10 text-accent-green" },
  WARN:    { label: "180D BACKTEST: WARN",   cls: "border-accent-amber/30 bg-accent-amber/10 text-accent-amber" },
  REJECT:  { label: "180D BACKTEST: REJECT", cls: "border-accent-red/30 bg-accent-red/10 text-accent-red" },
  UNKNOWN: { label: "180D BACKTEST: UNKNOWN", cls: "border-border bg-bg-surface text-text-muted" },
  NONE:    { label: "NO BACKTEST RUN YET",   cls: "border-border/40 bg-bg/40 text-text-muted" },
};

export function SocialLearningCenter() {
  const [data, setData] = useState<ResearchSnapshot | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [expandedHypothesis, setExpandedHypothesis] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/social/research-snapshot", { credentials: "include" })
      .then((res) => {
        if (res.status === 401) {
          setError("Unauthorized");
          return null;
        }
        return res.json();
      })
      .then((snapshot) => {
        if (snapshot) setData(snapshot);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Connection error");
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="border border-border bg-bg-elevated p-6 animate-pulse text-text-secondary font-mono text-xs">
        Efloud Sosyal Öğrenme Merkezi Yükleniyor...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="border border-accent-red/20 bg-accent-red/5 p-6 text-accent-red font-mono text-xs">
        Öğrenme Merkezi verileri yüklenemedi: {error || "Boş veri"}
      </div>
    );
  }

  const tagCounts: Record<string, number> = {};
  const categories: Record<string, string[]> = {
    structure: ["MSB", "BOS", "CHOCH", "HH", "HL", "LH", "LL", "MPA"],
    zones: ["FVG", "OTE", "Order Block"],
    liquidity: ["liquidity_sweep", "liquidity_target"],
    risk: ["risk_management"],
    recipe: ["market_structure_shift", "pullback", "fvg_reaction", "reversal_zone", "risk_first"],
  };

  data.doctrine.forEach((doc) => {
    doc.structure_terms.forEach((t) => { tagCounts[t] = (tagCounts[t] || 0) + 1; });
    doc.zones.forEach((z) => { tagCounts[z] = (tagCounts[z] || 0) + 1; });
    doc.liquidity_terms.forEach((l) => { tagCounts[l] = (tagCounts[l] || 0) + 1; });
    doc.risk_terms.forEach((r) => { tagCounts[r] = (tagCounts[r] || 0) + 1; });
    doc.setup_recipe.forEach((rcp) => { tagCounts[rcp] = (tagCounts[rcp] || 0) + 1; });
  });

  const filteredHypotheses = activeFilter
    ? data.hypotheses.filter((h) => h.doctrine_tags.includes(activeFilter))
    : data.hypotheses;

  const handleTagClick = (tag: string) => {
    setActiveFilter(activeFilter === tag ? null : tag);
  };

  const renderTagGroup = (label: string, tags: string[], transform?: (t: string) => string) => (
    <div className="space-y-2">
      <span className="text-[9px] text-text-muted uppercase tracking-widest block font-semibold">{label}</span>
      <div className="flex flex-wrap gap-1.5 pl-3">
        {tags.map((tag) => {
          const count = tagCounts[tag] || 0;
          if (count === 0) return null;
          const isSelected = activeFilter === tag;
          return (
            <button
              key={tag}
              onClick={() => handleTagClick(tag)}
              className={`px-2 py-0.5 text-[10px] flex items-center gap-1.5 transition-all duration-150 border whitespace-nowrap ${
                isSelected
                  ? "bg-accent-amber/15 text-accent-amber border-accent-amber/40 font-bold"
                  : "bg-bg border-border text-text-secondary hover:text-text-primary hover:border-border-strong"
              }`}
            >
              <span>{transform ? transform(tag) : tag}</span>
              <span className={`px-1 text-[8px] font-bold ${isSelected ? "bg-accent-amber/20 text-accent-amber" : "bg-bg-surface text-text-muted"}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="border border-border bg-bg-elevated overflow-hidden font-mono hover:border-border-strong transition-colors duration-300">
      {/* Title Header */}
      <div className="px-6 py-4 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4 bg-bg/85">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full bg-accent-amber dot-breathe" />
          <div>
            <h3 className="text-[11px] tracking-widest text-text-primary uppercase font-bold">
              Efloud Otonom Sosyal Öğrenme Merkezi (SMC)
            </h3>
            <span className="text-[9px] text-text-secondary uppercase">
              Sosyal Analiz &amp; TA Doktrini Hipotez Laboratuvarı
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="px-2 py-0.5 border border-border text-text-secondary text-[9px] font-bold">
            ARŞİV COUNT: <span className="text-text-primary tabular-nums">{data.archive_count}</span>
          </span>
          <span className="px-2.5 py-0.5 border border-accent-amber/20 bg-accent-amber/5 text-accent-amber text-[9px] font-bold tracking-wider">
            RESEARCH ONLY
          </span>
        </div>
      </div>

      {/* Safety Invariant */}
      <div className="mx-6 mt-6 p-4 border border-dashed border-accent-amber/30 bg-accent-amber/[0.02] border-l-2 border-l-accent-amber/60">
        <h4 className="text-[10px] font-bold text-accent-amber tracking-wider uppercase mb-1">
          GÜVENLİK PROTOKOLÜ: CANLI KONFİGÜRASYON DEĞİŞTİRİLMEZ
        </h4>
        <p className="text-[11px] text-text-secondary leading-relaxed">
          Bu panelde sunulan SMC (Smart Money Concepts) çıkarımları, otonom algoritmalar tarafından
          Telegram ve X akışlarından geriye dönük doctrine analizleri ile üretilen strateji hipotezleridir.
          Tüm candidate yaml yamaları tamamen izole bir araştırma hattında çalıştırılmakta olup, canlı bot emir
          verme motoruna veya üretim yapılandırma dosyalarına (<span className="text-text-primary">config.yaml</span>)
          kesinlikle doğrudan müdahale etmez.
        </p>
      </div>

      {/* Main Grid */}
      <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: doctrine tag cloud */}
        <div className="space-y-6 lg:border-r lg:border-border lg:pr-6">
          <div>
            <h4 className="text-[10px] uppercase tracking-wider text-text-secondary font-bold mb-3 flex items-center justify-between">
              <span>SMC DOKTRİN DAĞILIMI</span>
              {activeFilter && (
                <button
                  onClick={() => setActiveFilter(null)}
                  className="text-[9px] text-accent-amber border border-accent-amber/20 hover:bg-accent-amber/5 px-1.5 py-0.5 transition-colors"
                >
                  TEMİZLE [x]
                </button>
              )}
            </h4>
            <p className="text-[10px] text-text-muted mb-4 leading-normal">
              Gönderilerden çıkarılan deterministik SMC terimleri ve frekansları. Hipotezleri filtrelemek için bir etiket seçin.
            </p>
          </div>

          <div className="space-y-5">
            {renderTagGroup("├─ Market Yapısı Terimleri", categories.structure)}
            {renderTagGroup("├─ Arz & Talep Bölgeleri (Zones)", categories.zones)}
            {renderTagGroup("├─ Likidite Koşulları", categories.liquidity, (t) => t.replace("_", " "))}
            {renderTagGroup("├─ Formasyon Kurulumları", categories.recipe, (t) => t.replace(/_/g, " "))}
            {renderTagGroup("├─ Risk Yönetim Terimleri", categories.risk, (t) => t.replace("_", " "))}
          </div>
        </div>

        {/* Right: hypotheses */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-[10px] uppercase tracking-wider text-text-secondary font-bold">
              AKTİF STRATEJİ HİPOTEZLERİ &amp; CANDIDATE CONFIGS
            </h4>
            {activeFilter && (
              <span className="text-[10px] font-bold text-accent-amber">
                Filtre: <span className="underline">{activeFilter.replace(/_/g, " ").toUpperCase()}</span> ({filteredHypotheses.length} eşleşme)
              </span>
            )}
          </div>

          <div className="space-y-4 max-h-[580px] overflow-y-auto pr-1">
            {filteredHypotheses.length === 0 && (
              <div className="p-8 text-center text-text-muted text-xs border border-border border-dashed font-mono">
                Seçilen filtre kriterine uygun aktif araştırma hipotezi bulunmuyor.
              </div>
            )}

            {filteredHypotheses.map((hyp) => {
              const isExpanded = expandedHypothesis === hyp.id;
              const hasConfig = Object.keys(hyp.candidate_config_patch).length > 0;
              const run = data.research_runs?.[hyp.id];
              const verdictKey: Verdict | "NONE" = run ? run.verdict : "NONE";
              const verdictStyle = VERDICT_STYLES[verdictKey] ?? VERDICT_STYLES.UNKNOWN;

              return (
                <div
                  key={hyp.id}
                  className="border border-border bg-bg/50 p-5 hover:border-border-strong transition-colors duration-200 space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div>
                      <span className="text-[9px] uppercase tracking-widest text-text-muted font-bold block">ID: {hyp.id}</span>
                      <h5 className="text-xs font-bold text-text-primary mt-0.5">{hyp.title}</h5>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className="px-2 py-0.5 border border-accent-amber/20 bg-accent-amber/5 text-accent-amber text-[9px] font-bold uppercase">
                        {hyp.risk.replace("_", " ")}
                      </span>
                      <span
                        className={`px-2 py-0.5 border text-[9px] font-bold uppercase tracking-wider ${verdictStyle.cls}`}
                        title={run ? `Latest run: ${run.run_date} · ${Object.keys(run.gates).length} gates` : "No compare run linked to this hypothesis yet"}
                      >
                        {verdictStyle.label}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-text-secondary leading-relaxed bg-bg-surface/30 p-3 border-l-2 border-border">
                    {hyp.rationale}
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-[10px]">
                    <div>
                      <span className="text-[9px] uppercase tracking-wider text-text-muted block mb-1.5 font-bold">İlgili Doktrin Etiketleri</span>
                      <div className="flex flex-wrap gap-1">
                        {hyp.doctrine_tags.map((tag) => (
                          <span key={tag} className="px-1.5 py-0.5 bg-bg border border-border text-text-primary text-[9px] font-semibold">{tag}</span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <span className="text-[9px] uppercase tracking-wider text-text-muted block mb-1.5 font-bold">İzlenecek Başarı Metrikleri</span>
                      <div className="flex flex-wrap gap-1">
                        {hyp.metrics_to_watch.map((metric) => (
                          <span key={metric} className="px-1.5 py-0.5 bg-bg-surface text-text-secondary text-[9px] border border-border/40 font-mono">{metric.replace(/_/g, " ")}</span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-border pt-3">
                    <button
                      onClick={() => setExpandedHypothesis(isExpanded ? null : hyp.id)}
                      className="w-full flex items-center justify-between text-left text-[10px] text-text-secondary hover:text-text-primary font-bold transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <span className="text-accent-amber font-mono">&lt;/&gt;</span>
                        <span>CANDIDATE CONFIGURATION PATCH (YAML/JSON)</span>
                      </span>
                      <span className="text-text-muted font-mono text-[9px]">{isExpanded ? "[ collapse ]" : "[ expand ]"}</span>
                    </button>

                    {isExpanded && (
                      <div className="mt-3.5 space-y-2">
                        <p className="text-[9px] text-text-muted leading-normal pl-1">
                          Bu yama lokal backtest karşılaştırmalarında offline olarak simüle edilir. Canlı config dosyasını etkilemez.
                        </p>
                        {hasConfig ? (
                          <pre className="p-3 bg-bg border border-border text-accent-green text-[10.5px] overflow-x-auto leading-relaxed max-w-full font-mono font-bold">
                            {JSON.stringify(hyp.candidate_config_patch, null, 2)}
                          </pre>
                        ) : (
                          <pre className="p-3 bg-bg border border-border text-text-muted text-[10px] overflow-x-auto leading-normal font-mono">
                            {"// Bu hipotez için özel bir config parametre yaması tanımlanmamıştır.\n// Yalnızca işlem yaşam döngüsü telemetrisi ve PnL risk denetimi için izlenir."}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
