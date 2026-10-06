from __future__ import annotations

import pytest

from app import field_contexts, privacy, public_artifacts, publication


@pytest.mark.parametrize("key, expected", [
    ("firstName", "first_name"),
    ("ownerContact", "owner_contact"),
    ("  HOME-address / ", "home_address"),
    ("ADDRESSProvince", "addressprovince"),
    ("email2Address", "email2_address"),
    ("เลขบัตร / ประชาชน", "เลขบัตร_ประชาชน"),
    ("ที่อยู่บ้าน", "ที่อยู่บ้าน"),
    ("👤contact.Email", "contact_email"),
    ("", ""),
    (None, "none"),
    (123, "123"),
    (["FirstName"], "first_name"),
    ({"phoneNumber": "value"}, "phone_number_value"),
])
def test_normalization_preserves_field_names_and_object_inputs(key, expected):
    for normalize in (
        field_contexts.normalise_key,
        privacy.normalise_key,
        publication._normalise_key,
        public_artifacts._normalise_key,
    ):
        assert normalize(key) == expected


def test_normalization_tracks_changed_object_text_and_bounds_cached_keys():
    class FieldName:
        def __init__(self):
            self.text = "firstName"

        def __str__(self):
            return self.text

    key = FieldName()
    assert field_contexts.normalise_key(key) == "first_name"
    key.text = "lastName"
    assert field_contexts.normalise_key(key) == "last_name"

    field_contexts._normalise_key_text.cache_clear()
    for index in range(4100):
        field_contexts.normalise_key(f"field{index}")
    info = field_contexts._normalise_key_text.cache_info()
    assert info.currsize == info.maxsize == 4096
    field_contexts.normalise_key("field4099")
    assert field_contexts._normalise_key_text.cache_info().hits == info.hits + 1
