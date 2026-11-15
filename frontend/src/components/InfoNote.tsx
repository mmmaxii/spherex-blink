import type { ReactNode } from "react";

/**
 * A collapsible explanation with an (i) mark: closed by default so the page stays short, one
 * click away whenever someone wants to know what they are looking at.
 */
export function InfoNote({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="info-note">
      <summary>
        <span className="info-mark" aria-hidden="true">
          i
        </span>
        {title}
      </summary>
      <div className="info-body">{children}</div>
    </details>
  );
}
