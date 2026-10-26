import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Numbers with thousands separators and units always shown (05 §8). */
export function fmt(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** Times are shown in Asia/Dhaka with a BST (Bangladesh Standard Time) label. */
export function dhakaTime(iso: string | null | undefined, withDate = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const text = d.toLocaleString("en-GB", {
    timeZone: "Asia/Dhaka",
    day: withDate ? "2-digit" : undefined,
    month: withDate ? "short" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${text} BST`;
}
