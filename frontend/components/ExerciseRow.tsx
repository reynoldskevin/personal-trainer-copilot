import type { PlanExercise } from './types';

export default function ExerciseRow({ exercise }: { exercise: PlanExercise }) {
  return (
    <div className="exercise-row" data-component="ExerciseRow">
      <span className="name">{exercise.name}</span>
      <span className="prescription">
        {exercise.sets} × {exercise.reps}
        {exercise.notes ? ` — ${exercise.notes}` : ''}
      </span>
    </div>
  );
}
