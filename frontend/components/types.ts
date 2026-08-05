export interface Member {
  id: string;
  name: string;
  injuries: string[];
  goals: string[];
}

export interface RecentWorkout {
  timestamp: string;
  exercises: string[];
}

export interface AdherenceEntry {
  timestamp: string;
  planned: number;
  completed: number;
}

export interface MemberDetail extends Member {
  recent_workouts: RecentWorkout[];
  adherence: AdherenceEntry[];
}

export interface PlanExercise {
  exercise_id: string;
  name: string;
  sets: number;
  reps: number;
  notes: string | null;
}

export interface WorkoutPlan {
  member_id: string;
  summary: string;
  exercises: PlanExercise[];
  safety_flags: string[];
  excluded_contraindicated: string[];
}

export interface RetrievalBundle {
  member_id: string;
  query: string;
  vector_hits: unknown[];
  subgraph_facts: string[];
  context_items: string[];
  contraindications: string[];
  token_estimate: number;
  token_budget: number;
}

export type TabId = 'Overview' | 'Workout' | 'Insights' | 'Trends' | 'Chat';

export interface RiskFlag {
  kind: string;
  severity: string;
  detail: string;
}

export interface BiometricTrend {
  type: string;
  slope_per_week: number;
  direction: string;
  first_value: number;
  last_value: number;
}

export interface TrendSummary {
  window_weeks: number | null;
  adherence_percentage: number | null;
  adherence_sessions: string | null;
  biometrics: BiometricTrend[];
  workout_count: number;
  summary_lines: string[];
}

export interface InsightReport {
  member_id: string;
  summary: string;
  risk_flags: RiskFlag[];
  personalization_notes: string[];
  trends: TrendSummary | null;
  excluded_contraindicated: string[];
  safety_flags: string[];
}

export interface ChatAnswer {
  member_id: string;
  message: string;
  answer: string;
  context_used: string[];
}

export interface ChatTurn {
  role: 'coach' | 'assistant';
  text: string;
}
