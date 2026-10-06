import type { Metadata, Viewport } from "next";
import { DM_Mono, DM_Sans } from "next/font/google";
import Script from "next/script";
import { ThemeProvider } from "@/components/theme-provider";
import { themeInitScript } from "@/lib/theme-script";
import "./globals.css";

const dmSans = DM_Sans({ variable: "--font-dmsans", subsets: ["latin"] });
const dmMono = DM_Mono({
  variable: "--font-dmmono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "LETS Video Analyzer",
  description:
    "Ask questions about any video in plain language and receive precise answers as text, tables and charts.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#08202e" },
    { media: "(prefers-color-scheme: light)", color: "#e9f2f6" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${dmSans.variable} ${dmMono.variable} h-full`}
    >
      <body className="flex min-h-full flex-col">
        <Script id="theme-init" strategy="beforeInteractive">
          {themeInitScript}
        </Script>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
