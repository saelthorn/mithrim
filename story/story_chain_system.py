"""
story_chain_system.py

Phase 9 -- Story Chain System.

Provides StoryChain: a directed graph of story chain nodes that turns
individual StoryInstances (Phase 3) into interconnected, procedural
story *chains* -- prerequisites, branching, alternative outcomes, global
consequences, and multiple endings -- without any of it being scripted
by hand. Chains unlock and branch purely by reacting to normal
StoryDirector lifecycle events, which are themselves usually driven by
world events (TriggerSystem, world_time.py's scheduled events, player
actions on StoryObjects, ...).

This is framework only. A ChainNode knows which story it wraps and which
edges lead out of it; it contains no dialogue, clue text, or narrative
content. What each story in the chain actually says or shows is decided
by content systems built on StoryDirector's hooks, exactly as in
story_framework.py.

Design summary
---------------
- ChainOutcome    : the well-known outcome keys every node resolves to
                    from plain StoryState (completed / failed / aborted).
                    A node may resolve to any additional custom key too
                    (e.g. "spared", "betrayed") via its own resolver --
                    see ChainNode.outcome_resolver.
- ChainEdge       : one branch out of a node for a specific outcome --
                    which node comes next, an optional richer Condition
                    gating it (reputation, items, other chains, ...),
                    and consequences scoped to that branch alone.
- ChainNode       : a single story's place in the graph -- its outgoing
                    edges (grouped by outcome), and whether it's a
                    terminal "ending" node.
- StoryChain      : a named graph of ChainNodes: which nodes are roots
                    (no prerequisite), plus consequences that apply
                    globally whenever *any* ending is reached, and
                    consequences scoped to one specific ending.
- ChainRunState   : pure-data record of one chain's progress -- which
                    nodes resolved to which outcome, the path taken, and
                    which ending (if any) was reached. This is what
                    makes "multiple endings" introspectable afterwards.
- StoryChainManager: wires it all together. It never decides *when* a
                    node's story finishes -- it only reacts, via
                    StoryDirector hooks, once one does.

Relationship to the rest of the framework
-------------------------------------------
- StoryChainManager wraps a StoryManager (Phase 3) and a
  StoryQueueManager (Phase 8). It never runs story logic and never
  decides activation policy itself -- it only calls
  StoryQueueManager.enqueue() for the next node(s) once a prerequisite
  node resolves, letting the queue manager's existing priority/
  requirement/cooldown machinery decide *when* that next story actually
  gets to start.
- A node's story must already be registered with StoryManager before
  its chain is registered (create_story()/load_story() first) --
  StoryChainManager only wires progression on top, the same contract
  StoryQueueManager.enqueue() already documents. Non-root nodes are
  deliberately left un-enqueued at registration time: they only enter
  the queue once a prerequisite node resolves down the matching edge,
  so a chain never "runs ahead" of the player's actual choices.
- Branching and endings are driven entirely by StoryDirector's existing
  STORY_COMPLETED / STORY_FAILED / STORY_ABORTED hooks (story_framework.py)
  -- themselves usually the result of TriggerSystem events, StoryObject
  interactions, or world_time.py schedules. StoryChainManager never
  polls; it subscribes once per node and reacts.
- ChainEdge.condition is evaluated through the StoryManager's shared,
  caching ConditionEvaluator (condition_system.py) -- the same instance
  TriggerRule and ActivationRequirement already share, so a condition
  reused across many branches costs nothing extra to check.
- ChainEdge/StoryChain consequences run through the StoryManager's
  shared ConsequenceExecutor (consequence_system.py) against its
  ExecutionContext, exactly like TriggerRule.consequences -- so a
  chain's "world-changing" effects (reputation shifts, region unlocks,
  spawned NPCs, ...) use the same safe, reversible, serializable
  machinery as everything else in the framework instead of a bespoke
  path.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from story_framework import StoryEvent

if TYPE_CHECKING:
    from story_framework import StoryDirector, StoryInstance, StoryManager
    from story_queue_manager import ActivationRequirement, StoryQueueManager
    from condition_system import Condition, ConditionContext
    from consequence_system import Consequence, ConsequenceExecutor


# ---------------------------------------------------------------------------
# ChainOutcome
# ---------------------------------------------------------------------------

class ChainOutcome:
    """
    Well-known outcome keys a ChainNode resolves to by default, derived
    straight from StoryState. Not an Enum -- content is free to resolve
    to any other string key (via a node's own `outcome_resolver`, e.g.
    reading a story flag like "ending_choice") for finer-grained
    branching than plain completed/failed/aborted.
    """
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


def _default_outcome_resolver(story: "StoryInstance") -> str:
    """Fallback resolver: map StoryState straight onto a ChainOutcome
    key. Used whenever a ChainNode doesn't supply its own resolver."""
    if story.state.value == ChainOutcome.COMPLETED:
        return ChainOutcome.COMPLETED
    if story.state.value == ChainOutcome.FAILED:
        return ChainOutcome.FAILED
    return ChainOutcome.ABORTED


