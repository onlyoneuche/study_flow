import type { Group } from "@/lib/groups";
import type { StudySession } from "@/lib/sessions";
export type RecentStudy = { participant_id: number; session_id: number; subject: string; topic: string; level: string; planned_minutes: number; mode: string; session_date: string; status: string; ended_at: string | null; quiz_status: string; submitted: boolean; quiz_available: boolean };
export type Dashboard = { server_now: string; weekly_completed: number; groups: Group[]; sessions: StudySession[]; recent: RecentStudy[] };
