import { ComingSoon } from "@/components/coming-soon";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Disruption Radar");

export default function Page() {
  return (
    <ComingSoon
      title={"Disruption Radar"}
      question={"What happened, and does it affect us?"}
      milestone={"M4 (C2)"}
      items={["One event from many articles, with evidence quotes", "Linked ports, lanes and suppliers", "Buffer recommendations"]}
    />
  );
}
