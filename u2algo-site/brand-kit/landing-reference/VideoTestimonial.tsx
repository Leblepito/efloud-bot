"use client";

import { useState, useMemo } from "react";
import { Play, Star } from "lucide-react";
/** Simple seeded PRNG (mulberry32). */
function seededRandom(seed: number): () => number {
  return () => { let t = (seed += 0x6d2b79f5); t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
import { ScrollReveal } from "@/components/shared/ScrollReveal";
import { PexelsImage } from "@/components/shared/PexelsImage";

interface VideoTestimonialProps {
  name: string;
  role: string;
  avatar: string;
  rating: number;
  quote: string;
  videoId?: string;
  thumbnailGradient?: string;
  imageQuery?: string;
}

const MOCK_TESTIMONIALS: VideoTestimonialProps[] = [
  {
    name: "Ahmet Y.",
    role: "Day Trader, Istanbul",
    avatar: "🇹🇷",
    rating: 5,
    quote: "u2Algo's AI signals saved me hours of chart analysis. The multi-agent consensus gives me confidence to take trades.",
    videoId: "demo-1",
    thumbnailGradient: "linear-gradient(135deg, #00f0ff15, #0080ff25)",
    imageQuery: "turkish businessman trading office dark",
  },
  {
    name: "Dmitri K.",
    role: "Crypto Investor, Moscow",
    avatar: "🇷🇺",
    rating: 5,
    quote: "The education hub and games made me understand Elliott Waves in a week. My win rate jumped from 45% to 68%.",
    videoId: "demo-2",
    thumbnailGradient: "linear-gradient(135deg, #00ff8815, #00f0ff25)",
    imageQuery: "russian investor cryptocurrency analysis",
  },
  {
    name: "Sarah L.",
    role: "Algo Developer, London",
    avatar: "🇬🇧",
    rating: 4,
    quote: "Best backtesting engine I've used. The strategy builder with AI code generation is incredibly powerful.",
    videoId: "demo-3",
    thumbnailGradient: "linear-gradient(135deg, #a855f715, #0080ff25)",
    imageQuery: "woman developer coding dark screen",
  },
];

function VideoCard({ testimonial }: { testimonial: VideoTestimonialProps }) {
  const [playing, setPlaying] = useState(false);
  const { name, role, avatar, rating, quote, thumbnailGradient, imageQuery } = testimonial;

  // Pre-compute waveform bar heights to avoid Math.random() during render
  const waveformHeights = useMemo(() => {
    const rng = seededRandom(name.length * 137 + rating);
    return Array.from({ length: 30 }, (_, i) => 20 + Math.sin(i * 0.8) * 60 + rng() * 20);
  }, [name, rating]);

  return (
    <div className="relative rounded-2xl border border-white/5 bg-slate-900/40 overflow-hidden group hover:border-white/[0.12] transition-all duration-300 shadow-[0_0_30px_-8px_rgba(0,0,0,0.5)]" style={{ background: "linear-gradient(180deg, rgba(15,20,40,0.8) 0%, rgba(5,10,20,0.95) 100%)" }}>
      {/* Thumbnail / Video */}
      <div className="relative aspect-video cursor-pointer" onClick={() => setPlaying(!playing)}>
        <PexelsImage
          query={imageQuery || "business professional portrait dark"}
          className="absolute inset-0 !rounded-none"
          aspect="video"
          fallbackGradient={thumbnailGradient || "linear-gradient(135deg, #00f0ff10, #0080ff20)"}
        />
        {!playing ? (
          <>
            {/* Play overlay */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-14 h-14 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center group-hover:scale-110 group-hover:bg-[#00f0ff]/20 group-hover:border-[#00f0ff]/30 transition-all duration-300">
                <Play className="w-6 h-6 text-white ml-0.5" fill="white" />
              </div>
            </div>
            {/* Waveform decoration */}
            <div className="absolute bottom-3 left-3 right-3 flex items-end gap-[2px] h-6 opacity-30">
              {waveformHeights.map((h, i) => (
                <div key={i} className="flex-1 bg-white/40 rounded-full" style={{ height: `${h}%` }} />
              ))}
            </div>
          </>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80">
            <div className="text-center">
              <div className="text-4xl mb-2">{avatar}</div>
              <p className="text-[11px] text-slate-400">Video preview</p>
              <button onClick={(e) => { e.stopPropagation(); setPlaying(false); }} className="mt-2 text-[10px] text-[#00f0ff] hover:text-[#00f0ff]/80">Close</button>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        <div className="flex items-center gap-0.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Star key={i} className="w-3 h-3" fill={i < rating ? "#ffaa00" : "transparent"} stroke={i < rating ? "#ffaa00" : "rgba(255,255,255,0.15)"} strokeWidth={1.5} />
          ))}
        </div>

        <p className="text-[13px] text-slate-300 leading-relaxed italic">&ldquo;{quote}&rdquo;</p>

        <div className="flex items-center gap-2.5 pt-2 border-t border-white/[0.04]">
          <div className="w-8 h-8 rounded-full bg-white/[0.06] border border-white/[0.08] flex items-center justify-center text-base">{avatar}</div>
          <div>
            <div className="text-xs font-bold text-white">{name}</div>
            <div className="text-[10px] text-slate-500">{role}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function VideoTestimonials() {
  return (
    <section className="py-24 px-4">
      <div className="max-w-6xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
              Testimonials
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-bold text-white/90 tracking-tight">
              Hear From Our <span className="text-[#00f0ff]">Traders</span>
            </h2>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {MOCK_TESTIMONIALS.map((t, i) => (
            <ScrollReveal key={i} delay={i * 100}>
              <VideoCard testimonial={t} />
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
