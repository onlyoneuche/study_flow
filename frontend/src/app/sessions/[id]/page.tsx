import { SessionRoom } from "@/components/session-room";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <SessionRoom id={id} />; }