# ---------------------------------------------------------------------------
# ChainEdge
# ---------------------------------------------------------------------------

class ChainEdge:
    """
    One branch leading out of a ChainNode for a specific outcome.

    Edges are plain data plus two optional escape hatches, mirroring
    TriggerRule/ActivationRequirement's approach elsewhere in the
    framework: a richer `condition` for gating a branch on state beyond
    the outcome itself (reputation, items, another chain's ending, ...),
    and `consequences` scoped to this branch alone (as opposed to
    StoryChain's chain-wide `global_consequences`).
    """

    def __init__(
        self,
        outcome: str,
        next_node_id: str,
        condition: Optional["Condition"] = None,
        consequences: Optional[List["Consequence"]] = None,
        requirement: Optional["ActivationRequirement"] = None,
        edge_id: Optional[str] = None,
    ):
        self.id: str = edge_id or f"{outcome}->{next_node_id}:{id(self):x}"
        self.outcome: str = outcome
        self.next_node_id: str = next_node_id

        # Optional richer gate (see condition_system.py), evaluated
        # through the StoryManager's shared ConditionEvaluator.
        self.condition: Optional["Condition"] = condition
        # Branch-specific effects (see consequence_system.py), run
        # through the StoryManager's shared ConsequenceExecutor whenever
        # this edge is the one actually taken.
        self.consequences: List["Consequence"] = list(consequences or [])
        # Optional override for the next node's queue ActivationRequirement
        # (e.g. this branch should require a cooldown or a min level the
        # other branches don't). None means "use whatever requirement the
        # queue manager is called with", left to the caller.
        self.requirement: Optional["ActivationRequirement"] = requirement

    def __repr__(self) -> str:
        return f"ChainEdge(outcome={self.outcome!r}, next={self.next_node_id!r})"


# ---------------------------------------------------------------------------
# ChainNode
# ---------------------------------------------------------------------------

class ChainNode:
    """
    A single story's place within a StoryChain.

    Holds no narrative content -- only its story_id, its outgoing edges
    grouped by outcome, and whether it terminates the chain. `exclusive`
    controls how multiple edges registered under the *same* outcome are
    treated: exclusive (the default) takes the first edge whose
    condition passes -- a single branching choice; non-exclusive takes
    every edge whose condition passes -- a fan-out unlocking several
    follow-up stories at once.
    """

    def __init__(
        self,
        node_id: str,
        story_id: str,
        outcome_resolver: Optional[Callable[["StoryInstance"], str]] = None,
        ending_id: Optional[str] = None,
        exclusive: bool = True,
    ):
        self.id: str = node_id
        self.story_id: str = story_id
        self.outcome_resolver: Callable[["StoryInstance"], str] = (
            outcome_resolver or _default_outcome_resolver
        )
        # Set on terminal nodes only. Distinct string ids let a chain
        # have several different endings, not just "finished or not".
        self.ending_id: Optional[str] = ending_id
        self.exclusive: bool = exclusive

        self._edges: Dict[str, List[ChainEdge]] = {}

    # -- graph construction ---------------------------------------------------

    def add_edge(self, edge: ChainEdge) -> "ChainNode":
        """Register an outgoing edge. Returns self so edges can be
        chained fluently while building a chain."""
        self._edges.setdefault(edge.outcome, []).append(edge)
        return self

    def get_edges(self, outcome: str) -> List[ChainEdge]:
        return list(self._edges.get(outcome, ()))

    def all_edges(self) -> List[ChainEdge]:
        return [edge for edges in self._edges.values() for edge in edges]

    def is_ending(self) -> bool:
        return self.ending_id is not None

    def __repr__(self) -> str:
        return f"ChainNode(id={self.id!r}, story_id={self.story_id!r}, ending={self.ending_id!r})"


