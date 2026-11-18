import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "GridCast | California Energy Intelligence",
  description: "California demand and day-ahead price forecasting dashboard",
  icons: { icon: "/favicon.ico", shortcut: "/favicon.ico", apple: "/portfolio-knight.png" },
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
