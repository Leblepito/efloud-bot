import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { getSiteOrigin, getSiteUrl, OG_IMAGE_PATH, SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";
import { I18nProvider } from "@/lib/i18n/context";
import { ConditionalExpertChat } from "@/components/ConditionalExpertChat";
import { ConditionalOnboarding } from "@/components/ConditionalOnboarding";
import { NotificationBanner } from "@/components/NotificationBanner";
import { JetBrains_Mono, Outfit } from "next/font/google";
import { cn } from "@/lib/utils";
import MobileNav from "@/components/layout/MobileNav";
import { AnalyticsLoader } from "@/components/AnalyticsLoader";
import { CookieConsent } from "@/components/CookieConsent";
import { PWAInstallPrompt } from "@/components/PWAInstallPrompt";

const inter = localFont({
  src: "./fonts/inter-var.woff2",
  variable: "--font-inter",
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});
const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

const siteUrl = getSiteOrigin();
const siteUrlStr = getSiteUrl();

const LOCALES = ["en", "tr", "th", "ar", "ru", "zh"] as const;

const alternateLanguages: Record<string, string> = {};
for (const locale of LOCALES) {
  alternateLanguages[locale] = `${siteUrlStr}/?lang=${locale}`;
}
alternateLanguages["x-default"] = `${siteUrlStr}/`;

export const metadata: Metadata = {
  metadataBase: siteUrl,
  title: {
    default: SITE_NAME,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  alternates: {
    canonical: "/",
    languages: alternateLanguages,
  },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
    url: "/",
    locale: "en_US",
    alternateLocale: ["tr_TR", "th_TH", "ar_AE", "ru_RU", "zh_CN"],
    images: [
      {
        url: OG_IMAGE_PATH,
        width: 1200,
        height: 630,
        alt: SITE_NAME,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
    images: [OG_IMAGE_PATH],
  },
  manifest: "/manifest.json",
  icons: {
    icon: "/brand/logo-mark.svg",
    apple: "/brand/logo-mark.svg",
  },
  appleWebApp: {
    capable: true,
    title: SITE_NAME,
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#000000",
  colorScheme: "dark light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    name: SITE_NAME,
    url: siteUrl.origin,
    applicationCategory: "FinanceApplication",
    operatingSystem: "Web",
    description: SITE_DESCRIPTION,
    image: `${siteUrl.origin}${OG_IMAGE_PATH}`,
    inLanguage: LOCALES.map((l) => l),
    offers: [
      {
        "@type": "Offer",
        name: "Free",
        price: "0",
        priceCurrency: "USD",
        description: "Basic crypto indicators and support/resistance",
      },
      {
        "@type": "Offer",
        name: "Pro",
        price: "39.99",
        priceCurrency: "USD",
        billingIncrement: "P1M",
        description: "Order Block, Breaker Block, Elliott Wave + 20 backtests/day",
      },
      {
        "@type": "Offer",
        name: "Premium",
        price: "59.99",
        priceCurrency: "USD",
        billingIncrement: "P1M",
        description: "All Pro features + 50 backtests/day",
      },
    ],
    potentialAction: {
      "@type": "SearchAction",
      target: `${siteUrl.origin}/indicators?symbol={search_term_string}`,
      "query-input": "required name=search_term_string",
    },
  };

  const orgJsonLd = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: siteUrl.origin,
    logo: {
      "@type": "ImageObject",
      url: `${siteUrl.origin}/brand/logo-mark.svg`,
      width: 512,
      height: 512,
    },
    description: SITE_DESCRIPTION,
    sameAs: [
      "https://x.com/u2algo",
      "https://instagram.com/u2algo",
      "https://www.youtube.com/@Leblepito",
      "https://facebook.com/u2algo",
    ],
    contactPoint: {
      "@type": "ContactPoint",
      contactType: "customer support",
      availableLanguage: ["English", "Turkish", "Thai", "Arabic", "Russian", "Chinese"],
    },
  };

  return (
    <html lang="en" data-scroll-behavior="smooth" className={cn("dark", "font-sans")} suppressHydrationWarning>
      <head>
        <link rel="preload" href="/fonts/inter-var.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preconnect" href="https://data-api.binance.vision" />
        <link rel="preconnect" href="https://stream.binance.com" />
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var t=localStorage.getItem('u2algo_theme');if(t==='light'){document.documentElement.classList.remove('dark');document.documentElement.classList.add('light')}}catch(e){}})()` }} />
      </head>
      <body className={`${inter.variable} ${jetbrainsMono.variable} ${outfit.variable} font-sans antialiased bg-background text-foreground pb-16 md:pb-0`}>
        <noscript>
          <div style={{ padding: '2rem', textAlign: 'center', fontFamily: 'system-ui', color: '#94a3b8', background: '#0a0a0f' }}>
            <h1 style={{ color: '#00f0ff', marginBottom: '1rem' }}>u2Algo</h1>
            <p>JavaScript is required to use u2Algo. Please enable JavaScript in your browser settings.</p>
          </div>
        </noscript>
        {/* Skip to main content — a11y */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[200] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[#00f0ff] focus:text-white focus:text-sm focus:font-semibold"
        >
          Skip to main content
        </a>
        <div className="fixed inset-0 z-[-1] opacity-100 pointer-events-none" style={{ background: 'radial-gradient(ellipse at top, var(--u2-surface-base), var(--u2-surface-base))' }}></div>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }} />
        <I18nProvider>
          <main id="main-content">
            {children}
          </main>
          <ConditionalExpertChat />
          <ConditionalOnboarding />
          <NotificationBanner />
          <MobileNav />
          <AnalyticsLoader />
          <CookieConsent />
          <PWAInstallPrompt />
        </I18nProvider>
      </body>
    </html>
  );
}
