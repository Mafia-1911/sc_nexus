import { ComingSoon } from "@/components/coming-soon";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Route Planner");

export default function Page() {
  return (
    <ComingSoon
      title={"Route Planner"}
      question={"How do I move this cargo best?"}
      milestone={"M5 (C3)"}
      items={["Road, rail via Kamalapur ICD, barge via Pangaon", "Pareto chart of time, cost and CO2e", "On-time probability for the order deadline"]}
    />
  );
}
