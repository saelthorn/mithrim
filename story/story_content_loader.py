"""
story_content_loader.py

Phase 9 -- Data-Driven Story Content.

Loads whole stories -- metadata, requirements, stages, triggers,
conditions, consequences, dialogue, rewards, and failure states -- from
plain JSON, and wires the results into the existing framework
(StoryManager, StoryQueueManager, StoryFailureManager, StoryChainManager)
without any story needing its own Python module.

See STORY_SCHEMA.md alongside this file for the full JSON schema and a
worked example.

This is framework only, same spirit as every other Phase module: it
contains no narrative content itself, only the translation from data to
the framework objects that already know how to run that content
(TriggerRule, ActivationRequirement, FailurePolicy, StoryObject,
Consequence, Condition). Adding a new story, or changing an existing
one, means editing a JSON file -- never this loader.

Design summary
---------------
- StoryContentError  : raised on malformed content, always naming the
                        offending file so authoring mistakes are easy to
                        trace back to their source.
- DialogueNode/
  DialogueLibrary     : the one piece of genuinely new (but still
                        content-only) data this phase introduces, since
                        no dialogue system existed yet. Pure data --
                        speaker, text, choices -- keyed by story id then
                        node id, so a presentation layer can look up
                        `dialogue_id` off the active stage.
- StoryContentLoader   : reads one file (`load_file`) or every `*.json`
                        file under a directory (`load_directory`),
                        builds a StoryInstance + TriggerRules +
                        ActivationRequirement + FailurePolicy + rewards +
                        objects for each, registers them into the
                        supplied managers, and returns a report
                        (`LoadReport`) so a content pipeline/editor can
                        surface errors without a hard crash.
- Chain assembly        : `chain` blocks are collected during the first
                        pass (StoryChain nodes reference sibling stories
                        that may live in other files) and built into
                        StoryChain objects afterward via
                        `build_chains(report, chain_manager)`.

Relationship to the rest of the framework:
- JSON "requirements"  -> story_queue_manager.ActivationRequirement
- JSON "triggers"      -> trigger_system.TriggerRule (+ StoryInstance.add_trigger_rule)
- JSON "conditions"    -> condition_system.condition_from_dict (named + inline)
- JSON "objects"       -> story_object.story_object_from_dict, placed in the
                          story's SearchArea
- JSON "rewards"       -> consequence_system.consequence_from_dict, run via
                          StoryDirector hooks (STAGE_ADVANCED / STORY_COMPLETED)
- JSON "failure"       -> story_failure_system.FailurePolicy
- JSON "chain"         -> story_chain_system.ChainNode / ChainEdge
- JSON "dialogue"      -> DialogueLibrary (new, content-only data holder)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from story.story_framework import StoryDirector, StoryEvent, StoryManager
from story.trigger_system import TriggerRule, TriggerType
from story.condition_system import Condition, condition_from_dict
from story.consequence_system import Consequence, consequence_from_dict
from story.story_object import story_object_from_dict
from story.story_queue_manager import ActivationRequirement, StoryQueueManager
from story.story_failure_system import FailureMode, FailurePolicy, StoryFailureManager
from story.story_chain_system import ChainEdge, ChainNode, StoryChain, StoryChainManager


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class StoryContentError(ValueError):
    """Raised when a story JSON file is malformed. Always carries the
    source file path so authoring mistakes are easy to trace back."""

    def __init__(self, message: str, source: str):
        super().__init__(f"[{source}] {message}")
        self.source = source


# ---------------------------------------------------------------------------
# Dialogue (new, content-only -- no framework class existed for this yet)
# ---------------------------------------------------------------------------

class DialogueChoice:
    """One player-facing choice on a DialogueNode. `condition` gates
    whether the choice is even shown; `consequences` run if it's picked."""

    def __init__(
        self,
        text: str,
        next_node_id: Optional[str] = None,
        condition: Optional[Condition] = None,
        consequences: Optional[List[Consequence]] = None,
    ):
        self.text: str = text
        self.next_node_id: Optional[str] = next_node_id
        self.condition: Optional[Condition] = condition
        self.consequences: List[Consequence] = consequences or []


class DialogueNode:
    """One beat of dialogue: who's speaking, what they say, and what the
    player can do about it. Pure data -- rendering is a UI concern."""

    def __init__(self, speaker: str, text: str, choices: Optional[List[DialogueChoice]] = None):
        self.speaker: str = speaker
        self.text: str = text
        self.choices: List[DialogueChoice] = choices or []


