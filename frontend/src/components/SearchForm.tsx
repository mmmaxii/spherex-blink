import { useState, type FormEvent } from "react";
import { FOV_ARCMIN_OPTIONS } from "../state/urlState";

/** The five objects the challenge asks to test with. Names are resolved by the backend, which
 * also moves fast stars to where they are now (WISE 0855 is 2' from its catalogue position). */
const TEST_TARGETS = [
  { name: "Barnard's Star", note: "fastest star in the sky" },
  { name: "eps Ind B", note: "pair of brown dwarfs" },
  { name: "WISE 0855-0714", note: "cold, fast brown dwarf" },
  { name: "RW Aur", note: "variable star" },
  { name: "R Dra", note: "variable star" },
];

export interface Query {
  target: string | null;
  ra: string | null;
  dec: string | null;
  fovArcmin: number;
}

interface Props {
  initial: Query;
  busy: boolean;
  onSearch: (query: Query) => void;
}

export function SearchForm({ initial, busy, onSearch }: Props) {
  const [name, setName] = useState(initial.target ?? "");
  const [ra, setRa] = useState(initial.ra ?? "");
  const [dec, setDec] = useState(initial.dec ?? "");
  const [fovArcmin, setFovArcmin] = useState(initial.fovArcmin);
  const hasCoordinates = ra.trim() !== "" && dec.trim() !== "";
  const canSearch = hasCoordinates || name.trim() !== "";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSearch) return;
    // Coordinates win when both are filled; otherwise the name is looked up.
    onSearch(
      hasCoordinates
        ? { target: null, ra: ra.trim(), dec: dec.trim(), fovArcmin }
        : { target: name.trim(), ra: null, dec: null, fovArcmin },
    );
  }

  function pick(target: string) {
    setName(target);
    setRa("");
    setDec("");
    onSearch({ target, ra: null, dec: null, fovArcmin });
  }

  return (
    <form className="search" onSubmit={submit}>
      <div className="fields">
        <label>
          Right ascension
          <input
            value={ra}
            onChange={(e) => setRa(e.target.value)}
            placeholder="08h55m10.831s or 133.795"
            autoComplete="off"
          />
        </label>
        <label>
          Declination
          <input
            value={dec}
            onChange={(e) => setDec(e.target.value)}
            placeholder="-7d14m42.53s or -7.245"
            autoComplete="off"
          />
        </label>
        <label>
          …or an object name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Barnard's Star"
            autoComplete="off"
          />
        </label>
        <label>
          Field of view
          <select
            value={fovArcmin}
            onChange={(e) => setFovArcmin(Number(e.target.value))}
          >
            {FOV_ARCMIN_OPTIONS.map((fov) => (
              <option key={fov} value={fov}>
                {fov} arcmin
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="primary" disabled={!canSearch || busy}>
          Show images
        </button>
      </div>
      <div className="chips">
        <span className="muted">Try:</span>
        {TEST_TARGETS.map((t) => (
          <button
            key={t.name}
            type="button"
            className="chip"
            title={t.note}
            onClick={() => pick(t.name)}
          >
            {t.name}
          </button>
        ))}
      </div>
    </form>
  );
}
