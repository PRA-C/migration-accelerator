"""Catalog of AI and tool agents in the migration pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    node_id: str
    name: str
    role: str
    description: str
    uses_llm: bool
    wraps: str


AGENT_PIPELINE: tuple[AgentSpec, ...] = (
    AgentSpec(
        node_id="synthetic_data_generator",
        name="SyntheticDataGenerator",
        role="tool",
        description="Generate synthetic CSVs from input_schema DDL into synthetic_data_gen/.",
        uses_llm=False,
        wraps="accelarator.data_gen.defaults.generate_migration_tables",
    ),
    AgentSpec(
        node_id="environment_provisioner",
        name="EnvironmentProvisioner",
        role="tool",
        description="Provision Teradata source tables and BigQuery target dataset from synthetic CSVs.",
        uses_llm=False,
        wraps="reconciliation.schema_provisioner.provision_recon_schemas",
    ),
    AgentSpec(
        node_id="migration_intake",
        name="MigrationIntake",
        role="tool",
        description="Load SQL migration files from src/source_files_for_migration/.",
        uses_llm=False,
        wraps="accelarator.migration_assistant.io_handlers.read_source_migration_files",
    ),
    AgentSpec(
        node_id="migration_transpiler",
        name="MigrationTranspiler",
        role="llm",
        description=(
            "Transpile each migration via Data Engineer (generate) and Data Manager "
            "(validate) with up to 3 retries."
        ),
        uses_llm=True,
        wraps="accelarator.migration_assistant.transpiler.transpile_request",
    ),
    AgentSpec(
        node_id="recon_preparer",
        name="ReconPreparer",
        role="tool",
        description="Execute source and target SQL for each run and export reconciliation CSVs.",
        uses_llm=False,
        wraps="reconciliation.recon_executor.prepare_migration_run",
    ),
    AgentSpec(
        node_id="recon_comparator",
        name="ReconComparator",
        role="tool",
        description="Compare source vs target CSVs and update metadata recon_passed flags.",
        uses_llm=False,
        wraps="reconciliation.compare_results.compare_runs",
    ),
    AgentSpec(
        node_id="recon_analyst",
        name="ReconAnalyst",
        role="llm",
        description="Write reconciliation markdown report with optional LLM root-cause analysis.",
        uses_llm=True,
        wraps="reconciliation.recon_report.generate_reconciliation_report",
    ),
    AgentSpec(
        node_id="regression_runner",
        name="RegressionRunner",
        role="tool",
        description="Run unit, asset, and optional integration regression tests.",
        uses_llm=False,
        wraps="test_generator.runner.run_regression_suite",
    ),
    AgentSpec(
        node_id="qa_analyst",
        name="QAAnalyst",
        role="llm",
        description="Generate regression report with optional LLM failure analysis.",
        uses_llm=True,
        wraps="test_generator.report.generate_regression_report",
    ),
    AgentSpec(
        node_id="documentation_generator",
        name="DocumentationGenerator",
        role="tool",
        description="Generate migration overview, lineage diagrams, and per-run docs.",
        uses_llm=False,
        wraps="documentation.generator.generate_documentation",
    ),
    AgentSpec(
        node_id="doc_writer",
        name="DocWriter",
        role="llm",
        description="Optional LLM executive summary in migration_overview.md.",
        uses_llm=True,
        wraps="documentation.generator._llm_executive_summary",
    ),
)


AGENT_BY_NODE: dict[str, AgentSpec] = {spec.node_id: spec for spec in AGENT_PIPELINE}

# LangGraph nodes that invoke an LLM (directly or via bundled analyst sub-agent).
GRAPH_NODE_USES_LLM: frozenset[str] = frozenset({
    "migration_transpiler",       # MigrationTranspiler
    "recon_comparator",             # + ReconAnalyst report analysis
    "regression_runner",            # + QAAnalyst failure analysis
    "documentation_generator",      # + DocWriter executive summary
})


def graph_node_uses_llm(node_id: str) -> bool:
    return node_id in GRAPH_NODE_USES_LLM
