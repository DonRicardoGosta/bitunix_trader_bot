import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarketTicker } from "@/components/MarketTicker";
import { OrderForm } from "@/components/OrderForm";

export default function TradePage() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <MarketTicker symbol="BTCUSDT" />
        <Card>
          <CardHeader>
            <CardTitle>Stratégia javaslat</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted">
              Ez a kezdő scaffold – ide bővíthető pl. TradingView chart,
              indikátorok vagy automata stratégia panel. A backend
              <code className="text-accent mx-1">/api/market/depth/&lt;symbol&gt;</code>
              végpontja már ad orderbook adatot.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rendelés feladása</CardTitle>
        </CardHeader>
        <CardContent>
          <OrderForm />
        </CardContent>
      </Card>
    </div>
  );
}
