import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { OrderForm } from "@/components/OrderForm";
import { OrdersTable } from "@/components/OrdersTable";
import { OrdersTotalDbPnl } from "@/components/OrdersTotalDbPnl";

export default function OrdersPage() {
  return (
    <div className="space-y-6">
      <OrdersTotalDbPnl />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Rendelés napló</CardTitle>
              <span className="text-xs text-muted">
                forrás: saját Postgres napló + Bitunix history / nyitott pozíció
              </span>
              <p className="text-xs text-muted mt-2 max-w-3xl leading-relaxed">
                Ha a realizált PnL vagy az ROI üres: nyisd meg böngészőben a backend JSON-t:{" "}
                <code className="rounded bg-bg-card px-1 py-0.5 text-[11px]">
                  /api/orders?debug_sync=1
                </code>{" "}
                — másold be a chatbe <strong>egy érintett sor</strong> teljes{" "}
                <code className="rounded bg-bg-card px-1 py-0.5 text-[11px]">exchange.debug</code>{" "}
                objektumát, és ha van, a tábla feletti sárga „Bitunix szinkron” üzenetet is (API
                kulcsot / secretet ne küldj).
              </p>
            </CardHeader>
            <CardContent>
              <OrdersTable />
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
    </div>
  );
}
