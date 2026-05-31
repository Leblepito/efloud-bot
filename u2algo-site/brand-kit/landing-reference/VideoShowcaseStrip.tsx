"use client";

import { useState } from "react";
import { Play, Clock, X } from "lucide-react";
import { LANDING_VIDEOS, type VideoContent } from "@/lib/config/video-content";

/* ─── Video card data interface ────────────────────────── */
interface VideoCardUI extends VideoContent {
  tagColor?: string;
  gradientFrom?: string;
  gradientTo?: string;
}

/* ─── Fake waveform bars (deterministic) ──────────────── */
function WaveformBars({ seed }: { seed: number }) {
  const bars = Array.from({ length: 24 }, (_, i) => {
    const h = 15 + Math.sin(i * 0.9 + seed) * 45 + ((i * seed * 7) % 30);
    return Math.max(10, Math.min(95, h));
  });

  return (
    <div className="absolute bottom-3 left-3 right-3 flex items-end gap-[2px] h-5 opacity-20">
      {bars.map((h, i) => (
        <div
          key={i}
          className="flex-1 bg-white/50 rounded-full"
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  );
}

/* ─── Chart decoration in thumbnail ───────────────────── */
function ChartDecoration({ seed }: { seed: number }) {
  const points = Array.from({ length: 12 }, (_, i) => {
    const x = (i / 11) * 100;
    const y = 30 + Math.sin(i * 0.8 + seed) * 20 + ((i * seed * 3) % 15);
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg
      className="absolute inset-0 w-full h-full opacity-10"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      <polyline
        points={points}
        fill="none"
        stroke="rgba(0,240,255,0.6)"
        strokeWidth="0.8"
        vectorEffect="non-scaling-stroke"
      />
      {/* Grid dots */}
      {Array.from({ length: 20 }, (_, i) => (
        <circle
          key={i}
          cx={((i % 5) + 0.5) * 20}
          cy={(Math.floor(i / 5) + 0.5) * 25}
          r="0.4"
          fill="rgba(255,255,255,0.15)"
        />
      ))}
    </svg>
  );
}

/* ─── Single Video Card ───────────────────────────────── */
function VideoCardItem({
  video,
  index,
}: {
  video: VideoCardUI;
  index: number;
}) {
  const [showOverlay, setShowOverlay] = useState(false);
  const gradientFrom = video.gradientFrom || "from-slate-900/40";
  const gradientTo = video.gradientTo || "to-slate-800/40";
  const tagColor = video.tagColor || "text-slate-400 bg-white/5 border-white/10";

  return (
    <div
      className="
        group relative flex-shrink-0
        w-[280px] sm:w-auto
        snap-center
        rounded-xl border border-white/[0.06] bg-white/[0.03]
        overflow-hidden
        hover:border-[#00f0ff]/30 hover:shadow-[0_0_30px_rgba(0,240,255,0.08)]
        transition-all duration-300
        hover:scale-[1.03]
        cursor-pointer
      "
      onClick={() => setShowOverlay(true)}
    >
      {/* Thumbnail area — 16:9 */}
      <div className={`relative aspect-video bg-gradient-to-br ${gradientFrom} ${gradientTo} overflow-hidden`}>
        {/* Background chart decoration */}
        <ChartDecoration seed={index + 1} />

        {/* Waveform */}
        <WaveformBars seed={index + 1} />

        {/* Duration badge — top right */}
        <div className="absolute top-2.5 right-2.5 z-10 flex items-center gap-1 px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-sm border border-white/[0.08]">
          <Clock className="w-2.5 h-2.5 text-white/50" />
          <span className="text-[10px] font-mono text-white/70 font-medium">
            {video.duration}
          </span>
        </div>

        {/* Strategy tag — bottom left */}
        <div className="absolute bottom-2.5 left-2.5 z-10">
          <span
            className={`
              inline-flex items-center px-2 py-0.5 rounded-md
              text-[9px] font-bold uppercase tracking-wider
              border backdrop-blur-sm
              ${tagColor}
            `}
          >
            {video.tag}
          </span>
        </div>

        {/* Play button — center */}
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div
            className="
              w-12 h-12 rounded-full
              bg-white/[0.08] backdrop-blur-md border border-white/[0.15]
              flex items-center justify-center
              group-hover:scale-110 group-hover:bg-[#00f0ff]/15 group-hover:border-[#00f0ff]/30
              group-hover:shadow-[0_0_20px_rgba(0,240,255,0.2)]
              transition-all duration-300
            "
          >
            <Play className="w-5 h-5 text-white ml-0.5" fill="white" fillOpacity={0.9} />
          </div>
        </div>

        {/* Hover glow overlay */}
        <div className="absolute inset-0 bg-[#00f0ff]/[0.02] opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

        {/* Coming Soon overlay */}
        {showOverlay && (
          <div
            className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/80 backdrop-blur-sm"
            onClick={(e) => {
              e.stopPropagation();
              setShowOverlay(false);
            }}
          >
            <div className="relative">
              <div className="absolute -inset-4 rounded-full bg-[#00f0ff]/10 animate-pulse" />
              <Play className="w-8 h-8 text-[#00f0ff] relative" />
            </div>
            <span className="mt-3 text-sm font-display font-semibold text-white">
              Coming Soon
            </span>
            <span className="mt-1 text-[10px] text-slate-400">
              Video will be available shortly
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowOverlay(false);
              }}
              className="
                mt-3 flex items-center gap-1 px-3 py-1 rounded-lg
                text-[10px] text-white/50 border border-white/[0.08]
                hover:text-white/70 hover:border-white/[0.15]
                transition-all
              "
            >
              <X className="w-3 h-3" />
              Close
            </button>
          </div>
        )}
      </div>

      {/* Title */}
      <div className="px-3.5 py-3">
        <h3 className="text-[13px] font-display font-semibold text-white/80 leading-snug group-hover:text-white transition-colors duration-200">
          {video.title}
        </h3>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   VideoShowcaseStrip — horizontal video preview cards
   ═══════════════════════════════════════════════════════════ */
export function VideoShowcaseStrip() {
  if (LANDING_VIDEOS.length === 0) return null;

  return (
    <section className="py-12 sm:py-16 overflow-hidden bg-black">
      <div className="max-w-6xl mx-auto px-4">
        {/* Section header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
            <Play className="w-3 h-3" />
            Watch in Action
          </div>
          <h2 className="text-2xl sm:text-3xl font-display font-bold text-white/90 tracking-tight">
            See <span className="text-[#00f0ff]">Real Results</span>
          </h2>
        </div>

        {/* Desktop: 4-column grid */}
        <div className="hidden sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {LANDING_VIDEOS.map((video, i) => (
            <VideoCardItem key={i} video={video as any} index={i} />
          ))}
        </div>

        {/* Mobile: horizontal scroll with snap */}
        <div className="sm:hidden relative">
          {/* Fade edges */}
          <div className="absolute left-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-r from-black to-transparent pointer-events-none" />
          <div className="absolute right-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-l from-black to-transparent pointer-events-none" />

          <div
            className="
              flex gap-3 overflow-x-auto pb-4
              snap-x snap-mandatory
              scrollbar-hide
              -mx-4 px-4
            "
            style={{
              scrollbarWidth: "none",
              msOverflowStyle: "none",
            }}
          >
            {LANDING_VIDEOS.map((video, i) => (
              <VideoCardItem key={i} video={video as any} index={i} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
