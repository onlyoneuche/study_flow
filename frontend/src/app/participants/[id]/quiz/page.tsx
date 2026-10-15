import { QuizPage } from "@/components/quiz-page";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <QuizPage id={id} />; }
