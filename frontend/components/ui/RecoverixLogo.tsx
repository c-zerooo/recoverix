"use client";

import React from "react";

interface RecoverixLogoProps {
  className?: string;
  size?: number;
  showText?: boolean;
  subtitle?: string;
  variant?: "navy" | "white";
}

export function RecoverixLogo({
  className = "",
  size = 32,
  showText = true,
  subtitle = "DIGITAL EVIDENCE RECOVERY PLATFORM",
  variant = "navy",
}: RecoverixLogoProps) {
  const isNavy = variant === "navy";

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      {/* Precision Geometric Forensic Mark: Shield + Fragment Reassembly */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        {/* Outer Shield / Container Contour */}
        <path
          d="M20 3L6 8.5V18.2C6 26.8 12 34.8 20 37C28 34.8 34 26.8 34 18.2V8.5L20 3Z"
          fill={isNavy ? "#F0FDF4" : "rgba(16, 185, 129, 0.15)"}
          stroke={isNavy ? "#0F172A" : "#FFFFFF"}
          strokeWidth="2.2"
          strokeLinejoin="round"
        />

        {/* Fragment Path A (Header Segment - Navy) */}
        <path
          d="M14 14.5H22C24.2 14.5 26 16.3 26 18.5V19.5"
          stroke={isNavy ? "#0F172A" : "#FFFFFF"}
          strokeWidth="2.4"
          strokeLinecap="round"
        />

        {/* Fragment Gap / Reconstructed Intersection (Emerald Diamond Node) */}
        <rect
          x="17.5"
          y="18.5"
          width="5"
          height="5"
          rx="1"
          transform="rotate(45 20 21)"
          fill="#10B981"
          stroke={isNavy ? "#047857" : "#34D399"}
          strokeWidth="1"
        />

        {/* Fragment Path B (Reconstructed Trailer Segment - Emerald) */}
        <path
          d="M14 22.5V23.5C14 25.7 15.8 27.5 18 27.5H26"
          stroke="#10B981"
          strokeWidth="2.4"
          strokeLinecap="round"
        />

        {/* Discrete Forensic Anchor Nodes */}
        <circle cx="14" cy="14.5" r="1.6" fill={isNavy ? "#0F172A" : "#FFFFFF"} />
        <circle cx="26" cy="27.5" r="1.6" fill="#10B981" />
      </svg>

      {showText && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5 leading-none">
            <span
              className={`font-mono font-extrabold tracking-wider text-base ${
                isNavy ? "text-slate-900" : "text-white"
              }`}
            >
              RECOVERIX
            </span>
          </div>
          {subtitle && (
            <span
              className={`font-mono text-[9px] uppercase tracking-wider mt-1 ${
                isNavy ? "text-slate-500" : "text-slate-400"
              }`}
            >
              {subtitle}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
