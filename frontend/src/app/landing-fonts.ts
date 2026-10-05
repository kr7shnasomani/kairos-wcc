import { DM_Sans, Instrument_Sans } from "next/font/google";

// Shared brand typefaces. Declared in their own module (no "use client") so
// both the root layout and the client-side landing can use the same font files.
export const instrumentSans = Instrument_Sans({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const dmSans = DM_Sans({
  variable: "--font-dm",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});
