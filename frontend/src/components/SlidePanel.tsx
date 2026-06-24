import type { ReactNode } from "react";

type Props = {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
};

export function SlidePanel({ open, title, subtitle, onClose, children, wide }: Props) {
  return (
    <>
      <div className={`backdrop ${open ? "open" : ""}`} onClick={onClose} />
      <aside className={`slide-panel ${open ? "open" : ""} ${wide ? "wide" : ""}`}>
        <header className="slide-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="slide-body">{children}</div>
      </aside>
    </>
  );
}
