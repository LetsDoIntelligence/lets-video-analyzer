import { Fragment } from "react";

/** Minimal inline formatting: paragraphs and **bold**. */
export function RichText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/);
  return (
    <>
      {paragraphs.map((p, i) => (
        <p key={i} className={i > 0 ? "mt-3 text-sm text-ink-3" : undefined}>
          {p.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith("**") && part.endsWith("**") ? (
              <strong key={j} className="font-semibold text-ink">
                {part.slice(2, -2)}
              </strong>
            ) : (
              <Fragment key={j}>{part}</Fragment>
            ),
          )}
        </p>
      ))}
    </>
  );
}
