import type { PlanExercise } from './types';

export default function ExerciseRow({
  exercise,
  index,
}: {
  exercise: PlanExercise;
  index?: number;
}) {
  return (
    <div className="kg-ex-row" data-component="ExerciseRow">
      {index != null && <span className="kg-ex-row__idx">{index}</span>}
      <div className="kg-grow">
        <div className="kg-h3">{exercise.name}</div>
        <p className="kg-mono">
          {exercise.sets} × {exercise.reps}
          {exercise.notes ? ` · ${exercise.notes}` : ''}
        </p>
      </div>
      <span className="kg-chip kg-chip--safe kg-chip--sm">Safe</span>
    </div>
  );
}
