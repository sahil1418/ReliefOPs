"""Function-calling tool declarations for the Gemini copilot.

Each tool maps to a Python handler in `executor.py` that performs the actual
Firestore query or mutation. Schema is in OpenAPI-style JSON since `google-genai`
accepts that shape directly via `types.FunctionDeclaration`.
"""
from __future__ import annotations

from typing import Any

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "query_shipments",
        "description": (
            "List shipments matching one or more filters. Returns at most 20 rows."
            " Use when the user asks about deliveries in flight, stalled shipments,"
            " or shipments tied to a specific volunteer or disaster."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "status": {
                    "type": "STRING",
                    "enum": ["created", "assigned", "in_transit", "delivered", "failed"],
                    "description": "Filter by status. Omit to include any.",
                },
                "disasterId": {"type": "STRING", "description": "Filter by disaster doc id."},
                "volunteerId": {"type": "STRING", "description": "Filter by assigned volunteer uid."},
                "priority": {
                    "type": "STRING",
                    "enum": ["critical", "high", "normal"],
                },
                "limit": {"type": "INTEGER", "description": "Max rows (1-20).", "minimum": 1, "maximum": 20},
            },
        },
    },
    {
        "name": "get_warehouse_stock",
        "description": (
            "Look up current stock levels at a warehouse. If `sku` is provided,"
            " returns just that line item; otherwise returns a per-category summary."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "warehouseId": {"type": "STRING", "description": "Required."},
                "sku": {"type": "STRING", "description": "Optional SKU filter."},
            },
            "required": ["warehouseId"],
        },
    },
    {
        "name": "dispatch_volunteer",
        "description": (
            "Manually assign a volunteer to an existing shipment. Use only when the"
            " user explicitly asks to override the auto-match. Confirms the change"
            " by returning the updated shipment status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "shipmentId": {"type": "STRING"},
                "volunteerId": {"type": "STRING", "description": "User uid (or volunteer doc id)."},
            },
            "required": ["shipmentId", "volunteerId"],
        },
    },
    {
        "name": "summarize_disaster_status",
        "description": (
            "Aggregate a disaster's current operational state: counts of demand"
            " requests by severity, shipments by status, and total kg delivered."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"disasterId": {"type": "STRING"}},
            "required": ["disasterId"],
        },
    },
    {
        "name": "find_similar_past_disasters",
        "description": (
            "Vector-search the `ai_embeddings` collection for past disaster reports"
            " or playbooks similar to the user's free-text query. Returns up to 5"
            " short summaries the model can ground its answer on."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Free-text search."},
                "limit": {"type": "INTEGER", "minimum": 1, "maximum": 5},
            },
            "required": ["query"],
        },
    },
]


SYSTEM_PROMPT = """You are ReliefOps Copilot, an AI dispatcher for an NGO running humanitarian
disaster relief logistics on the Google Cloud / Firebase stack.

Operating rules:
* Use the available tools whenever the user asks about live operational state
  (shipments, inventory, volunteers, disaster summaries). Don't invent data.
* When the user asks for an action (dispatch, reroute), use the matching tool
  rather than describing the action in prose.
* Numbers come from tool results. If a tool returns 0 rows, say so plainly.
* When summarizing tool output, prefer concise tables and bullet points over
  long prose. Markdown is fine; the UI renders it.
* Address the coordinator by their role (e.g., "Coordinator", "Maya"); their
  org and uid are passed in the system context but never expose raw uids unless
  asked.
* If a request is unclear or risky (mass-dispatch, deletes), ask a clarifying
  question first.
"""


__all__ = ["TOOL_DECLARATIONS", "SYSTEM_PROMPT"]
