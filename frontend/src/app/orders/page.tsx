import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { OrdersTable } from "@/components/OrdersTable";

export default function OrdersPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rendelés napló</CardTitle>
        <span className="text-xs text-muted">
          forrás: a backend saját Postgres audit táblája
        </span>
      </CardHeader>
      <CardContent>
        <OrdersTable />
      </CardContent>
    </Card>
  );
}
