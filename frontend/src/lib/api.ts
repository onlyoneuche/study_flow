export type EducationLevel = "JSS1" | "JSS2" | "JSS3" | "SS1" | "SS2" | "SS3" | "UG_100" | "UG_200" | "UG_300" | "UG_400" | "UG_500" | "POSTGRAD" | "OTHER";
export const levels: EducationLevel[] = ["JSS1", "JSS2", "JSS3", "SS1", "SS2", "SS3", "UG_100", "UG_200", "UG_300", "UG_400", "UG_500", "POSTGRAD", "OTHER"];
export function bandFor(level: EducationLevel) { return level.startsWith("JSS") || level.startsWith("SS") ? "secondary" : "tertiary"; }
export function levelLabel(level: EducationLevel) { return level.startsWith("UG_") ? `${level.slice(3)}L` : level === "POSTGRAD" ? "Postgraduate" : level === "OTHER" ? "Other / adult learner" : level; }
export type User = { id: number; email: string; display_name: string; level: EducationLevel; audience_band: "secondary" | "tertiary"; is_verified: boolean; guardian_consent_at: string | null; adult_confirmed_at: string | null };

const messages: Record<string, string> = {
  LOGIN_BAD_CREDENTIALS: "Email or password is incorrect.",
  REGISTER_USER_ALREADY_EXISTS: "An account with this email already exists. Try signing in.",
  VERIFY_USER_BAD_TOKEN: "This verification link is invalid or has expired. Request a new link.",
  VERIFY_USER_ALREADY_VERIFIED: "Your email is already verified. You can sign in.",
  RESET_PASSWORD_BAD_TOKEN: "This reset link is invalid, expired or already used. Request a new link.",
};

export async function api<T>(path: string, options: { method?: string; body?: unknown; token?: string; form?: URLSearchParams } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: options.method ?? "GET", cache: "no-store", signal: AbortSignal.timeout(15000),
      headers: { ...(options.form ? { "Content-Type": "application/x-www-form-urlencoded" } : options.body ? { "Content-Type": "application/json" } : {}), ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}) },
      body: options.form ?? (options.body ? JSON.stringify(options.body) : undefined),
    });
  } catch { throw new Error("We couldn’t connect. Please try again."); }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = Array.isArray(detail) ? detail.map((entry: { msg: string }) => entry.msg.replace(/^Value error, /, "")).join(". ") : typeof detail === "object" && detail?.reason ? detail.reason : messages[detail] ?? (typeof detail === "string" ? detail : "Something went wrong. Please try again.");
    throw new Error(message);
  }
  return response.status === 204 ? undefined as T : await response.json().catch(() => undefined) as T;
}
