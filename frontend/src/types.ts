export type PipelineOptions = {
  use_llm: boolean;
  skip_synthetic: boolean;
  skip_provision: boolean;
  skip_migrate: boolean;
  skip_recon: boolean;
  skip_tests: boolean;
  skip_docs: boolean;
  integration_tests: boolean;
  preset: string;
  source_database: string;
  target_database: string;
};

export type DbOption = { value: string; label: string };

export type MigrationProfile = {
  sources: DbOption[];
  targets: DbOption[];
  defaults: { source: string; target: string };
  provisioned_pairs: { source: string; target: string }[];
};

export const DB_SHORT: Record<string, string> = {
  teradata: "TD",
  oracle: "OR",
  mssql: "SS",
  netezza: "NZ",
  postgres: "PG",
  mysql: "MY",
  snowflake: "SF",
  redshift: "RS",
  bigquery: "BQ",
  azure_synapse: "AS",
  spark: "SP",
};

export function dbLabel(value: string, options?: DbOption[]): string {
  const hit = options?.find((o) => o.value === value);
  return hit?.label ?? value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const defaultOptions = (): PipelineOptions => ({
  use_llm: true,
  skip_synthetic: false,
  skip_provision: false,
  skip_migrate: false,
  skip_recon: false,
  skip_tests: false,
  skip_docs: false,
  integration_tests: false,
  preset: "full",
  source_database: "teradata",
  target_database: "bigquery",
});

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type AgentStep = {
  index: number;
  node_id: string;
  name: string;
  role: string;
  uses_llm: boolean;
  state: "pending" | "active" | "done";
};

export type MigrationRun = {
  run_id: number;
  source_file: string | null;
  success: boolean;
  validation_passed: boolean;
  recon_passed: boolean | null;
  recon_ind: string | null;
  created_at: string;
};

export type FeedEvent = {
  id: string;
  ts: number;
  kind: "info" | "agent" | "data" | "success" | "error";
  title: string;
  detail?: string;
  nodeId?: string;
};

export type EnvStatus = { name: string; configured: boolean; label: string };

/** LangGraph pipeline nodes (must match backend GRAPH_NODE_ORDER). */
export const GRAPH_PIPELINE: {
  node_id: string;
  name: string;
  role: string;
  uses_llm: boolean;
}[] = [
  { node_id: "synthetic_data_generator", name: "SyntheticDataGenerator", role: "tool", uses_llm: false },
  { node_id: "environment_provisioner", name: "EnvironmentProvisioner", role: "tool", uses_llm: false },
  { node_id: "migration_intake", name: "MigrationIntake", role: "tool", uses_llm: false },
  { node_id: "migration_transpiler", name: "MigrationTranspiler", role: "llm", uses_llm: true },
  { node_id: "recon_preparer", name: "ReconPreparer", role: "tool", uses_llm: false },
  { node_id: "recon_comparator", name: "ReconComparator", role: "llm", uses_llm: true },
  { node_id: "regression_runner", name: "RegressionRunner", role: "llm", uses_llm: true },
  { node_id: "documentation_generator", name: "DocumentationGenerator", role: "llm", uses_llm: true },
];

export function buildStepsFromProgress(
  completed: string[],
  active: string,
  nodeStatus: string
): AgentStep[] {
  return GRAPH_PIPELINE.map((spec, i) => ({
    index: i + 1,
    node_id: spec.node_id,
    name: spec.name,
    role: spec.role,
    uses_llm: spec.uses_llm,
    state:
      completed.includes(spec.node_id)
        ? "done"
        : spec.node_id === active && (nodeStatus === "starting" || nodeStatus === "complete")
          ? "active"
          : "pending",
  })) as AgentStep[];
}
