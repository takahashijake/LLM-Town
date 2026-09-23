import pytest

from src.llm.response_contract import (
    OutputConstraintMode, TRANSFORMERS_CAPABILITIES, grounded_response_schema,
)


def test_canonical_schema_has_bounded_grounding_refs_and_flat_optional_fields():
    schema = grounded_response_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["grounding_refs"]["maxItems"] == 3
    assert schema["properties"]["follow_through"]["required"] == [
        "kind", "target", "grounding_ref",
    ]


def test_transformers_capabilities_reject_unavailable_native_constraints():
    assert TRANSFORMERS_CAPABILITIES.select(OutputConstraintMode.PROMPTED_JSON) == OutputConstraintMode.PROMPTED_JSON
    with pytest.raises(ValueError, match="does not support native_json_schema"):
        TRANSFORMERS_CAPABILITIES.select(OutputConstraintMode.NATIVE_JSON_SCHEMA)
