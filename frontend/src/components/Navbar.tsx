import Link from "next/link";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/trade", label: "Kereskedés" },
  { href: "/orders", label: "Rendelések" },
  { href: "/positions", label: "Pozíciók" },
];

export function Navbar() {
  return (
    <header className="border-b border-border bg-bg-subtle/60 backdrop-blur sticky top-0 z-10">
      <div className="mx-auto max-w-7xl px-4 py-3 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-bold text-accent">⟡ Bitunix Trader</span>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="px-3 py-1.5 rounded-md text-slate-300 hover:bg-bg-card hover:text-slate-100 transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
