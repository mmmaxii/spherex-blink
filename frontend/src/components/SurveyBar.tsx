import { SURVEYS, type Survey } from "../sky/surveys";

/** Row of missions, ordered by wavelength: the same sky in ultraviolet, visible and infrared. */
export function SurveyBar({
  current,
  onChange,
}: {
  current: Survey;
  onChange: (survey: Survey) => void;
}) {
  return (
    <div
      className="glass survey-bar"
      role="group"
      aria-label="Sky survey shown on the map"
    >
      {SURVEYS.map((survey) => (
        <button
          key={survey.id}
          className="survey"
          aria-pressed={survey.id === current.id}
          title={survey.note}
          onClick={() => onChange(survey)}
        >
          <b>{survey.label}</b>
          <small>{survey.band}</small>
        </button>
      ))}
    </div>
  );
}
