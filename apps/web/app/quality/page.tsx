import { ComingSoon } from "@/components/coming-soon";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Quality Lab");

export default function Page() {
  return (
    <ComingSoon
      title={"Quality Lab"}
      question={"Is this batch OK, and what does a bad batch cost us?"}
      milestone={"M7 (C5)"}
      items={["Anomaly heatmaps on fabric and tablet images", "AQL batch board", "Impact on orders and deliveries"]}
    />
  );
}
