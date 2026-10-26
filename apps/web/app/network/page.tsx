import { ComingSoon } from "@/components/coming-soon";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Supplier Network");

export default function Page() {
  return (
    <ComingSoon
      title={"Supplier Network"}
      question={"Where are we fragile?"}
      milestone={"M3 (C1)"}
      items={["Graph and geo views of the supply network", "Criticality: dominators, downstream counts, HHI, TTS vs TTR", "What-if: close a node or a port for N days and watch the ripple"]}
    />
  );
}
