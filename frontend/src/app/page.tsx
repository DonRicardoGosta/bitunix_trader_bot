import { DashboardOverview } from "@/components/DashboardOverview";
import { MarketTicker } from "@/components/MarketTicker";
import { TradingGateBanner } from "@/components/TradingGateBanner";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <TradingGateBanner />
      <MarketTicker symbol="BTCUSDT" />
      <DashboardOverview />
    </div>
  );
}
