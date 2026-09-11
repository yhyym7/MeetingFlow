export interface CurrentUser { id: number; name: string; username: string; role: 'BOSS' | 'EMPLOYEE' | 'MANAGER'; department_id: number | null }
export interface MeetingSummary { id: number; title: string; starts_at: string; location: string | null }
export interface TaskSummary {
  id: number; title: string; status: 'TODO' | 'IN_PROGRESS' | 'DONE'; due_at: string | null
  source_meeting_title: string | null; is_overdue: boolean
}
export interface Dashboard {
  role: 'BOSS' | 'EMPLOYEE' | 'MANAGER'; as_of: string
  statistics: { total: number; todo: number; in_progress: number; done: number; overdue: number; due_today: number }
  upcoming_meetings: MeetingSummary[]
  due_today_tasks: TaskSummary[]; overdue_tasks: TaskSummary[]; in_progress_tasks: TaskSummary[]
  pending_supplement_count: number | null
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Person { id: number; name: string; department_id: number | null; is_active?: boolean }
export interface Department { id: number; name: string }
export interface MeetingInput { id: number; version: number; text: string; processing_status: string; job_id: number | null }
export interface MeetingAudio { id: number; meeting_id: number; original_name: string; size_bytes: number; created_at: string; status: 'AWAITING_TRANSCRIPTION' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'; message: string; transcript: string | null; error_code: string | null; input_id: number | null }
export interface Source { kind: 'task' | 'meeting'; id: number; title: string; excerpt: string | null; input_id: number | null; input_version: number | null; chunk_id: number | null; start_offset: number | null; end_offset: number | null }
export interface MeetingDetail extends MeetingSummary { can_manage: boolean; direct_participant_ids: number[]; department_ids: number[]; department_attendance: { department_id: number; participant_ids: number[]; can_arrange: boolean }[]; description: string | null; participant_ids: number[]; current_input: MeetingInput | null; current_audio: MeetingAudio | null }
export interface Job { id: number; status: string; stage: string; error_code: string | null; scope: string }
export interface Analysis { id: number; mode: string; summary: string; decisions: string[]; risks: string[]; raw_output?: string }
export interface TaskDetail extends TaskSummary {
  description: string; owner_id: number; collaborator_ids: number[]; meeting_id: number | null
  source_excerpt: string | null; can_view_meeting: boolean; can_manage: boolean; can_update_status: boolean; priority: 'LOW' | 'NORMAL' | 'HIGH'; completed_at: string | null
}
export interface TaskDraft { title: string; description: string; owner_id: number | null; collaborator_ids: number[]; due_at: string | null; priority: string; source_excerpt: string }
export interface Candidate {
  id: number; status: string; needs_attention: boolean; task_id: number | null; task_deleted: boolean
  resolved: { candidate: { title: string; description: string | null; source_quote: string; priority: string; deadline_text: string | null } | null; owner_id: number | null; collaborator_ids: number[]; due_at: string | null; issues: string[] }
}
export interface TaskEvent { id: number; actor_id: number; event_type: string; body: string | null; created_at: string; changes: Record<string, unknown> | null }