# ---------------------------------------------------------------------------
# StoryChain
# ---------------------------------------------------------------------------

class StoryChain:
    """
    A named directed graph of ChainNodes: one procedural story chain.

    `global_consequences` run once whenever the chain reaches *any*
    ending, regardless of which branch got there -- for effects that
    should always happen once the chain concludes (e.g. the region's
    threat level drops). `ending_consequences` are keyed by ending_id
    for effects specific to a single ending (e.g. only the "bandits
    routed" ending spawns a victory merchant).
    """

    def __init__(
        self,
        chain_id: str,
        root_node_ids: Optional[List[str]] = None,
        global_consequences: Optional[List["Consequence"]] = None,
    ):
        self.id: str = chain_id
        self.nodes: Dict[str, ChainNode] = {}
        self.root_node_ids: List[str] = list(root_node_ids or [])
        self.global_consequences: List["Consequence"] = list(global_consequences or [])
        self.ending_consequences: Dict[str, List["Consequence"]] = {}

        # story_id -> node_id, kept in sync by add_node() so
        # StoryChainManager can resolve "which node just finished"
        # without a linear scan.
        self._node_by_story: Dict[str, str] = {}

    # -- graph construction ---------------------------------------------------

    def add_node(self, node: ChainNode, root: bool = False) -> ChainNode:
        """Register a node with this chain. Set root=True as a shortcut
        for also adding it to root_node_ids."""
        self.nodes[node.id] = node
        self._node_by_story[node.story_id] = node.id
        if root and node.id not in self.root_node_ids:
            self.root_node_ids.append(node.id)
        return node

    def set_ending_consequences(self, ending_id: str, consequences: List["Consequence"]) -> None:
        self.ending_consequences[ending_id] = list(consequences)

    # -- lookups ---------------------------------------------------------------

    def node_for_story(self, story_id: str) -> Optional[ChainNode]:
        node_id = self._node_by_story.get(story_id)
        return self.nodes.get(node_id) if node_id else None

    def get_ending_ids(self) -> Set[str]:
        return {node.ending_id for node in self.nodes.values() if node.is_ending()}

    # -- validation -------------------------------------------------------

    def validate(self) -> List[str]:
        """
        Check internal graph consistency. Returns a list of human-
        readable problems; an empty list means the chain is valid.
        """
        problems: List[str] = []

        if not self.id:
            problems.append("Chain has no id.")
        if not self.root_node_ids:
            problems.append("Chain has no root nodes.")

        for root_id in self.root_node_ids:
            if root_id not in self.nodes:
                problems.append(f"Root node {root_id!r} is not registered on the chain.")

        for node in self.nodes.values():
            for edge in node.all_edges():
                if edge.next_node_id not in self.nodes:
                    problems.append(
                        f"Node {node.id!r} has an edge to unknown node {edge.next_node_id!r}."
                    )
            if not node.is_ending() and not node.all_edges():
                problems.append(f"Node {node.id!r} is not an ending but has no outgoing edges.")

        return problems

    def is_valid(self) -> bool:
        return not self.validate()

    def __repr__(self) -> str:
        return f"StoryChain(id={self.id!r}, nodes={len(self.nodes)}, endings={sorted(self.get_ending_ids())})"


# ---------------------------------------------------------------------------
# ChainRunState
# ---------------------------------------------------------------------------

