/**
 * Texts that explain the mission, the data and every number on the page, shown in collapsible
 * (i) notes. Facts come from the SPHEREx Explanatory Supplement v2.1 (IRSA, Nov 2026) and the DR1
 * documentation; keep them in sync with those sources, not with memory.
 */
import { InfoNote } from "../components/InfoNote";

/** The mission and the data release, for the top of the analysis page. */
export function AboutMission() {
  return (
    <InfoNote title="About SPHEREx and these data">
      <p>
        <strong>SPHEREx</strong> (Spectro-Photometer for the History of the
        Universe, Epoch of Reionization and Ices Explorer) is a NASA mission
        launched on 12 March 2025. Since May 2025 it maps the whole sky every
        six months in <strong>102 infrared colours from 0.75 to 5 µm</strong>,
        four times over its 25-month mission. Near the ecliptic poles it looks
        much more often (the deep fields).
      </p>
      <p>
        A 20 cm telescope sends the light to six detectors (2040 × 2040 pixels
        of 6.15″). Over each detector sits a filter whose colour changes from
        one edge to the other, so{" "}
        <strong>every row of an image sees a different wavelength</strong>. As
        the telescope steps across the sky, each star falls on different rows
        and its spectrum is built image by image. Every exposure lasts 114 s and
        takes six images at once.
      </p>
      <p>
        This tool uses the public <strong>Level 2 spectral images</strong> of
        Data Release 1 (DR1, the first year, fully reprocessed) and the weekly
        Quick Release 3 (QR3, the second year, same processing), from the
        NASA/IPAC Infrared Science Archive (IRSA). Each image is calibrated in
        MJy/sr and carries a flag for every pixel. Only the small piece needed
        is read from each 65 MB file.
      </p>
      <p className="small muted">
        Cite DOI 10.26131/IRSA678 (DR1) and 10.26131/IRSA679 (QR3). Explanatory
        Supplement: irsa.ipac.caltech.edu/data/SPHEREx/docs.
      </p>
    </InfoNote>
  );
}

/** The six detectors and what "D1…D6" means. */
export function DetectorsInfo() {
  return (
    <InfoNote title="What are the detectors D1–D6?">
      <p>
        Each detector covers one range of wavelengths. Within that range, the
        wavelength of a star depends on where it falls on the detector, so two
        images of the same detector can see it at slightly different colours
        (each image is labelled with its own).
      </p>
      <table>
        <thead>
          <tr>
            <th>Detector</th>
            <th>Wavelength</th>
            <th>Resolving power R</th>
            <th>What stands out</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>D1</td>
            <td>0.75–1.12 µm</td>
            <td>39</td>
            <td>closest to visible light</td>
          </tr>
          <tr>
            <td>D2</td>
            <td>1.10–1.65 µm</td>
            <td>41</td>
            <td>near-infrared J and H</td>
          </tr>
          <tr>
            <td>D3</td>
            <td>1.64–2.42 µm</td>
            <td>41</td>
            <td>K band; cool stars are bright</td>
          </tr>
          <tr>
            <td>D4</td>
            <td>2.42–3.82 µm</td>
            <td>35</td>
            <td>water ice and organics (3 µm)</td>
          </tr>
          <tr>
            <td>D5</td>
            <td>3.81–4.42 µm</td>
            <td>112</td>
            <td>CO₂ ice (4.26 µm)</td>
          </tr>
          <tr>
            <td>D6</td>
            <td>4.41–5.00 µm</td>
            <td>128</td>
            <td>CO (4.67 µm); brown dwarfs are bright</td>
          </tr>
        </tbody>
      </table>
      <p className="small muted">
        D1–D3 and D4–D6 look at the same sky at the same time (a dichroic splits
        the light), in pairs D1↔D4, D2↔D5, D3↔D6. The number under each button
        is how many images cover this position.
      </p>
    </InfoNote>
  );
}

