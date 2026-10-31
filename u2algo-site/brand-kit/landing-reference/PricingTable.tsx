"use client";

import Link from "next/link";
import { Check, X, Sparkles, Zap, Crown, Rocket } from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

/* ─── Plan definitions ──────────────────────────────── */
interface Plan {
  name: string;
  icon: typeof Zap;
  price: string;
  period: string;
  description: string;
  features: string[];
  highlighted: boolean;
  badge?: string;
  cta: string;
  ctaStyle: "ghost" | "gradient" | "gradient-outline";
}

const PLANS: Plan[] = [
  {
    name: "Free",
    icon: Zap,
    price: "$0",
    period: "",
    description: "Get started with the essentials. No credit card required.",
    features: [
      "1 paper trading bot",
      "10 backtests/month",
      "3 AI prompts/month",
      "Basic indicators",
      "Education hub access",
      "Community support",
    ],
    highlighted: false,
    cta: "Get Started Free",
    ctaStyle: "ghost",
  },
  {
    name: "Starter",
    icon: Rocket,
    price: "$25",
    period: "/wk",
    description: "For active traders ready to go live with their first bot.",
    features: [
      "1 live trading bot",
      "100 backtests/month",
      "20 AI prompts/month",
      "Elliott Wave + SMC",
      "15min signal delay",
      "Email support",
    ],
    highlighted: false,
    cta: "Start Trading",
    ctaStyle: "ghost",
  },
  {
    name: "Pro",
    icon: Sparkles,
    price: "$100",
    period: "/mo",
    description: "Full power trading with unlimited everything.",
    features: [
      "5 live trading bots",
      "Unlimited backtests & alerts",
      "Unlimited AI prompts",
      "5min signal delay",
      "Marketplace buy & sell",
      "Priority support",
    ],
    highlighted: true,
    badge: "Most Popular",
    cta: "Go Pro",
    ctaStyle: "gradient",
  },
  {
    name: "Premium",
    icon: Crown,
    price: "$200",
    period: "/mo",
    description: "Institutional grade. Copy trading, API access, dedicated support.",
    features: [
      "Everything in Pro",
      "10 live trading bots",
      "Real-time signals",
      "Copy trading",
      "API access",
      "Dedicated support",
    ],
    highlighted: false,
    badge: "Best Value",
    cta: "Go Premium",
    ctaStyle: "gradient-outline",
  },
];

/* ─── Feature comparison matrix ─────────────────────── */
interface ComparisonRow {
  feature: string;
  free: boolean | string;
  starter: boolean | string;
  pro: boolean | string;
  premium: boolean | string;
}

const COMPARISON: ComparisonRow[] = [
  { feature: "Live trading bots", free: false, starter: "1", pro: "5", premium: "10" },
  { feature: "Backtests / month", free: "10", starter: "100", pro: "Unlimited", premium: "Unlimited" },
  { feature: "AI prompts / month", free: "3", starter: "20", pro: "Unlimited", premium: "Unlimited" },
  { feature: "Alerts", free: "5", starter: "25", pro: "Unlimited", premium: "Unlimited" },
  { feature: "Signal delay", free: "1 hour", starter: "15 min", pro: "5 min", premium: "Real-time" },
  { feature: "Elliott Wave + SMC", free: false, starter: true, pro: true, premium: true },
  { feature: "AI Strategy Builder", free: false, starter: true, pro: true, premium: true },
  { feature: "Marketplace", free: false, starter: false, pro: true, premium: true },
  { feature: "Copy trading", free: false, starter: false, pro: false, premium: true },
  { feature: "API access", free: false, starter: false, pro: false, premium: true },
  { feature: "Education hub", free: true, starter: true, pro: true, premium: true },
];

