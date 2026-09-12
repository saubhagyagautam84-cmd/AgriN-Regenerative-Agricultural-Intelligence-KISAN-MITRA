import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kisan Sathi — Farm Advisor",
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
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
