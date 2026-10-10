import './globals.css';
import './workbench.css';
import './pages.css';
import {Workspace} from '@/components/workspace';
import type {Metadata, Viewport} from 'next';

export const metadata: Metadata = {
  title: 'ImpulseTwin AI · HV Engineering',
  description: 'Physics-guided, inventory-aware impulse generator decision support for POWERnext AI.',
};
export const viewport: Viewport = {themeColor: '#0e161d'};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en">
      <head>
        <link rel="preload" href="/fonts/Barlow-Regular.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/BarlowCondensed-SemiBold.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
      </head>
      <body>
        <Workspace>{children}</Workspace>
      </body>
    </html>
  );
}