/** The three views and the layers of the player. */
export function PlayerInfo() {
  return (
    <InfoNote title="How to read the player">
      <dl>
        <dt>Every image</dt>
        <dd>
          Each exposure in date order, aligned north-up with one brightness
          scale. What moves jumps from frame to frame; what varies changes
          brightness (check the wavelength first).
        </dd>
        <dt>Survey passes (stacked)</dt>
        <dd>
          The median of all the images of one survey pass (a few weeks, every ~6
          months): less noise, fainter objects, and whatever shows in only one
          image (cosmic rays, something that moved) is removed.
        </dd>
        <dt>Difference</dt>
        <dd>
          A pass minus the reference pass (the first one with at least three
          images). Grey means no change; white = brighter in that pass, black =
          brighter in the reference. A moving star leaves a white–black pair.
          Bright stars leave residuals because the two passes see them at
          different wavelengths.
        </dd>
        <dt>Target marker</dt>
        <dd>
          Where the target is expected on that date (proper motion included).
        </dd>
        <dt>Show flagged pixels / Paint flags</dt>
        <dd>
          Pixels flagged by the SPHEREx pipeline are filled from the surrounding
          sky by default. "Show" displays what the detector recorded; "Paint"
          marks where they are.
        </dd>
        <dt>Gaia / WISE</dt>
        <dd>
          Catalogued sources from ESA Gaia DR3 (visible, positions moved to the
          SPHEREx date) and AllWISE (3.4–22 µm, positions of 2010).
        </dd>
      </dl>
      <p className="small muted">
        Keys: ← → step, space play/pause. The compass shows north and east; the
        bar is 1 arcminute.
      </p>
    </InfoNote>
  );
}

/** What each pipeline flag means (names read from every file's FLAGS header). */
const FLAGS: [string, string, string][] = [
  [
    "TRANSIENT",
    "A jump during the exposure (cosmic ray, start of blooming)",
    "kept",
  ],
  [
    "OVERFLOW",
    "Reached half the pixel's capacity; value from the first reads",
    "kept",
  ],
  ["SUR_ERROR", "The exposure's ramp could not be fitted", "hidden"],
  ["NONFUNC", "Dead pixel", "hidden"],
  ["DICHROIC", "Edge of bands 3–4, less than 50 % throughput", "caution"],
  ["MISSING_DATA", "Lost in transmission", "hidden"],
  ["HOT / COLD", "Too much or no signal in this exposure", "hidden"],
  [
    "NONLINEAR",
    "Brightness correction not reliable (near saturation)",
    "hidden",
  ],
  ["PERSIST", "Ghost of a bright star from a previous exposure", "hidden"],
  ["OUTLIER", "Statistical outlier", "kept"],
  [
    "SOURCE",
    "Light from a catalogued star or asteroid (marks ~45 % of pixels)",
    "kept",
  ],
  [
    "GHOST / CROSSTALK",
    "Optical ghost or electronic echo of a bright source",
    "caution",
  ],
  ["STREAK", "Satellite trail", "caution"],
  ["BLOOM", "Charge spilling from a saturated star", "hidden"],
  ["SNOWBALL", "Giant cosmic-ray hit", "hidden"],
  ["HALO", "Around a cosmic-ray hit", "hidden"],
];

