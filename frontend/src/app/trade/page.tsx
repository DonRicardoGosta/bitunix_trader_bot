import { redirect } from "next/navigation";

/** A kézi kereskedés a Rendelések oldalon érhető el. */
export default function TradePageRedirect() {
  redirect("/orders");
}