class ChainRunState:
    """
    Pure-data record of one chain's progress at runtime.

    Kept separate from StoryChain (the static graph) the same way
    StoryInstance is kept separate from story content -- this is what
    gets persisted/inspected, while the graph itself stays fixed,
    reusable definition data.
    """

    def __init__(self, chain_id: str):
        self.chain_id: str = chain_id
        # node_id -> outcome it resolved to, in resolution order.
        self.resolved_nodes: Dict[str, str] = {}
        self.path: List[str] = []
        self.reached_ending_id: Optional[str] = None

    def record(self, node_id: str, outcome: str) -> None:
        self.resolved_nodes[node_id] = outcome
        self.path.append(node_id)

    def is_finished(self) -> bool:
        return self.reached_ending_id is not None

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "resolved_nodes": dict(self.resolved_nodes),
            "path": list(self.path),
            "reached_ending_id": self.reached_ending_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChainRunState":
        run = cls(chain_id=data["chain_id"])
        run.resolved_nodes = dict(data.get("resolved_nodes", {}))
        run.path = list(data.get("path", []))
        run.reached_ending_id = data.get("reached_ending_id")
        return run

    def __repr__(self) -> str:
        status = self.reached_ending_id or "in progress"
        return f"ChainRunState(chain_id={self.chain_id!r}, status={status!r}, steps={len(self.path)})"


# ---------------------------------------------------------------------------
# StoryChainManager
# ---------------------------------------------------------------------------

