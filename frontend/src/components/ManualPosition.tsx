import { useState, type FormEvent } from "react";

export const MIN_FIELD_ARCMIN = 3; // limits of the analysis (backend max_fov_arcmin = 20)
export const MAX_FIELD_ARCMIN = 20;

interface Props {
  busy: boolean;
  onPreview: (ra: string, dec: string, fovArcmin: number) => void;
}

/**
 * Type a position and a field size by hand. Coordinates are sent as typed: the backend
 * (/api/resolve) reads decimal degrees and sexagesimal (05h07m49.6s, +30d24m05s, 76.9566).
 * "Preview" moves the map there and draws the field; nothing is analysed until "Analyse".
 */
export function ManualPosition({ busy, onPreview }: Props) {
  const [ra, setRa] = useState("");
  const [dec, setDec] = useState("");
  const [fovArcmin, setFovArcmin] = useState(6);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (ra.trim() && dec.trim()) onPreview(ra.trim(), dec.trim(), fovArcmin);
  };

  return (
    <form className="manual" onSubmit={submit}>
      <p className="small muted">Or type a position</p>
      <div className="manual-grid">
        <label>
          RA
          <input
            value={ra}
            onChange={(e) => setRa(e.target.value)}
            placeholder="05h07m49.6s or 76.957"
            autoComplete="off"
            required
          />
        </label>
        <label>
          Dec
          <input
            value={dec}
            onChange={(e) => setDec(e.target.value)}
            placeholder="+30d24m05s or 30.401"
            autoComplete="off"
            required
          />
        </label>
        <label>
          Field (′)
          <input
            type="number"
            min={MIN_FIELD_ARCMIN}
            max={MAX_FIELD_ARCMIN}
            step={1}
            value={fovArcmin}
            onChange={(e) => setFovArcmin(Number(e.target.value))}
            required
          />
        </label>
      </div>
      <button type="submit" disabled={busy}>
        Preview on the map
      </button>
    </form>
  );
}
