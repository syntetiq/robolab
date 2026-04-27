import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Sidebar } from '@/components/layout/Sidebar';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'RoboLab Console',
  description: 'Operator console for Isaac Sim teleoperation',
};

import { TooltipProvider } from '@/components/ui/tooltip';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <TooltipProvider>
          <div className="flex min-h-screen bg-muted/20">
            <Sidebar />
            <main className="flex-1 overflow-auto">
              {children}
            </main>
          </div>
        </TooltipProvider>
      </body>
    </html>
  );
}
