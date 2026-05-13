# Frontend - Bitunix Trader

Next.js 14 (App Router) + TypeScript + TailwindCSS alapú trader dashboard.

## Modulok

| Útvonal                                | Szerep                                |
| -------------------------------------- | ------------------------------------- |
| `src/app/page.tsx`                     | Dashboard kezdőlap                    |
| `src/app/trade/page.tsx`               | Order form + piaci ár                 |
| `src/app/orders/page.tsx`              | Rendelés napló                        |
| `src/app/positions/page.tsx`           | Nyitott pozíciók                      |
| `src/components/`                      | Üzleti komponensek                    |
| `src/components/ui/`                   | shadcn-stílusú primitívek             |
| `src/lib/api.ts`                       | Backend API kliens                    |

## Helyi futtatás

```bash
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Tesztek:

```bash
npm test
```