/* ─── CTA button renderer ───────────────────────────── */
function PricingButton({
  cta,
  style,
  highlighted: _highlighted,
}: {
  cta: string;
  style: Plan["ctaStyle"];
  highlighted: boolean;
}) {
  const base =
    "w-full inline-flex items-center justify-center gap-2 px-6 py-3.5 font-semibold text-sm rounded-xl transition-all duration-300 active:scale-[0.97]";

  if (style === "gradient") {
    return (
      <Link
        href="/pricing"
        className={`${base} bg-gradient-to-r from-[#00f0ff] to-[#0080ff] text-white shadow-lg shadow-[#00f0ff]/25 hover:shadow-xl hover:shadow-[#00f0ff]/35 hover:brightness-110`}
      >
        {cta}
      </Link>
    );
  }

  if (style === "gradient-outline") {
    return (
      <Link
        href="/pricing"
        className={`${base} relative text-white border border-white/[0.15] bg-white/[0.04] hover:bg-white/[0.08] hover:border-[#00f0ff]/30`}
      >
        <span
          className="absolute inset-0 rounded-xl opacity-0 hover:opacity-100 transition-opacity duration-300 pointer-events-none"
          style={{
            background:
              "linear-gradient(135deg, rgba(0,240,255,0.06) 0%, rgba(0,128,255,0.06) 100%)",
          }}
          aria-hidden="true"
        />
        <span className="relative">{cta}</span>
      </Link>
    );
  }

  /* Ghost */
  return (
    <Link
      href="/pricing"
      className={`${base} border border-white/[0.1] bg-white/[0.04] text-slate-200 hover:bg-white/[0.08] hover:border-white/[0.15]`}
    >
      {cta}
    </Link>
  );
}

/* ─── Comparison cell ───────────────────────────────── */
function ComparisonCell({ value }: { value: boolean | string }) {
  if (typeof value === "string") {
    return (
      <span className="text-sm text-slate-300 font-medium">{value}</span>
    );
  }
  if (value) {
    return (
      <Check className="w-4.5 h-4.5 text-[#00ff88] mx-auto" strokeWidth={2} />
    );
  }
  return (
    <X className="w-4.5 h-4.5 text-slate-400 mx-auto" strokeWidth={1.5} />
  );
}

