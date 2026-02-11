import '../styles/globals.css';

import type { Metadata } from 'next';
import { IBM_Plex_Sans, Outfit } from 'next/font/google';
import Link from 'next/link';

const outfit = Outfit({
  subsets: ['latin'],
  variable: '--font-display',
  weight: ['500', '600', '700', '800'],
});

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  variable: '--font-ui',
  weight: ['400', '500', '600', '700'],
});

export const metadata: Metadata = {
  title: 'Market Mood Radar',
  description: 'Reddit ticker-targeted stance analytics',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='en' className={`${outfit.variable} ${ibmPlexSans.variable}`}>
      <body>
        <div className='app-shell mx-auto max-w-6xl px-4 pb-8 pt-5 sm:px-6'>
          <header className='line-section fade-up mb-5 flex flex-wrap items-end justify-between gap-4'>
            <div className='space-y-1.5'>
              <p className='eyebrow'>Reddit Stance Analytics</p>
              <div className='flex flex-wrap items-center gap-2'>
                <Link href='/' className='display text-2xl font-bold text-slate-900 sm:text-[30px]'>
                  Market Mood Radar
                </Link>
                <Link href='/research' className='score-pill score-pill-neutral'>
                  Research Lab
                </Link>
              </div>
            </div>
            <div className='flex flex-wrap items-center gap-2 text-xs'>
              <span className='score-pill score-pill-neutral'>Berlin day buckets</span>
              <span className='score-pill score-pill-neutral'>Backend JSON only</span>
            </div>
          </header>

          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
