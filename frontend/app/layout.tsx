import type { ReactNode } from 'react';
import './globals.css';

export const metadata = {
  title: 'Coach Dashboard',
  description: 'Minimal coach dashboard for the Knowledge Graph Coaching Platform.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
