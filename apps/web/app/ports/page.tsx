import { ComingSoon } from "@/components/coming-soon";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Ports & Vessels");

export default function Page() {
  return (
    <ComingSoon
      title={"Ports & Vessels"}
      question={"When will vessels berth and leave, and how congested will it get?"}
      milestone={"M6 (C4)"}
      items={["Queue timeline and a 14-day fan chart (P10\u2013P90)", "Vessel table with wait P10/P50/P90 and the drivers", "Satellite panel: SAR counts vs AIS"]}
    />
  );
}
