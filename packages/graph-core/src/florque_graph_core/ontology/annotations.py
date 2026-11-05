"""The annotation vocabulary owned by the engine (spec 4.7). Unknown keys are rejected at load."""

from __future__ import annotations

SCHEMA_ANNOTATIONS = {"mixins_version"}

CLASS_ANNOTATIONS = {
    "root",  # "true": anchors the graph (Project)
    "scope",  # project (default) | global: global classes carry no project_id
    "natural_key",  # comma separated slot names identifying a node exactly
    "dedupe_scope",  # parent (default) | root | global | none (natural key and similarity only)
    "merge",  # additive (default) | claims
    "allowed_parent",  # for classes without a kind enum
    "branch",
    "use_when",
    "not_for",  # agent guidance, rendered into the card
    "required_kind_values",  # mixin contract: kind values the host class must offer
    "required_edge",  # mixin contract: edge slot the host class must offer
}

SLOT_ANNOTATIONS = {
    "edge",  # relationship type; marks the slot as an edge
    "edge_properties",  # comma separated slot names allowed as edge properties
    "owner",  # human (default) | evaluator | hub | system
    "immutable",  # always | <status>: frozen once the node reaches that status
}

ENUM_VALUE_ANNOTATIONS = {
    "allowed_parent",  # Class or Class:kind, comma separated
    "requires",  # edge slots that must exist at creation
}

OWNERS = {"human", "evaluator", "hub", "system"}
DEDUPE_SCOPES = {"parent", "root", "global", "none"}
MERGE_MODES = {"additive", "claims"}
