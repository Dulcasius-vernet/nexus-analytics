import type { Metadata } from "next";
import "./styles.css";
export const metadata: Metadata = {
  title: "Nexus Analytics",
  description: "AI-augmented business intelligence and predictive analytics",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
