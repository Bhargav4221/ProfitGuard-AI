import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ProfitGuard AI — Profit Intelligence & RTO Recovery for D2C Commerce',
  description: 'Protect contribution margins, reduce COD RTO losses, and automate delivery recovery for high-growth Indian D2C merchants.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 antialiased">{children}</body>
    </html>
  );
}
