import { ComingSoon } from "@/components/coming-soon";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Scenario Studio");

export default function Page() {
  return (
    <ComingSoon
      title={"Scenario Studio"}
      question={"What if\u2026, and what should we do?"}
      milestone={"M8 (Nexus)"}
      items={["Build a scenario across all capabilities", "With vs without the recommended actions", "One-page export"]}
    />
  );
}
