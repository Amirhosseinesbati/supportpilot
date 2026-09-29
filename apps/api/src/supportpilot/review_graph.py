from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .db import SessionLocal
from .graphs import checkpoint_saver
from .returns import review_return


class ReviewState(TypedDict, total=False):
    workspace_id: str
    proposal_id: str
    proposal_version: str
    decision: str
    actor_id: str
    edited_reason: str | None
    status: str
    idempotent_replay: bool


def _interrupt_for_review(state: ReviewState) -> dict:
    decision = interrupt({"proposal_id": state["proposal_id"],
                          "proposal_version": state["proposal_version"],
                          "action": "Review the exact return proposal version"})
    if decision.get("proposal_id") != state["proposal_id"] or \
            decision.get("version") != state["proposal_version"]:
        raise ValueError("Review does not match the paused proposal version")
    return {"decision": decision["decision"], "actor_id": decision["actor_id"],
            "edited_reason": decision.get("edited_reason")}


def _execute_review(state: ReviewState) -> dict:
    with SessionLocal() as db:
        proposal, replay = review_return(db, workspace_id=state["workspace_id"],
            proposal_id=state["proposal_id"], actor_id=state["actor_id"],
            decision=state["decision"], version=state["proposal_version"],
            edited_reason=state.get("edited_reason"))
        return {"status": proposal.status, "idempotent_replay": replay}


def build_review_graph(checkpointer):
    builder = StateGraph(ReviewState)
    builder.add_node("human_review", _interrupt_for_review)
    builder.add_node("execute_review", _execute_review)
    builder.add_edge(START, "human_review")
    builder.add_edge("human_review", "execute_review")
    builder.add_edge("execute_review", END)
    return builder.compile(checkpointer=checkpointer)


def _config(workspace_id: str, proposal_id: str, version: str) -> dict:
    return {"configurable": {"thread_id": f"return:{workspace_id}:{proposal_id}:{version}"},
            "recursion_limit": 6}


def start_review(*, workspace_id: str, proposal_id: str, version: str) -> None:
    with checkpoint_saver() as saver:
        graph = build_review_graph(saver)
        config = _config(workspace_id, proposal_id, version)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            graph.invoke({"workspace_id": workspace_id, "proposal_id": proposal_id,
                          "proposal_version": version}, config)


def resume_review(*, workspace_id: str, proposal_id: str, version: str,
                  actor_id: str, decision: str, edited_reason: str | None) -> dict:
    start_review(workspace_id=workspace_id, proposal_id=proposal_id, version=version)
    with checkpoint_saver() as saver:
        graph = build_review_graph(saver)
        return graph.invoke(Command(resume={"proposal_id": proposal_id,
            "version": version, "actor_id": actor_id, "decision": decision,
            "edited_reason": edited_reason}), _config(workspace_id, proposal_id, version))
