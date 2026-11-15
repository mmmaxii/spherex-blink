import { useEffect, useRef } from "react";

/**
 * "How it works": a short guide opened from the (i) button. A native <dialog>, so Escape closes
 * it and focus stays inside while it is open.
 */
export function InfoDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className="glass info"
      onClose={onClose}
      aria-labelledby="info-title"
    >
      {/* The close button comes first: the browser focuses it on open, so the guide starts at the top. */}
      <form method="dialog" className="panel-title">
        <h2 id="info-title">How SPHEREx Blink works</h2>
        <button className="info-button" aria-label="Close">
          ✕
        </button>
      </form>
      <p>
        NASA's SPHEREx telescope photographs the whole sky again and again in
        102 infrared colours (0.75–5 µm). This tool shows how one patch of sky
        changed between those dates: what moves, what brightens or fades.
      </p>

      <h3>The mission and the data</h3>
      <p>
        SPHEREx was launched on 12 March 2025 and, since May 2025, maps the
        whole sky every six months (four times in 25 months), more often near
        the ecliptic poles. A filter whose colour changes across each of its six
        detectors makes every row of an image see a different wavelength;
        stepping across the sky, each star is seen in all 102 colours. The
        images used here are the public Level 2 spectral images of DR1 (first
        year) and QR3 (second year) from NASA/IPAC IRSA, calibrated in MJy/sr
        with a quality flag on every pixel.
      </p>

      <h3>1. Choose a field</h3>
      <ul>
        <li>
          Move over the map: the coordinates follow the cursor. Click (or tap)
          to fix the field.
        </li>
        <li>
          Or type RA, Dec and the field size, and press "Preview on the map".
        </li>
        <li>
          Or go to an object by name, such as the challenge's test targets.
        </li>
        <li>
          The field follows the zoom of the map, between 3′ and 20′ (one SPHEREx
          pixel is 6.15″). The yellow square shows it.
        </li>
      </ul>

      <h3>2. Analyse</h3>
      <p>
        The tool asks the NASA/IPAC archive (IRSA) which SPHEREx images cover
        the field, reads only the small piece of each image that is needed,
        aligns them north-up and plays them as a short video. The preview uses
        the detector with most images.
      </p>

      <h3>3. Full analysis</h3>
      <ul>
        <li>
          Every image, one stack per survey pass (more signal, less noise) and
          differences between passes.
        </li>
        <li>The six detectors: each one covers a range of wavelengths.</li>
        <li>
          The spectrum of the object, measured on every image, one colour per
          pass.
        </li>
        <li>
          Gaia and WISE catalogues on top, and the same field seen by other
          telescopes.
        </li>
        <li>
          The address holds every option: copy it to share the exact view.
        </li>
      </ul>

      <h3>Good to know</h3>
      <ul>
        <li>
          Each SPHEREx image sees the field at a different wavelength. A change
          of brightness between two images can be the colour, not time: every
          image is labelled with its wavelength.
        </li>
        <li>
          Pixels flagged by the SPHEREx pipeline (cosmic rays, persistence,
          halos) are filled from the surrounding sky in the pictures;
          measurements never use them.
        </li>
        <li>
          Very bright stars saturate SPHEREx: their spectrum cannot be measured
          with an aperture.
        </li>
        <li>
          The mission buttons change the map only (from ultraviolet to
          sub-millimetre). Those surveys were taken years before SPHEREx: a fast
          star is somewhere else today.
        </li>
        <li>
          Your last five analyses are kept in this browser only (menu ☰).
        </li>
      </ul>

      <p className="small muted">
        Data: SPHEREx DR1 + QR3 spectral images (NASA/IPAC IRSA). Sky map:
        Aladin Lite (CDS) with surveys served by IRSA. Built for the NASA Space
        Apps Challenge 2026.
      </p>
      <form method="dialog">
        <button className="primary">Close</button>
      </form>
    </dialog>
  );
}
