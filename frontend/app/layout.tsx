import type { Metadata } from "next";
import ClickFeedback from "./ClickFeedback";
import "./globals.css";
import "./filters.css";

export const metadata: Metadata = {
  title: "CvolvePro — Find work that fits",
  description: "AI-powered live job search across the world's best career platforms."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><ClickFeedback/>{children}</body></html>;
}
