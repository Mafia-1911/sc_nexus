/** Decorative background (05 §3 "calm, oceanic"): a slow swell and a few ships crossing.
 *  Pure SVG + CSS, behind everything, ignored by assistive tech, still under reduced motion. */
const SHIPS = [
  { top: "14%", scale: 0.9, duration: 140, delay: -20 },
  { top: "38%", scale: 0.6, duration: 190, delay: -110 },
  { top: "63%", scale: 1.1, duration: 160, delay: -60 },
  { top: "84%", scale: 0.75, duration: 210, delay: -150 },
];

function Ship({ scale }: { scale: number }) {
  // A container ship in profile: hull, stacked boxes, bridge.
  return (
    <svg width={160 * scale} height={48 * scale} viewBox="0 0 160 48" aria-hidden>
      <path d="M4 30 H150 L138 44 H18 Z" fill="currentColor" />
      <rect x="22" y="18" width="18" height="12" fill="currentColor" opacity="0.8" />
      <rect x="42" y="14" width="18" height="16" fill="currentColor" opacity="0.65" />
      <rect x="62" y="18" width="18" height="12" fill="currentColor" opacity="0.8" />
      <rect x="82" y="12" width="18" height="18" fill="currentColor" opacity="0.65" />
      <rect x="112" y="6" width="14" height="24" fill="currentColor" />
      <rect x="116" y="0" width="4" height="7" fill="currentColor" />
    </svg>
  );
}

export function OceanBackdrop() {
  return (
    <div aria-hidden className="ocean-backdrop pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {[0, 1, 2].map((i) => (
        <svg
          key={i}
          className="ocean-swell absolute left-0 w-[200%]"
          style={{ bottom: `${8 + i * 22}%`, animationDuration: `${60 + i * 25}s` }}
          height="40"
          viewBox="0 0 1200 40"
          preserveAspectRatio="none"
        >
          <path
            d="M0 20 Q 75 0 150 20 T 300 20 T 450 20 T 600 20 T 750 20 T 900 20 T 1050 20 T 1200 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
      ))}
      {SHIPS.map((s) => (
        <div
          key={s.top}
          className="ocean-ship absolute left-0"
          style={{ top: s.top, animationDuration: `${s.duration}s`, animationDelay: `${s.delay}s` }}
        >
          <Ship scale={s.scale} />
        </div>
      ))}
    </div>
  );
}
