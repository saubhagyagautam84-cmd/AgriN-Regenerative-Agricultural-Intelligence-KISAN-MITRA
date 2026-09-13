import type { Metadata, Viewport } from "next";
import { Baloo_2, Noto_Sans, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n/I18nContext";
import { ThemeProvider } from "@/lib/theme/ThemeContext";
import { AuthProvider } from "@/lib/auth/AuthContext";
import LanguagePickerModal from "@/components/LanguagePickerModal";
import ChatBotWidget from "@/components/ChatBotWidget";

// Ported from kisan-sathi-frontend.html: Baloo 2 for headings/buttons/brand,
// Noto Sans + Noto Sans Devanagari for body text - both are required, not
// just Noto Sans, or Hindi (and every other Devanagari-script language here)
// falls back to a font with no Devanagari glyphs.
const baloo2 = Baloo_2({
  subsets: ["latin"],
  weight: ["500", "700", "800"],
  variable: "--font-baloo",
  display: "swap",
});
const notoSans = Noto_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-noto-sans",
  display: "swap",
});
const notoSansDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "700"],
  variable: "--font-noto-devanagari",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kisan Mitra — Farm Advisor",
  description:
    "Soil health, irrigation, crop and rotation advice for Indian farmers, from a PIN code and a crop name.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Most farmers will open this on a phone. Do not block pinch-zoom.
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      data-theme="light"
      className={`${baloo2.variable} ${notoSans.variable} ${notoSansDevanagari.variable}`}
    >
      <body className="min-h-screen">
        <ThemeProvider>
          <I18nProvider>
            <AuthProvider>
              <LanguagePickerModal />
              {children}
              <ChatBotWidget />
            </AuthProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