/* ─── Individual plan card ──────────────────────────── */
function PlanCard({ plan, delay }: { plan: Plan; delay: number }) {
  const Icon = plan.icon;

  return (
    <ScrollReveal delay={delay}>
      <div
        className={`
          relative flex flex-col h-full p-6 sm:p-8 rounded-2xl
          transition-all duration-300
          ${
            plan.highlighted
              ? "bg-white/[0.05] border-2 border-[#00f0ff]/30 shadow-xl shadow-[#00f0ff]/10 scale-[1.02] lg:scale-105"
              : "bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.12]"
          }
        `}
      >
        {/* Most Popular badge */}
        {plan.badge && (
          <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 z-10">
            <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-gradient-to-r from-[#00f0ff] to-[#0080ff] text-white text-xs font-semibold shadow-lg shadow-[#00f0ff]/25">
              <Sparkles className="w-3 h-3" />
              {plan.badge}
            </span>
          </div>
        )}

        {/* Glow behind highlighted card */}
        {plan.highlighted && (
          <div
            className="absolute inset-0 rounded-2xl pointer-events-none"
            style={{
              background:
                "radial-gradient(ellipse at top center, rgba(0,240,255,0.06) 0%, transparent 60%)",
            }}
            aria-hidden="true"
          />
        )}

        {/* Plan header */}
        <div className="relative">
          <div className="flex items-center gap-2.5 mb-4">
            <div
              className={`flex items-center justify-center w-9 h-9 rounded-lg border ${
                plan.highlighted
                  ? "bg-[#00f0ff]/15 border-[#00f0ff]/25 text-[#00f0ff]"
                  : "bg-white/[0.04] border-white/[0.08] text-slate-400"
              }`}
            >
              <Icon className="w-4.5 h-4.5" strokeWidth={1.5} />
            </div>
            <h3 className="text-white font-display font-semibold text-xl">
              {plan.name}
            </h3>
          </div>

          {/* Price */}
          <div className="flex items-baseline gap-1 mb-2">
            <span className="text-white font-display font-bold text-4xl sm:text-5xl tracking-tight">
              {plan.price}
            </span>
            <span className="text-slate-500 text-sm font-medium">
              {plan.period}
            </span>
          </div>

          <p className="text-slate-400 text-sm leading-relaxed mb-6">
            {plan.description}
          </p>
        </div>

        {/* CTA button */}
        <PricingButton
          cta={plan.cta}
          style={plan.ctaStyle}
          highlighted={plan.highlighted}
        />

        {/* Divider */}
        <div className="my-6 h-px bg-white/[0.06]" />

        {/* Feature list */}
        <ul className="relative flex flex-col gap-3 flex-1">
          {plan.features.map((feature) => (
            <li key={feature} className="flex items-start gap-2.5">
              <Check
                className={`w-4 h-4 mt-0.5 shrink-0 ${
                  plan.highlighted ? "text-[#00f0ff]" : "text-[#00ff88]"
                }`}
                strokeWidth={2}
              />
              <span className="text-sm text-slate-300 leading-snug">
                {feature}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </ScrollReveal>
  );
}

/* ─── Comparison table ──────────────────────────────── */
function ComparisonGrid() {
  return (
    <ScrollReveal delay={400}>
      <div className="mt-16 sm:mt-24">
        <h3 className="text-white font-display font-semibold text-xl sm:text-2xl text-center mb-8">
          Compare Plans
        </h3>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            {/* Table header */}
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="text-left py-3 px-4 text-slate-400 text-sm font-medium w-1/3">
                  Feature
                </th>
                <th className="text-center py-3 px-4 text-slate-400 text-sm font-medium">
                  Free
                </th>
                <th className="text-center py-3 px-4 text-slate-400 text-sm font-medium">
                  Starter
                </th>
                <th className="text-center py-3 px-4 text-sm font-medium">
                  <span className="text-[#00f0ff]">Pro</span>
                </th>
                <th className="text-center py-3 px-4 text-sm font-medium">
                  <span className="text-[#ffaa00]">Premium</span>
                </th>
              </tr>
            </thead>

            {/* Table body */}
            <tbody>
              {COMPARISON.map((row, i) => (
                <tr
                  key={row.feature}
                  className={`border-b border-white/[0.04] ${
                    i % 2 === 0 ? "bg-white/[0.01]" : ""
                  }`}
                >
                  <td className="py-3 px-4 text-sm text-slate-300">
                    {row.feature}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <ComparisonCell value={row.free} />
                  </td>
                  <td className="py-3 px-4 text-center">
                    <ComparisonCell value={row.starter} />
                  </td>
                  <td className="py-3 px-4 text-center">
                    <ComparisonCell value={row.pro} />
                  </td>
                  <td className="py-3 px-4 text-center">
                    <ComparisonCell value={row.premium} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </ScrollReveal>
  );
}

/* ─── Main pricing section ──────────────────────────── */
export function PricingTable() {
  return (
    <section className="relative py-20 sm:py-28 px-4 overflow-hidden">
      {/* Subtle top separator */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.12) 30%, rgba(0,128,255,0.12) 70%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      {/* Background ambient glow */}
      <div
        className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[700px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,240,255,0.03) 0%, transparent 60%)",
        }}
        aria-hidden="true"
      />

      <div className="relative mx-auto max-w-6xl">
        {/* Section header */}
        <ScrollReveal>
          <div className="text-center mb-14 sm:mb-18">
            <h2 className="font-display font-bold text-3xl sm:text-4xl md:text-5xl text-white leading-tight">
              Simple, Transparent{" "}
              <span
                className="bg-clip-text text-transparent"
                style={{
                  backgroundImage:
                    "linear-gradient(135deg, #00f0ff 0%, #0080ff 100%)",
                }}
              >
                Pricing
              </span>
            </h2>
            <p className="mt-4 sm:mt-5 text-slate-400 text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
              Start free, upgrade when you are ready. No hidden fees, cancel
              anytime.
            </p>
          </div>
        </ScrollReveal>

        {/* Plan cards: 1 col mobile, 3 col desktop */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 lg:gap-5 items-stretch lg:items-center">
          {PLANS.map((plan, i) => (
            <PlanCard key={plan.name} plan={plan} delay={i * 120} />
          ))}
        </div>

        {/* Feature comparison table */}
        <ComparisonGrid />
      </div>

      {/* Subtle bottom separator */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.08) 30%, rgba(0,128,255,0.08) 70%, transparent 100%)",
        }}
        aria-hidden="true"
      />
    </section>
  );
}
