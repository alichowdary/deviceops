"""Focused broker-password domain-separation tests."""

from __future__ import annotations

import hashlib
import hmac
import re
import unittest

from deviceops_api.device_credentials import (
    BROKER_AUTH_CONTEXT,
    derive_broker_password_from_stored_hash,
    hash_device_secret,
)


class BrokerPasswordDerivationTests(unittest.TestCase):
    def test_derivation_is_deterministic_lowercase_hex_and_domain_separated(self) -> None:
        stored_hash = hash_device_secret("test-device-secret-one")

        first = derive_broker_password_from_stored_hash(stored_hash)
        second = derive_broker_password_from_stored_hash(stored_hash)

        self.assertEqual(first, second)
        self.assertRegex(first, re.compile(r"^[0-9a-f]{64}$"))
        self.assertNotEqual(first, stored_hash)

    def test_different_signing_keys_produce_different_broker_passwords(self) -> None:
        first = derive_broker_password_from_stored_hash(
            hash_device_secret("test-device-secret-one")
        )
        second = derive_broker_password_from_stored_hash(
            hash_device_secret("test-device-secret-two")
        )

        self.assertNotEqual(first, second)

    def test_stored_hex_is_decoded_before_hmac(self) -> None:
        stored_hash = hashlib.sha256(b"test-device-secret").hexdigest()
        expected = hmac.new(
            bytes.fromhex(stored_hash),
            BROKER_AUTH_CONTEXT,
            hashlib.sha256,
        ).hexdigest()
        incorrect_ascii_hex_result = hmac.new(
            stored_hash.encode("ascii"),
            BROKER_AUTH_CONTEXT,
            hashlib.sha256,
        ).hexdigest()

        actual = derive_broker_password_from_stored_hash(stored_hash)

        self.assertEqual(actual, expected)
        self.assertNotEqual(actual, incorrect_ascii_hex_result)


if __name__ == "__main__":
    unittest.main()
