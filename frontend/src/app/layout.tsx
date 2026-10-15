import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/app-shell";
import { PwaRegistration } from "@/components/pwa-registration";
import { AuthProvider } from "@/components/auth-provider";
import "@fontsource-variable/plus-jakarta-sans";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "StudyFlow", template: "%s · StudyFlow" },
  description: "Your topic. Your pace. Your study squad.",
  applicationName: "StudyFlow",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "StudyFlow" },
  icons: { icon: "/icon.svg", apple: "/icons/icon-192.png" },
};

export const viewport: Viewport = {
  themeColor: "#059669",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-GB">
      <body className="font-sans antialiased">
        <AuthProvider><AppShell>{children}</AppShell></AuthProvider>
        <PwaRegistration />
      </body>
    </html>
  );
}
