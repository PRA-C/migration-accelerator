"""Build the sequential LangGraph agent pipeline."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    documentation_generator,
    environment_provisioner,
    migration_intake,
    migration_transpiler,
    recon_comparator,
    recon_preparer,
    regression_runner,
)
from .state import PipelineState


def build_pipeline_graph():
    """
    Sequential agent pipeline:

    EnvironmentProvisioner → MigrationIntake → MigrationTranspiler →
    ReconPreparer → ReconComparator (+ ReconAnalyst) →
    RegressionRunner (+ QAAnalyst) → DocumentationGenerator (+ DocWriter)
    """
    graph = StateGraph(PipelineState)

    graph.add_node("environment_provisioner", environment_provisioner)
    graph.add_node("migration_intake", migration_intake)
    graph.add_node("migration_transpiler", migration_transpiler)
    graph.add_node("recon_preparer", recon_preparer)
    graph.add_node("recon_comparator", recon_comparator)
    graph.add_node("regression_runner", regression_runner)
    graph.add_node("documentation_generator", documentation_generator)

    graph.add_edge(START, "environment_provisioner")
    graph.add_edge("environment_provisioner", "migration_intake")
    graph.add_edge("migration_intake", "migration_transpiler")
    graph.add_edge("migration_transpiler", "recon_preparer")
    graph.add_edge("recon_preparer", "recon_comparator")
    graph.add_edge("recon_comparator", "regression_runner")
    graph.add_edge("regression_runner", "documentation_generator")
    graph.add_edge("documentation_generator", END)

    return graph.compile()
