import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { OrdersTable } from "@/components/OrdersTable";

export default function OrdersPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rendelés napló</CardTitle>
        <span className="text-xs text-muted">
          forrás: saját Postgres napló + Bitunix history / nyitott pozíció (5 mp-enként frissül)
        </span>
      </CardHeader>
      <CardContent>
        <OrdersTable />
      </CardContent>
    </Card>
  );
}