class DialogueLibrary:
    """
    Every DialogueNode for every loaded story, keyed by story id then
    node id -- matching how a stage's `dialogue_id` looks itself up.
    """

    def __init__(self):
        self._nodes: Dict[str, Dict[str, DialogueNode]] = {}

    def register(self, story_id: str, node_id: str, node: DialogueNode) -> None:
        self._nodes.setdefault(story_id, {})[node_id] = node

    def get(self, story_id: str, node_id: str) -> Optional[DialogueNode]:
        return self._nodes.get(story_id, {}).get(node_id)

    def __len__(self) -> int:
        return sum(len(nodes) for nodes in self._nodes.values())


# ---------------------------------------------------------------------------
# Loaded-story bookkeeping
# ---------------------------------------------------------------------------

class LoadedStory:
    """Everything the loader produced for one JSON file, kept around so
    rewards/stage metadata are reachable at runtime without re-parsing."""

    def __init__(self, story_id: str, source: str):
        self.story_id: str = story_id
        self.source: str = source
        self.metadata: Dict[str, Any] = {}
        self.stage_names: List[str] = []
        self.stage_objectives: List[str] = []
        self.stage_dialogue_ids: List[Optional[str]] = []
        self.chain_block: Optional[Dict[str, Any]] = None


class LoadReport:
    """Result of a load_directory()/load_file() call: what succeeded,
    what failed, and every pending chain block still waiting to be
    assembled by build_chains()."""

    def __init__(self):
        self.loaded: Dict[str, LoadedStory] = {}
        self.errors: List[StoryContentError] = []

    def add_error(self, error: StoryContentError) -> None:
        self.errors.append(error)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __repr__(self) -> str:
        return f"LoadReport(loaded={len(self.loaded)}, errors={len(self.errors)})"


# ---------------------------------------------------------------------------
# StoryContentLoader
# ---------------------------------------------------------------------------

