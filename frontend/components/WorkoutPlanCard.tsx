import type { WorkoutPlan } from './types';
import ExerciseRow from './ExerciseRow';
import StatusChip from './StatusChip';

export default function WorkoutPlanCard({ plan }: { plan: WorkoutPlan }) {
  return (
    <div className="panel workout-plan-card" data-component="WorkoutPlanCard">
      <p>{plan.summary}</p>
      {plan.safety_flags.length > 0 && (
        <div className="safety-flags">
          {plan.safety_flags.map((flag) => (
            <StatusChip key={flag} label={flag} />
          ))}
        </div>
      )}
      <div className="exercise-list">
        {plan.exercises.map((exercise) => (
          <ExerciseRow key={exercise.exercise_id} exercise={exercise} />
        ))}
      </div>
    </div>
  );
}
