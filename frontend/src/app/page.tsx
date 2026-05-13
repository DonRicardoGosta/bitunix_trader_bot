import { DashboardOverview } from "@/components/DashboardOverview";
import { TradingGateBanner } from "@/components/TradingGateBanner";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <TradingGateBanner />
      <DashboardOverview />
    </div>
  );
}
