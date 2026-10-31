// The shapes the backend returns. See the description of POST /chat in the API docs (/docs).

export type Role = 'teacher' | 'school_admin' | 'superadmin';

export interface Profile {
  user_id: number;
  full_name: string;
  role: Role;
  school_name: string | null; // null for the superadmin
  class_names: string[]; // classes a teacher leads
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: Profile;
}

export interface Session {
  token: string;
  profile: Profile;
  email?: string; // what the person typed to sign in (the profile has no email)
}

export interface Student {
  id: number;
  full_name: string;
  class: string | null;
  status: 'active' | 'inactive';
  school?: string | null;
}

export interface Teacher {
  id: number;
  full_name: string;
}

export interface HistoryItem {
  action: string;
  date: string | null; // 2026-10-27
  from_class: string | null; // null also means "a class you may not see"
  to_class: string | null;
}

export interface ClassInfo {
  name: string;
  school: string;
  active_students: number;
  teachers: Teacher[] | null; // null = this user may not see assignments
}

export interface Finding {
  student_id: number;
  full_name: string;
  state: 'active' | 'deactivated' | 'moved_out_of_your_access';
  current_class: string | null;
  history: HistoryItem[];
}

export type Warning =
  | { code: 'same_name_elsewhere'; students: Student[] }
  | { code: 'classes_left_without_teacher'; classes: string[] }
  | { code: 'class_left_without_teacher'; class: string }
  | { code: string };

// What a pending change will do. Which fields exist depends on `action`.
export interface ConfirmationDetails {
  action: string;
  student_name?: string; // add_student
  class?: string; // add_student, assign_teacher, unassign_teacher
  school?: string;
  student?: Student; // remove_student, restore_student
  students?: Student[]; // transfer_students
  to_class?: string; // transfer_students
  teacher_name?: string; // add_teacher
  teacher?: Teacher; // remove_teacher, assign_teacher, unassign_teacher
  classes?: string[]; // add_teacher, remove_teacher
}

export type Block =
  | { type: 'class_roster'; class: string; school: string; teachers: Teacher[] | null; students: Student[]; count: number }
  | { type: 'class_overview'; classes: ClassInfo[] }
  | { type: 'teacher_list'; teachers: (Teacher & { school: string; classes: string[] })[] }
  | { type: 'school_list'; schools: { id: number; name: string }[] }
  | { type: 'student_list'; students: Student[] }
  | { type: 'student_card'; student: Student; history: HistoryItem[] }
  | { type: 'duplicates'; groups: { name: string; students: Student[] }[]; count: number }
  | { type: 'investigation'; findings: Finding[]; note?: string }
  | {
      type: 'confirmation';
      token: string;
      action: string;
      summary: string;
      details: ConfirmationDetails;
      warnings: Warning[];
      expires_at: string;
    }
  | { type: 'result'; status: 'done' | 'already_done' | 'cancelled'; token?: string; result: Record<string, unknown> }
  | { type: 'banner'; level: 'error' | 'info'; message: string; code: string | null };

export interface ChatMeta {
  request_type: string;
  outcome: string;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  duration_ms: number;
}

export interface ChatResponse {
  conversation_id: string;
  text: string;
  blocks: Block[];
  meta: ChatMeta;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  text: string;
  blocks: Block[];
  at: string | null;
}

export interface HistoryResponse {
  conversation_id: string | null;
  messages: HistoryMessage[];
}
