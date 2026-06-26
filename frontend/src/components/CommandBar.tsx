type Preset = {
  id: string;
  label: string;
  short: string;
  primary?: boolean;
};

const PRESETS: Preset[] = [
  { id: "full", label: "Full pipeline", short: "E2E", primary: true },
  { id: "provision", label: "Provision", short: "Prov" },
  { id: "migrate", label: "Migrate", short: "Mig" },
  { id: "recon", label: "Reconcile", short: "Rec" },
  { id: "tests", label: "Tests", short: "QA" },
  { id: "docs", label: "Docs", short: "Doc" },
];

type Props = {
  disabled?: boolean;
  onRun: (preset: string) => void;
};

export function CommandBar({ disabled, onRun }: Props) {
  return (
    <nav className="command-bar" aria-label="Pipeline presets">
      <div className="command-rail">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={p.primary ? "cmd-btn cmd-btn--primary" : "cmd-btn cmd-btn--ghost"}
            disabled={disabled}
            title={p.label}
            onClick={() => onRun(p.id)}
          >
            {p.primary ? (
              <span className="cmd-play" aria-hidden>
                <span className="cmd-play-triangle" />
              </span>
            ) : null}
            <span className="cmd-label">{p.primary ? "Full" : p.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
