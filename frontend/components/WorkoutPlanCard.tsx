import type { WorkoutPlan } from './types';
import ExerciseRow from './ExerciseRow';
import StatusChip from './StatusChip';

export default function WorkoutPlanCard({ plan }: { plan: WorkoutPlan }) {
  return (
    <div className="kg-card" data-component="WorkoutPlanCard">
      <div className="kg-between">
        <div>
          <p className="kg-eyebrow">Generated plan</p>
          <h2 className="kg-h1" style={{ marginTop: 6 }}>
            {plan.summary}
          </h2>
        </div>
        <div className="kg-row-f">
          <span className="kg-chip kg-chip--safe">
            <span className="kg-chip__dot" />
            Cleared
          </span>
        </div>
      </div>

      {plan.safety_flags.length > 0 && (
        <div className="kg-row-f" style={{ marginTop: 'var(--space-md)' }}>
          {plan.safety_flags.map((flag) => (
            <StatusChip key={flag} label={flag} />
          ))}
        </div>
      )}

      <div
        className="kg-row-f"
        style={{ gap: 'var(--space-md)', margin: 'var(--space-md) 0 var(--space-lg)' }}
      >
        <span className="kg-mono">{plan.exercises.length} exercises</span>
      </div>

      <div className="kg-stack" style={{ gap: 'var(--space-sm)' }}>
        {plan.exercises.map((exercise, i) => (
          <ExerciseRow key={exercise.exercise_id} exercise={exercise} index={i + 1} />
        ))}
      </div>
    </div>
  );
}
