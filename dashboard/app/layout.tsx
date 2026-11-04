import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "GridCast | California Energy Intelligence",
  description: "Verified CAISO demand and day-ahead LMP research terminal",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
