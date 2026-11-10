export type User = { id: string; username: string; csrf: string }
export type Source = { number: number; title: string; url: string; published_at?: string; text?: string }
export type Artifact = { id: string; name: string; url: string; size: number; verified: boolean; task_id?: string }
export type Step = { tool: string; title: string; status: string }
export type TaskEvent = { tool: string; message: string; at: string }
export type TaskContext = { parent_task_id: string; turns: { task_id: string; prompt: string; answer: string }[]; truncated: boolean; text_characters: number }
export type UploadFinding = { reference: string; filename: string; heading: string; summary: string; quote: string; line_start: number; line_end: number; mode: string }
export type Task = {
  id: string; prompt: string; status: string; plan: Step[]; answer: string;
  sources: Source[]; artifacts: Artifact[]; events: TaskEvent[]; warnings: string[];
  error?: string; created_at: string; completed_at?: string
  context?: TaskContext
  browser_pages?: { number: number; title: string; url: string; requested_url: string; screenshot: string; reading_characters: number }[]
  upload_findings?: UploadFinding[]
}
export type Upload = { id: string; name: string; text_preview?: string }
export type ScheduleRun = { id: number; attempted_at: string; task_id: string | null; status: string; skip_reason: string | null }
export type Schedule = { id: string; prompt: string; interval_minutes: number; next_run: string | number; enabled: boolean; recent_runs?: ScheduleRun[] }
export type Approval = { id: string; action: string; detail: string; status: string; task_id: string }
export type Capabilities = {
  model: string; context_size: number; browser_enabled: boolean; code_execution: boolean;
  formats: string[]; limits: Record<string, number | string>
}
export type Page = 'workspace' | 'research' | 'files' | 'browser' | 'code' | 'schedules' | 'settings'
