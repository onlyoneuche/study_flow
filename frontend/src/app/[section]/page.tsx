import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

const sections: Record<string, { title: string; description: string }> = {
  study: { title: "Your study time", description: "Live and solo sessions will be available here as StudyFlow takes shape." },
  ranks: { title: "Progress worth celebrating", description: "Your squad’s weekly progress and personal improvement will appear here." },
  squad: { title: "Your study squad", description: "Soon you’ll create a squad and invite friends to study together." },
};

export async function generateMetadata({ params }: { params: Promise<{ section: string }> }): Promise<Metadata> {
  const { section } = await params;
  return { title: sections[section]?.title ?? "Page not found" };
}

export default async function Section({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const content = sections[section];
  if (!content) notFound();
  return <section className="card mx-auto max-w-2xl p-6 md:p-10">
    <p className="text-sm font-bold text-brand-700">Coming soon</p>
    <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900">{content.title}</h1>
    <p className="mt-4 leading-relaxed text-slate-500">{content.description}</p>
    <Link href="/" className="mt-7 inline-flex min-h-12 items-center rounded-2xl bg-brand-600 px-5 font-bold text-white hover:bg-brand-700">Back to Home</Link>
  </section>;
}
