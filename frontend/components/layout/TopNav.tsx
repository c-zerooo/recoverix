"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function TopNav() {
  const pathname = usePathname();
  
  return (
    <nav className="border-b border-[#1E293B] bg-[#0B0F1A]/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="font-bold text-lg text-white tracking-tight">
          Recoverix
        </Link>

        <div className="flex items-center gap-6 text-sm font-medium h-full">
          <Link 
            href="/" 
            className={`h-full flex items-center px-1 border-b-2 transition-colors ${
              pathname === '/' || pathname === ''
                ? 'border-pink-500 text-pink-500' 
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            Upload
          </Link>
          <Link 
            href="/dashboard" 
            className={`h-full flex items-center px-1 border-b-2 transition-colors ${
              pathname?.startsWith('/dashboard') || pathname?.startsWith('/artifacts')
                ? 'border-pink-500 text-pink-500' 
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            Dashboard
          </Link>
        </div>
      </div>
    </nav>
  );
}
