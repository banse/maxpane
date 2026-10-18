"""Frozen, standard-library-only handoff for the historical workflow atlas."""

from typing import Literal, TypedDict

WORKFLOW_GUIDE_KEYS = ("workflow_guide",)
WORKFLOW_GUIDE_WIDGET_SIGNATURES = {"WorkflowGuideView": ("workflow_guide",)}


class Source(TypedDict):
    title: str
    date: str
    plane: str
    worker: str
    references: list[str]


class Stat(TypedDict):
    title: str
    value: str
    caption: str


class GuidanceCard(TypedDict):
    title: str
    heading: str
    value: str
    rows: list[str]
    caption: str
    footer: str


class Node(TypedDict):
    id: str
    label: str
    kind: Literal["step", "plane", "merge", "failure", "state"]
    explanation: str
    limits: list[str]
    example: str
    source_excerpt: str
    guidance: list[GuidanceCard]
    guidance_notes: list[str]


class Topic(TypedDict):
    id: str
    number: int
    title: str
    short_title: str
    summary: str
    stats: list[Stat]
    diagram: list[str]
    nodes: list[Node]
    source_excerpt: str


class Catalogue(TypedDict):
    source: Source
    topics: list[Topic]


class Snapshot(TypedDict):
    workflow_guide: Catalogue
