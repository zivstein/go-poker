/** A code-drawn SVG chip glyph (W23): one owned asset, not traced from any
 * reference sheet. Used standalone for chips in front and inside the
 * `ProductLogo`'s `o`. */
export interface ChipProps {
  size?: number;
  className?: string;
  "aria-hidden"?: boolean;
}

export function Chip({ size = 24, className, ...rest }: ChipProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      aria-hidden={rest["aria-hidden"] ?? true}
    >
      <title>Chip</title>
      <circle
        cx="12"
        cy="12"
        r="11"
        fill="var(--chip-body)"
        stroke="var(--chip-edge)"
        strokeWidth="1.5"
      />
      <circle
        cx="12"
        cy="12"
        r="7.5"
        fill="none"
        stroke="var(--chip-marking)"
        strokeWidth="1.25"
        strokeDasharray="3 4"
      />
      <circle cx="12" cy="12" r="3.25" fill="var(--chip-edge)" />
    </svg>
  );
}
