import { JoinPage } from "@/components/join-page";
export default async function Page({ params }: { params: Promise<{ code: string }> }) { const { code } = await params; return <JoinPage code={code} />; }