export function FlagsInfo() {
  return (
    <InfoNote title="What do the pixel flags mean?">
      <p>
        Every SPHEREx image comes with a flag for every pixel. The official
        recipe for photometry hides some of them (cosmic rays, persistence and
        halos change from image to image and would look like moving objects) and
        keeps others.
      </p>
      <table>
        <thead>
          <tr>
            <th>Flag</th>
            <th>Meaning</th>
            <th>Here</th>
          </tr>
        </thead>
        <tbody>
          {FLAGS.map(([name, meaning, use]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{meaning}</td>
              <td>{use}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </InfoNote>
  );
}

/** The fields of "About this image". */
export function FrameFieldsInfo() {
  return (
    <InfoNote title="What do these values mean?">
      <dl>
        <dt>Wavelength</dt>
        <dd>
          Centre of the colour seen at the target's pixel, and the width of that
          band (about λ/40; λ/120 in D5–D6). From the file's wavelength table
          (approximate to 0.1 %).
        </dd>
        <dt>Date</dt>
        <dd>
          Middle of the 114 s exposure, in UTC and as a Modified Julian Date
          (MJD, days since 17 Nov 1858). DR1 = first year, QR3 = second year.
        </dd>
        <dt>Quality</dt>
        <dd>
          The pipeline's verdict (L2DQAFLG: Pass), whether the astrometry is
          complete (FINAST), and glows that were present: airglow (helium line
          at 1.083 µm), aurora, or "shuttle glow" (around the spacecraft, at 2.9
          and 4.5 µm).
        </dd>
        <dt>Sky level removed</dt>
        <dd>
          The median brightness of the cutout (mostly zodiacal light, sunlight
          scattered by interplanetary dust), subtracted so frames can be
          compared; and the pixel noise.
        </dd>
        <dt>Flagged pixels</dt>
        <dd>
          Share of the cutout hidden, and how many pixels carry each flag (see
          the flags note).
        </dd>
        <dt>Field covered</dt>
        <dd>
          How much of the chosen field this image covers (images near a detector
          edge cover less).
        </dd>
        <dt>Original file</dt>
        <dd>The full Level 2 FITS file in the IRSA archive.</dd>
      </dl>
    </InfoNote>
  );
}

/** How the spectrum is measured and what each column of the table is. */
export function SpectrumInfo() {
  return (
    <InfoNote title="How is the spectrum measured? What are the columns?">
      <p>
        On every image the brightness of the target is measured in a circle of
        2.5 pixels (15″, about 98 % of a star's light), minus the sky in a ring
        around it. Each image gives one point, at the wavelength of the pixel
        where the target fell; all the images together draw the spectrum from
        0.75 to 5 µm. Each survey pass has its own colour: if the passes
        disagree at the same wavelength, the object changed.
      </p>
      <dl>
        <dt>Wavelength (µm)</dt>
        <dd>
          From the per-pixel spectral calibration maps (the precise ones, for
          science).
        </dd>
        <dt>Flux (mJy)</dt>
        <dd>
          Millijansky (1 mJy = 10⁻²⁹ W m⁻² Hz⁻¹), using each pixel's own solid
          angle.
        </dd>
        <dt>Error (mJy)</dt>
        <dd>
          Pixel noise and sky uncertainty, plus 3 % for the calibration (as the
          official tool).
        </dd>
        <dt>Date, Pass, Detector</dt>
        <dd>
          When the image was taken, which survey pass it belongs to, and which
          detector.
        </dd>
        <dt>Note</dt>
        <dd>
          "suspect" = far from the other points of the same pass at that
          wavelength (usually an unflagged cosmic ray), drawn hollow and shown,
          not removed. "% light on flagged pixels" = the flux was corrected for
          flagged pixels inside the circle (up to 20 %; above that the image is
          skipped).
        </dd>
      </dl>
      <p className="small muted">
        Validated with eps Ind B (a pair of brown dwarfs): its four passes agree
        and its spectrum shows the expected water and methane bands. Very bright
        stars saturate SPHEREx and cannot be measured this way.
      </p>
    </InfoNote>
  );
}

/** The surveys of the sky map. */
export function SurveysInfo() {
  return (
    <InfoNote title="About these surveys">
      <p>
        The same patch of sky seen by other missions, from ultraviolet to
        sub-millimetre. They are all-sky maps (HiPS) served by IRSA and drawn
        with Aladin Lite (CDS).
      </p>
      <ul>
        <li>
          <strong>GALEX</strong> (NASA, 2003–2013): ultraviolet; hot young
          stars.
        </li>
        <li>
          <strong>DSS2</strong>: photographic plates of the visible sky
          (1980s–1990s).
        </li>
        <li>
          <strong>2MASS</strong> (1997–2001): near-infrared J, H, K, the closest
          to SPHEREx's D2–D3.
        </li>
        <li>
          <strong>SPHEREx</strong>: the DR1 all-sky cube, one of its 102
          channels (2.04 µm).
        </li>
        <li>
          <strong>Spitzer</strong> IRAC 3.6 µm: deep, but only parts of the sky.
        </li>
        <li>
          <strong>WISE</strong> (2010): 3.4–22 µm, the closest to SPHEREx's
          D4–D6.
        </li>
        <li>
          <strong>Herschel</strong> PACS 70–160 µm: cold dust, parts of the sky.
        </li>
        <li>
          <strong>Planck</strong>: sub-millimetre; the dust of the Milky Way.
        </li>
      </ul>
    </InfoNote>
  );
}
