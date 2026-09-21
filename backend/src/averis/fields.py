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
    "shipper": (
        "exporter / shipper",
        "exporter/shipper",
        "shipper / exporter",
        "shipper/exporter",
        "shipper",
        "exporter",
        "托运人",
        "託運人",
        "发货人",
        "發貨人",
        "pengirim",
    ),
    "consignee": (
        "receiving party / consignee",
        "receiving party/consignee",
        "to the order of",
        "consignee",
        "收货人",
        "收貨人",
        "penerima",
    ),
    "notify_party": (
        "notify party/intermediate consignee",
        "party to notify",
        "notify party",
        "notify",
        "通知方",
        "通知人",
        "pihak untuk dimaklumkan",
        "pihak dimaklumkan",
    ),
    "port_of_loading": (
        "port of loading",
        "portof loading",
        "load port",
        "loading port",
        "pol",
        "装货港",
        "裝貨港",
        "装运港",
        "裝運港",
        "pelabuhan muatan",
        "pelabuhan muat",
    ),
    "port_of_discharge": (
        "destination port",
        "port of discharge",
        "portof discharge",
        "discharge port",
        "pod",
        "卸货港",
        "卸貨港",
        "pelabuhan pelepasan",
        "pelabuhan pemunggahan",
    ),
    "container_count": (
        "number of containers or packages",
        "no. of containers or packages",
        "number of containers",
        "no. of containers",
        "container count",
        "total containers",
        "containers",
        "集装箱数量",
        "集裝箱數量",
        "货柜数量",
        "貨櫃數量",
        "bilangan kontena",
        "jumlah kontena",
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
        "毛重",
        "berat kasar",
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

# Non-comparison headings still delimit source regions. Keep their meaning in
# one place so readers and complete-candidate construction agree on boundaries.
DOCUMENT_BOUNDARY_LABELS: Final[tuple[str, ...]] = (
    "b/l no",
    "b/l number",
    "bill of lading no",
    "bill of lading number",
    "booking",
    "shipment id",
    "shipment reference",
    "ocean vessel",
    "vessel",
    "voyage",
    "export carrier",
    "container no",
    "container number",
    "hs code",
    "notes",
    "remarks",
    "instructions",
    "date",
    "航次",
    "船名",
    "备注",
    "catatan",
    "kapal",
)
