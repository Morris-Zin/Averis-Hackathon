from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

FIELDS = (
    "shipper", "consignee", "notify_party", "port_of_loading",
    "port_of_discharge", "container_count", "gross_weight_kg",
)
Category = Literal["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
Field = Literal[
    "shipper", "consignee", "notify_party", "port_of_loading",
    "port_of_discharge", "container_count", "gross_weight_kg",
]


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Category
    status: Literal["OK", "MISMATCH", "NEEDS_REVIEW"]
    review_reason: Literal[
        "wrong_doc_type", "missing_attachment", "unreadable", "missing_value"
    ] | None
    has_defect: bool
    defect_fields: list[Field]

    @model_validator(mode="after")
    def coherent_result(self):
        mismatch = self.status == "MISMATCH"
        if self.has_defect != mismatch or bool(self.defect_fields) != mismatch:
            raise ValueError("MISMATCH requires has_defect and nonempty defect_fields")
        if len(set(self.defect_fields)) != len(self.defect_fields):
            raise ValueError("Duplicate defect fields")
        if (self.status == "NEEDS_REVIEW") != (self.review_reason is not None):
            raise ValueError("Only NEEDS_REVIEW requires a review_reason")
        if self.category != "BL_COMPARISON" and self.status != "OK":
            raise ValueError("Only comparison requests proceed to document checking")
        return self
