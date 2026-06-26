import type { DbOption, MigrationProfile } from "../types";
import { DB_SHORT } from "../types";
import { CommandBar } from "./CommandBar";

type Props = {
  source: string;
  target: string;
  profile: MigrationProfile | null;
  disabled?: boolean;
  pipelineDisabled?: boolean;
  onSourceChange: (value: string) => void;
  onTargetChange: (value: string) => void;
  onRunPipeline: (preset: string) => void;
};

function DbPicker({
  kind,
  value,
  options,
  disabled,
  onChange,
}: {
  kind: "source" | "target";
  value: string;
  options: DbOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const label = options.find((o) => o.value === value)?.label ?? value;
  return (
    <div className={`route-picker route-picker--${kind}`}>
      <span className="route-picker-kind">{kind}</span>
      <div className={`route-select-wrap route-select-wrap--${value}`}>
        <span className={`route-db-chip ${value}`} aria-hidden>
          {DB_SHORT[value] ?? label.slice(0, 2).toUpperCase()}
        </span>
        <select
          className="route-select-input"
          value={value}
          disabled={disabled}
          aria-label={`${kind} database`}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <span className="route-select-chevron" aria-hidden />
      </div>
    </div>
  );
}

export function MigrationRouteBar({
  source,
  target,
  profile,
  disabled,
  pipelineDisabled,
  onSourceChange,
  onTargetChange,
  onRunPipeline,
}: Props) {
  const sources = profile?.sources ?? [{ value: "teradata", label: "Teradata" }];
  const targets = profile?.targets ?? [{ value: "bigquery", label: "BigQuery" }];
  const liveReady = profile?.provisioned_pairs.some(
    (p) => p.source === source && p.target === target
  );

  return (
    <section className="route-bar" aria-label="Migration route configuration">
      <div className="route-bar-glow" aria-hidden />
      <div className="route-bar-inner">
        <div className="route-heading">
          <div className="route-title-block">
            <span className="route-kicker">Migration route</span>
            <span className="route-sub">Choose source &amp; target before pipeline run</span>
          </div>
          <span className={`route-status ${liveReady ? "live" : "transpile"}`}>
            <i className="route-status-dot" />
            {liveReady ? "Live provision ready" : "Transpile mode"}
          </span>
        </div>

        <div className="route-controls">
          <div className="route-pickers">
            <DbPicker
              kind="source"
              value={source}
              options={sources}
              disabled={disabled}
              onChange={onSourceChange}
            />

            <div className="route-connector" aria-hidden>
              <div className="route-connector-track">
                <span className="route-connector-pulse" />
              </div>
              <span className="route-connector-arrow">→</span>
            </div>

            <DbPicker
              kind="target"
              value={target}
              options={targets}
              disabled={disabled}
              onChange={onTargetChange}
            />
          </div>

          <CommandBar disabled={pipelineDisabled} onRun={onRunPipeline} />
        </div>

        {!liveReady && (
          <p className="route-hint">
            <span className="route-hint-item route-hint-warn">
              Provision: Teradata → BigQuery only
            </span>
          </p>
        )}
      </div>
    </section>
  );
}
