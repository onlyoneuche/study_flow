"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "Home", path: "M3 11l9-7 9 7v9H15v-6H9v6H3z" },
  { href: "/study", label: "Study", path: "M9 2h6M12 9v4l3 2M20 13a8 8 0 1 1-16 0 8 8 0 0 1 16 0" },
  { href: "/ranks", label: "Ranks", path: "M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3" },
  { href: "/squad", label: "Squad", path: "M12.5 8a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname.startsWith("/auth/")) return <main id="main" className="min-h-dvh px-5 py-7 md:py-12"><Link href="/" className="mx-auto mb-10 flex min-h-12 max-w-lg items-center gap-3 text-2xl font-extrabold"><BrandMark />StudyFlow</Link>{children}</main>;
  return (
    <div className="min-h-dvh min-[1025px]:pl-62">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-xl focus:bg-white focus:p-4">Skip to content</a>
      <aside className="fixed inset-y-0 left-0 hidden w-62 flex-col border-r border-slate-200/70 bg-white px-5 py-7 min-[1025px]:flex">
        <Link href="/" className="flex min-h-12 items-center gap-2.5 px-2 text-[22px] font-extrabold tracking-tight text-slate-900">
          <BrandMark />StudyFlow
        </Link>
        <nav aria-label="Main navigation" className="mt-9 space-y-1.5">
          {items.map((item) => <NavItem key={item.href} item={item} active={pathname === item.href} />)}
        </nav>
        <div className="mt-auto rounded-2xl bg-brand-50 p-4 text-sm leading-relaxed text-brand-800">
          A little progress, together.<br />One session at a time.
        </div>
      </aside>
      <main id="main" className="mx-auto max-w-7xl px-5 pt-7 pb-28 md:px-8 md:pt-10 min-[1025px]:px-10 min-[1025px]:pb-10">
        {children}
      </main>
      <nav aria-label="Main navigation" className="fixed inset-x-0 bottom-0 z-20 flex justify-around border-t border-slate-100 bg-white px-3 pt-2 pb-[max(12px,env(safe-area-inset-bottom))] min-[1025px]:hidden">
        {items.map((item) => <NavItem key={item.href} item={item} active={pathname === item.href} mobile />)}
      </nav>
    </div>
  );
}

function NavItem({ item, active, mobile = false }: { item: typeof items[number]; active: boolean; mobile?: boolean }) {
  return <Link href={item.href} aria-current={active ? "page" : undefined} className={`flex min-h-12 items-center rounded-2xl font-semibold ${mobile ? "min-w-16 flex-col justify-center gap-1 text-[11px]" : "gap-3 px-4 text-base"} ${active ? `text-brand-700 ${mobile ? "" : "bg-brand-50"}` : "text-slate-500 hover:text-brand-700"}`}>
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={item.path} /></svg>
    {item.label}
  </Link>;
}

export function BrandMark() {
  return <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white" aria-hidden="true">
    <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19V8l8-4 8 4v11M9 19v-6h6v6" /></svg>
  </span>;
}