class StoryContentLoader:
    """
    Reads story JSON and registers the result into the supplied
    framework managers.

    One loader instance can be reused across many load_directory() /
    load_file() calls (e.g. a base content pack plus a DLC folder); its
    DialogueLibrary and pending chain blocks accumulate across calls.
    """

    def __init__(
        self,
        story_manager: StoryManager,
        queue_manager: Optional[StoryQueueManager] = None,
        failure_manager: Optional[StoryFailureManager] = None,
    ):
        self.story_manager: StoryManager = story_manager
        self.queue_manager: Optional[StoryQueueManager] = queue_manager
        self.failure_manager: Optional[StoryFailureManager] = failure_manager
        self.dialogue: DialogueLibrary = DialogueLibrary()

        # Named condition trees declared under a story's "conditions"
        # block, resolvable by name from that same story's triggers/
        # chain edges. Cleared and repopulated per file (names are only
        # meaningful within the file that declared them).
        self._named_conditions: Dict[str, Condition] = {}

        # story_id -> pending "chain" block, consumed by build_chains().
        self._pending_chains: Dict[str, Dict[str, Any]] = {}

    # -- public entry points -----------------------------------------------

    def load_directory(self, root: str) -> LoadReport:
        """Load every `*.json` file directly under `root` (non-recursive
        by design -- keep one story pack's directory flat and let the
        content pipeline organize packs as separate roots)."""
        report = LoadReport()
        for path in sorted(Path(root).glob("*.json")):
            self._load_one(path, report)
        return report

    def load_file(self, path: str) -> LoadReport:
        report = LoadReport()
        self._load_one(Path(path), report)
        return report

    def build_chains(self, chain_manager: StoryChainManager) -> List[str]:
        """
        Assemble every pending `chain` block collected so far into
        StoryChain objects and register them. Returns the list of built
        chain_ids. Safe to call incrementally as more content loads --
        already-registered chain_ids are skipped (re-register manually
        via chain_manager if a chain needs to be rebuilt).
        """
        by_chain: Dict[str, List[Dict[str, Any]]] = {}
        for story_id, block in self._pending_chains.items():
            by_chain.setdefault(block["chain_id"], []).append({**block, "story_id": story_id})

        built: List[str] = []
        for chain_id, blocks in by_chain.items():
            nodes = [
                ChainNode(
                    node_id=block["node_id"],
                    story_id=block["story_id"],
                    ending_id=block.get("ending_id"),
                    exclusive=block.get("exclusive", True),
                )
                for block in blocks
            ]
            chain = StoryChain(chain_id=chain_id, nodes=nodes)
            for block in blocks:
                for edge_data in block.get("edges", []):
                    edge = ChainEdge(
                        outcome=edge_data["outcome"],
                        next_node_id=edge_data["next_node_id"],
                        condition=self._resolve_condition(edge_data.get("condition"), block["story_id"]),
                        consequences=[consequence_from_dict(c) for c in edge_data.get("consequences", [])],
                    )
                    chain.get_node(block["node_id"]).add_edge(edge)
            chain_manager.register_chain(chain)
            built.append(chain_id)
        return built

    # -- per-file loading -----------------------------------------------------

    def _load_one(self, path: Path, report: LoadReport) -> None:
        source = str(path)
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            report.add_error(StoryContentError(f"could not parse JSON ({exc})", source))
            return

        try:
            loaded = self._build_story(data, source)
        except StoryContentError as exc:
            report.add_error(exc)
            return
        except (KeyError, TypeError, ValueError) as exc:
            report.add_error(StoryContentError(f"malformed story data: {exc}", source))
            return

        report.loaded[loaded.story_id] = loaded

    def _build_story(self, data: Dict[str, Any], source: str) -> LoadedStory:
        story_id = data.get("id")
        if not story_id:
            raise StoryContentError("missing required field 'id'", source)

        stages = data.get("stages") or [{"id": 0, "name": "start", "objective": ""}]

        self._named_conditions = {
            name: condition_from_dict(cond) for name, cond in data.get("conditions", {}).items()
        }

        director = self.story_manager.create_story(
            story_id=story_id,
            seed=data.get("seed"),
            stage_count=len(stages),
        )
        story = director.story

        self._apply_search_area(story, data.get("search_area"))
        self._apply_objects(director, data.get("objects", []), source)
        self._apply_triggers(story, data.get("triggers", []), story_id)
        self._apply_dialogue(story_id, data.get("dialogue", {}))
        self._apply_rewards(director, data.get("rewards", {}), stages)

        if self.queue_manager is not None:
            self._register_queue_entry(story_id, data.get("requirements", {}))
        if self.failure_manager is not None and "failure" in data:
            self._register_failure_policy(story_id, data["failure"])

        loaded = LoadedStory(story_id=story_id, source=source)
        loaded.metadata = dict(data.get("metadata", {}))
        loaded.stage_names = [stage.get("name", str(stage.get("id", i))) for i, stage in enumerate(stages)]
        loaded.stage_objectives = [stage.get("objective", "") for stage in stages]
        loaded.stage_dialogue_ids = [stage.get("dialogue_id") for stage in stages]

        chain_block = data.get("chain")
        if chain_block:
            self._pending_chains[story_id] = chain_block
            loaded.chain_block = chain_block

        return loaded

    # -- section builders -----------------------------------------------------

    def _resolve_condition(self, cond_data: Any, story_id: str) -> Optional[Condition]:
        """A condition field may be a named reference (string, looked up
        in this file's "conditions" block) or an inline condition dict.
        None passes through unchanged."""
        if cond_data is None:
            return None
        if isinstance(cond_data, str):
            if cond_data not in self._named_conditions:
                raise StoryContentError(
                    f"story {story_id!r} references unknown named condition {cond_data!r}", story_id
                )
            return self._named_conditions[cond_data]
        return condition_from_dict(cond_data)

    def _apply_search_area(self, story: Any, area_data: Optional[Dict[str, Any]]) -> None:
        if not area_data:
            return
        center = tuple(area_data.get("center", (0.0, 0.0)))
        size = tuple(area_data.get("size", (50, 50)))
        story.create_search_area(center=center, size=size, seed=area_data.get("seed"))

    def _apply_objects(self, director: StoryDirector, objects_data: List[Dict[str, Any]], source: str) -> None:
        if not objects_data:
            return
        if director.story.search_area is None:
            raise StoryContentError("'objects' declared but no 'search_area' was given", source)
        for obj_data in objects_data:
            payload = {
                "story_id": director.story.id,
                "object_type": obj_data["object_type"],
                "id": obj_data.get("id"),
                "position": obj_data["position"],
                "repeatable": obj_data.get("repeatable", False),
                "data": obj_data.get("data", {}),
            }
            story_object = story_object_from_dict(payload)
            director.story.search_area.add_object(story_object)

    def _apply_triggers(self, story: Any, triggers_data: List[Dict[str, Any]], story_id: str) -> None:
        for rule_data in triggers_data:
            rule = TriggerRule(
                trigger_type=TriggerType(rule_data["trigger_type"]),
                target_id=rule_data.get("target_id"),
                instigator_id=rule_data.get("instigator_id"),
                location_id=rule_data.get("location_id"),
                min_stage=rule_data.get("min_stage"),
                max_stage=rule_data.get("max_stage"),
                required_flags=rule_data.get("required_flags"),
                data_filters=rule_data.get("data_filters"),
                condition=self._resolve_condition(rule_data.get("condition"), story_id),
                consequences=[consequence_from_dict(c) for c in rule_data.get("consequences", [])],
                repeatable=rule_data.get("repeatable", False),
                rule_id=rule_data.get("rule_id"),
            )
            story.add_trigger_rule(rule)

    def _apply_dialogue(self, story_id: str, dialogue_data: Dict[str, Any]) -> None:
        for node_id, node_data in dialogue_data.items():
            choices = [
                DialogueChoice(
                    text=choice["text"],
                    next_node_id=choice.get("next"),
                    condition=self._resolve_condition(choice.get("condition"), story_id),
                    consequences=[consequence_from_dict(c) for c in choice.get("consequences", [])],
                )
                for choice in node_data.get("choices", [])
            ]
            node = DialogueNode(speaker=node_data.get("speaker", ""), text=node_data.get("text", ""), choices=choices)
            self.dialogue.register(story_id, node_id, node)

    def _apply_rewards(self, director: StoryDirector, rewards_data: Dict[str, Any], stages: List[Dict[str, Any]]) -> None:
        """
        Wires reward Consequences to the director's own hooks rather than
        StoryManager's shared executor, since rewards should fire exactly
        once per stage/completion regardless of whether a host has wired
        an ExecutionContext for TriggerRule consequences yet. The actual
        `execute()` calls still happen lazily, against whatever
        ExecutionContext the host later attaches to StoryManager.
        """
        on_stage_data: Dict[str, List[Dict[str, Any]]] = rewards_data.get("on_stage", {})
        on_stage: Dict[int, List[Consequence]] = {
            int(stage_key): [consequence_from_dict(c) for c in consequences]
            for stage_key, consequences in on_stage_data.items()
        }
        on_complete = [consequence_from_dict(c) for c in rewards_data.get("on_complete", [])]

        # Per-stage "on_enter" consequences declared directly on a stage
        # (see STORY_SCHEMA.md) are folded in alongside rewards.on_stage,
        # so authors can use whichever grouping reads more naturally.
        for index, stage in enumerate(stages):
            on_stage.setdefault(index, [])
            on_stage[index].extend(consequence_from_dict(c) for c in stage.get("on_enter", []))

        if not on_stage and not on_complete:
            return

        def _run(consequences: List[Consequence]) -> None:
            manager = self.story_manager
            if not consequences or manager.execution_context is None:
                return
            for consequence in consequences:
                manager.consequence_executor.execute(consequence, manager.execution_context)

        def _on_stage_advanced(story: Any, stage: int, **_: Any) -> None:
            _run(on_stage.get(stage, []))

        def _on_completed(story: Any, **_: Any) -> None:
            _run(on_complete)

        director.on(StoryEvent.STAGE_ADVANCED, _on_stage_advanced)
        director.on(StoryEvent.STORY_COMPLETED, _on_completed)

    def _register_queue_entry(self, story_id: str, requirements_data: Dict[str, Any]) -> None:
        location = requirements_data.get("location")
        requirement = ActivationRequirement(
            min_player_level=requirements_data.get("min_player_level"),
            location=tuple(location) if location else None,
            max_distance=requirements_data.get("max_distance"),
            required_story_ids=requirements_data.get("required_story_ids"),
            condition=self._resolve_condition(requirements_data.get("condition"), story_id),
            cooldown=requirements_data.get("cooldown_hours", 0.0),
        )
        self.queue_manager.enqueue(story_id, requirement=requirement)

    def _register_failure_policy(self, story_id: str, failure_data: Dict[str, Any]) -> None:
        consequences = {
            FailureMode(mode): [consequence_from_dict(c) for c in items]
            for mode, items in failure_data.get("consequences", {}).items()
        }
        follow_up = {
            FailureMode(mode): target_story_id
            for mode, target_story_id in failure_data.get("follow_up_story_id", {}).items()
        }
        applies_to = failure_data.get("applies_to")
        policy = FailurePolicy(
            scar_tag=failure_data.get("scar_tag"),
            consequences=consequences,
            follow_up_story_id=follow_up,
            applies_to=[FailureMode(m) for m in applies_to] if applies_to else None,
        )
        self.failure_manager.register_policy(story_id, policy)