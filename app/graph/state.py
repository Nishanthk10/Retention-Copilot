from typing import TypedDict

class GraphState(TypedDict,total=False):
    call_id: str
    turn_no: int
    generation: int
    turns: list[dict]
    summary: dict
    context: dict
    candidates: list[dict]
    permitted: list[dict]
    displayed: list[dict]
    failures: int
