"""Shared shipping vocabulary owned in one place.

Segmentation, verification and inference instructions consume the same field
and category definitions so aliases cannot drift. Layout-specific grouping and
parser-only headings stay in the document reader; this module owns only the
official seven fields, their human labels and the category set.
"""

from typing import Final

from averis.contracts import FIELDS, Category, Field

CATEGORIES: Final[tuple[Category, ...]] = (
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
)

FIELDS_ORDERED: Final[tuple[Field, ...]] = tuple(FIELDS)  # type: ignore[arg-type]

FIELD_LABELS: Final[dict[Field, str]] = {
    "shipper": "Shipper",
    "consignee": "Consignee",
    "notify_party": "Notify party",
    "port_of_loading": "Port of loading",
    "port_of_discharge": "Port of discharge",
    "container_count": "Container count",
    "gross_weight_kg": "Gross weight",
}

# Canonical aliases shared by evidence segmentation, normalization and prompts.
# Parser-only headings (vessel, voyage, B/L number, HS code, etc.) remain in
# documents.py; they help grouping but never define shipment values.
FIELD_ALIASES: Final[dict[Field, tuple[str, ...]]] = {
    "shipper": ("shipper/exporter", "shipper", "exporter"),
    "consignee": ("to the order of", "consignee"),
    "notify_party": ("notify party/intermediate consignee", "notify party", "notify"),
    "port_of_loading": ("port of loading", "portof loading", "load port", "pol"),
    "port_of_discharge": (
        "port of discharge",
        "portof discharge",
        "discharge port",
        "pod",
    ),
    "container_count": (
        "number of containers or packages",
        "no. of containers or packages",
        "number of containers",
        "no. of containers",
        "container count",
        "total containers",
        "containers",
    ),
    "gross_weight_kg": (
        "total gross weight (kg)",
        "total gross weight kg",
        "total gross weight",
        "total gross wt (kgs)",
        "total gross wt kgs",
        "total gross wt",
        "gross weight毛重(kgs)",
        "gross weight (kg)",
        "gross wt (kgs)",
        "gross weight kg",
        "gross weight",
        "gross wt",
    ),
}

FIELD_MEANINGS: Final[dict[Field, str]] = {
    "shipper": "shipper/exporter name and any address actually provided",
    "consignee": "consignee name and any address actually provided",
    "notify_party": "notify party name and any address actually provided",
    "port_of_loading": "port of loading (origin port)",
    "port_of_discharge": "port of discharge (destination port)",
    "container_count": (
        "total number of containers in the shipment, not package count, "
        "container identifier, or equipment size"
    ),
    "gross_weight_kg": (
        "total gross weight of the entire shipment, not an individual "
        "container's weight, net weight, or tare weight; retain the source unit"
    ),
}