class StoryChainManager:
    """
    Orchestrates many StoryChains atop a StoryManager and a
    StoryQueueManager.

    Nothing here is scripted per story: a chain progresses purely by
    reacting to a node's story finishing (STORY_COMPLETED / STORY_FAILED
    / STORY_ABORTED, fired by StoryDirector -- see story_framework.py).
    Those events already happen "naturally" through world events
    (TriggerSystem rules, StoryObject interactions, world_time.py
    schedules) elsewhere in the stack; this manager only listens for
    them and, once a node resolves, decides which edges apply and hands
    the next node(s)' stories to the wrapped StoryQueueManager -- which
    in turn only activates them once its own requirements are met. A
    chain therefore never "jumps ahead" of the player or the world.
    """

    def __init__(
        self,
        story_manager: "StoryManager",
        queue_manager: "StoryQueueManager",
        consequence_executor: Optional["ConsequenceExecutor"] = None,
    ):
        self.story_manager: "StoryManager" = story_manager
        self.queue_manager: "StoryQueueManager" = queue_manager
        # Reuse the manager's shared executor by default, same reasoning
        # as StoryQueueManager reusing the shared ConditionEvaluator.
        self.consequence_executor: "ConsequenceExecutor" = (
            consequence_executor or story_manager.consequence_executor
        )

        self._chains: Dict[str, StoryChain] = {}
        self._runs: Dict[str, ChainRunState] = {}

    # -- registration -----------------------------------------------------

    def register_chain(
        self,
        chain: StoryChain,
        priority: int = 0,
        root_requirement: Optional["ActivationRequirement"] = None,
    ) -> ChainRunState:
        """
        Register a chain, wire every node's story lifecycle hooks, and
        enqueue only its root node(s) -- everything downstream stays
        unenqueued until a prerequisite node's outcome actually unlocks
        it. Every node's story must already exist in the wrapped
        StoryManager (create_story()/load_story() first); this only
        wires progression on top, the same contract StoryQueueManager.
        enqueue() documents.
        """
        self._chains[chain.id] = chain
        run = ChainRunState(chain.id)
        self._runs[chain.id] = run

        for node in chain.nodes.values():
            self._wire_node(chain, node)

        for root_id in chain.root_node_ids:
            root = chain.nodes[root_id]
            self.queue_manager.enqueue(root.story_id, priority=priority, requirement=root_requirement)

        return run

    def _wire_node(self, chain: StoryChain, node: ChainNode) -> None:
        director = self.story_manager.get_director(node.story_id)
        if director is None:
            return  # story not loaded yet -- content is responsible for creating it first

        def on_finished(story: "StoryInstance", **_context: Any) -> None:
            self._on_node_resolved(chain, node)

        director.on(StoryEvent.STORY_COMPLETED, on_finished)
        director.on(StoryEvent.STORY_FAILED, on_finished)
        director.on(StoryEvent.STORY_ABORTED, on_finished)

    # -- reaction to world-driven story completion -------------------------

    def _on_node_resolved(self, chain: StoryChain, node: ChainNode) -> None:
        story = self.story_manager.get_story(node.story_id)
        if story is None:
            return

        outcome = node.outcome_resolver(story)
        run = self._runs[chain.id]
        run.record(node.id, outcome)

        if node.is_ending():
            self._reach_ending(chain, run, node)
            return

        self._follow_edges(chain, run, node, outcome)

    def _follow_edges(self, chain: StoryChain, run: ChainRunState, node: ChainNode, outcome: str) -> None:
        context = self.story_manager.condition_context

        for edge in node.get_edges(outcome):
            if edge.condition is not None and not self._condition_holds(edge.condition, context):
                continue

            self._apply(edge.consequences)
            self._unlock_next(chain, edge)

            if node.exclusive:
                break  # first satisfied branch wins; the rest are alternatives, not fan-out

    def _unlock_next(self, chain: StoryChain, edge: ChainEdge) -> None:
        next_node = chain.nodes.get(edge.next_node_id)
        if next_node is None:
            return
        self.queue_manager.enqueue(next_node.story_id, requirement=edge.requirement)

    def _reach_ending(self, chain: StoryChain, run: ChainRunState, node: ChainNode) -> None:
        run.reached_ending_id = node.ending_id
        self._apply(chain.global_consequences)
        self._apply(chain.ending_consequences.get(node.ending_id, []))

    # -- shared condition/consequence plumbing -----------------------------

    def _condition_holds(self, condition: "Condition", context: Optional["ConditionContext"]) -> bool:
        """Mirrors StoryManager._check_rule_condition(): fails closed
        (branch not taken) if no ConditionContext has been supplied yet."""
        if context is None:
            return False
        return self.story_manager.condition_evaluator.evaluate(condition, context)

    def _apply(self, consequences: List["Consequence"]) -> None:
        """Mirrors StoryManager._run_rule_consequences(): a missing
        ExecutionContext or a failed consequence is swallowed here
        rather than raised, since Consequence.execute() already
        guarantees it never raises."""
        context = self.story_manager.execution_context
        if not consequences or context is None:
            return
        for consequence in consequences:
            self.consequence_executor.execute(consequence, context)

    # -- retrieval ------------------------------------------------------

    def get_chain(self, chain_id: str) -> Optional[StoryChain]:
        return self._chains.get(chain_id)

    def get_run(self, chain_id: str) -> Optional[ChainRunState]:
        return self._runs.get(chain_id)

    def list_chains(self) -> List[StoryChain]:
        return list(self._chains.values())

    # -- bulk persistence -------------------------------------------------

    def save_runs(self) -> Dict[str, Any]:
        """Serialize every chain's run progress. Chain *graphs* (nodes,
        edges, conditions, consequences) are definition data supplied by
        content, not runtime state -- like TriggerRule/ActivationRequirement
        elsewhere in the framework, they are expected to be rebuilt and
        re-registered by content-layer code, not round-tripped here."""
        return {"runs": [run.to_dict() for run in self._runs.values()]}

    def load_runs(self, data: Dict[str, Any]) -> None:
        """Restore run progress after chains have been re-registered via
        register_chain(). Only touches runs for chains already known to
        this manager; unknown chain ids in the data are ignored."""
        for run_data in data.get("runs", []):
            chain_id = run_data.get("chain_id")
            if chain_id in self._chains:
                self._runs[chain_id] = ChainRunState.from_dict(run_data)

    def __len__(self) -> int:
        return len(self._chains)

    def __repr__(self) -> str:
        finished = sum(1 for run in self._runs.values() if run.is_finished())
        return f"StoryChainManager(chains={len(self._chains)}, finished={finished})"