import { useCallback, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { api } from "../api";
import type { AgentStep, FeedEvent, PipelineOptions } from "../types";
import { buildStepsFromProgress, GRAPH_PIPELINE } from "../types";

const FIRST_NODE = GRAPH_PIPELINE[0]?.node_id ?? "environment_provisioner";

let feedSeq = 0;

function pushFeed(
  setFeed: Dispatch<SetStateAction<FeedEvent[]>>,
  ev: Omit<FeedEvent, "id" | "ts">
) {
  setFeed((prev) => [
    { ...ev, id: `f-${++feedSeq}`, ts: Date.now() },
    ...prev.slice(0, 199),
  ]);
}

export function usePipeline(options: PipelineOptions, onRefresh: () => Promise<void>) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [running, setRunning] = useState(false);
  const [activeNode, setActiveNode] = useState("");
  const [phase, setPhase] = useState("idle");
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [summary, setSummary] = useState("");
  const completedRef = useRef<string[]>([]);
  const sawStreamEventRef = useRef(false);

  const loadSteps = useCallback(async (completed: string[], active: string) => {
    const r = await api.agents(completed.join(","), active);
    setSteps(r.steps);
    return r.steps;
  }, []);

  const applyEvent = useCallback((ev: Record<string, unknown>) => {
    if (Array.isArray(ev.completed_nodes)) {
      completedRef.current = [...new Set(ev.completed_nodes as string[])];
    }

    const active = String(ev.active_node || "");
    const nodeStatus = String(ev.node_status || "");
    if (ev.phase) setPhase(String(ev.phase));
    if (active) setActiveNode(active);

    const localSteps = buildStepsFromProgress(
      completedRef.current,
      active,
      nodeStatus
    );
    setSteps(localSteps);

    if (active && (nodeStatus === "starting" || nodeStatus === "complete")) {
      const label = active.replace(/_/g, " ");
      pushFeed(setFeed, {
        kind: nodeStatus === "complete" ? "success" : "agent",
        title: nodeStatus === "complete" ? `${label} complete` : `Running ${label}`,
        detail: String(ev.activity || "").replace(/\*\*/g, "").slice(0, 320),
        nodeId: active,
      });
    }

    if (ev.type === "start") {
      pushFeed(setFeed, {
        kind: "info",
        title: "Pipeline connected",
        detail: String(ev.activity || "Streaming live updates…").slice(0, 200),
      });
    }

    if (ev.type === "complete") {
      pushFeed(setFeed, {
        kind: "success",
        title: "Pipeline complete",
        detail: String(ev.summary || "").slice(0, 400),
      });
    }

    if (ev.type === "error") {
      pushFeed(setFeed, {
        kind: "error",
        title: "Pipeline error",
        detail: String(ev.message || ""),
      });
    }

    if (ev.activity) setSummary(String(ev.activity));
    if (ev.summary && ev.type === "complete") setSummary(String(ev.summary));
  }, []);

  const runPipeline = useCallback(
    async (preset: string) => {
      setRunning(true);
      setPhase("starting");
      setSummary("");
      setActiveNode("");
      completedRef.current = [];
      sawStreamEventRef.current = false;
      setActiveNode(FIRST_NODE);
      setPhase("running");
      setSteps(buildStepsFromProgress([], FIRST_NODE, "starting"));
      const opts = { ...options, preset };

      pushFeed(setFeed, {
        kind: "info",
        title: "Pipeline started",
        detail: `Preset: ${preset} — connecting to agent stream…`,
      });

      try {
        await api.streamPipeline(opts, (ev) => {
          sawStreamEventRef.current = true;
          applyEvent(ev);
        });
        setPhase("complete");
        if (sawStreamEventRef.current) {
          await loadSteps(completedRef.current, "");
        } else {
          pushFeed(setFeed, {
            kind: "error",
            title: "Stream produced no events",
            detail: "Check API on port 8000 and hard-refresh the page (Ctrl+Shift+R).",
          });
        }
        await onRefresh();
      } catch (e) {
        setPhase("error");
        pushFeed(setFeed, { kind: "error", title: "Stream failed", detail: String(e) });
      } finally {
        setRunning(false);
        setActiveNode("");
      }
    },
    [options, applyEvent, loadSteps, onRefresh]
  );

  const initFeed = useCallback(() => {
    pushFeed(setFeed, {
      kind: "info",
      title: "Control plane online",
      detail: "Teradata → LangGraph agents → BigQuery",
    });
  }, []);

  const initSteps = useCallback(() => {
    setSteps(buildStepsFromProgress([], "", ""));
  }, []);

  return {
    steps,
    running,
    activeNode,
    phase,
    feed,
    summary,
    runPipeline,
    loadSteps,
    initSteps,
    setFeed,
    initFeed,
  };
}
