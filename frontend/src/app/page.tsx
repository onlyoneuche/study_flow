import { BrandMark } from "@/components/app-shell";
import { HealthStatus } from "@/components/health-status";

export default function Home() {
  return <>
    <header className="mb-6 flex items-center gap-3 min-[1025px]:mb-8">
      <div className="min-[1025px]:hidden"><BrandMark /></div>
      <div><p className="text-sm text-slate-500">A little progress, every day</p><h1 className="text-2xl font-extrabold tracking-tight text-slate-900 md:text-3xl">Welcome to StudyFlow</h1></div>
    </header>
    <section className="relative overflow-hidden rounded-[26px] bg-linear-to-br from-brand-600 to-brand-700 p-6 text-white md:p-8">
      <div aria-hidden="true" className="absolute -top-10 -right-10 size-48 rounded-full bg-white/10" />
      <p className="relative text-sm font-semibold text-brand-100">Better together</p>
      <h2 className="relative mt-3 max-w-xl text-3xl leading-tight font-extrabold tracking-tight md:text-4xl">Your topic. Your pace.<br />Your study squad.</h2>
      <p className="relative mt-4 max-w-lg text-sm leading-relaxed text-brand-50 md:text-base">Make time for what you’re learning, reflect with a quiz, and build a study habit with friends.</p>
    </section>
    <div className="mt-5 grid items-start gap-5 md:grid-cols-2">
      <section className="card p-5 md:p-6">
        <span className="inline-flex rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800">Taking shape</span>
        <h2 className="mt-4 text-xl font-bold text-slate-900">Good things start small.</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">We’re getting your study space ready. Accounts, squads and timed sessions are coming next.</p>
        <p className="mt-5 rounded-xl bg-brand-50 p-3 text-sm font-semibold text-brand-800">Personal progress. Shared encouragement.</p>
      </section>
      <HealthStatus />
    </div>
  </>;
}
