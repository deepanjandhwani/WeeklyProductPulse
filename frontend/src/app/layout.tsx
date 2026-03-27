import type { Metadata } from "next";
import { Figtree, Newsreader } from "next/font/google";
import "./globals.css";

const figtree = Figtree({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

const newsreader = Newsreader({
  variable: "--font-report",
  subsets: ["latin"],
  display: "swap",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Weekly Product Pulse — IndMoney",
  description:
    "Weekly Play Store review intelligence: themes, quotes, and actions for IndMoney.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${figtree.variable} ${newsreader.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
