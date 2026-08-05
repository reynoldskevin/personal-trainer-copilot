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
