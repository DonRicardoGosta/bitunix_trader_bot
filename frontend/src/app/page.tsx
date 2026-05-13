import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarketTicker } from "@/components/MarketTicker";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-bold text-slate-100">Üdv a Bitunix Trader-en</h1>
        <p className="text-muted mt-1">
          Kövesd a piaci árakat, kezeld a pozícióidat és kereskedj futures
          kontraktusokkal a Bitunix tőzsdén. Alapértelmezetten dry-run módban
          fut – élesítéshez állítsd a <code className="text-accent">BITUNIX_LIVE_TRADING=true</code>{" "}
          flag-et.
        </p>
      </section>

      <MarketTicker symbol="BTCUSDT" />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ShortcutCard
          href="/trade"
          title="Kereskedés"
          description="Adj fel piaci vagy limit rendelést szimbólumra."
        />
        <ShortcutCard
          href="/strategies"
          title="Stratégiák"
          description="Automatizált logikák kezelése (pl. top movers, 4h cooldown, max leverage)."
        />
        <ShortcutCard
          href="/events"
          title="Eseménynapló"
          description="Minden esemény DB-ben tárolva, szűrhetően."
        />
        <ShortcutCard
          href="/positions"
          title="Pozíciók"
          description="Megnyitott pozíciók és PnL áttekintés."
        />
        <ShortcutCard
          href="/orders"
          title="Rendelés napló"
          description="A backend audit log-ja a feladott rendelésekről."
        />
      </div>
    </div>
  );
}

function ShortcutCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link href={href}>
      <Card className="hover:border-accent transition-colors cursor-pointer h-full">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted">{description}</p>
        </CardContent>
      </Card>
    </Link>
  );
}
