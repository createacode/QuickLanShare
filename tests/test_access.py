from __future__ import annotations

import unittest

from quicklanshare.services.access import is_ip_allowed, normalize_ipv4
from quicklanshare.utils.app_config import ServerSettings

SERVER = "192.168.10.25"


class AccessScopeTests(unittest.TestCase):
    def test_default_last_octet(self) -> None:
        self.assertTrue(is_ip_allowed(SERVER, "192.168.10.99", "last1"))
        self.assertFalse(is_ip_allowed(SERVER, "192.168.11.99", "last1"))

    def test_last_two_octets(self) -> None:
        self.assertTrue(is_ip_allowed(SERVER, "192.168.99.99", "last2"))
        self.assertFalse(is_ip_allowed(SERVER, "192.169.99.99", "last2"))

    def test_last_three_octets(self) -> None:
        self.assertTrue(is_ip_allowed(SERVER, "192.99.99.99", "last3"))
        self.assertFalse(is_ip_allowed(SERVER, "193.99.99.99", "last3"))

    def test_all_and_loopback(self) -> None:
        self.assertTrue(is_ip_allowed(SERVER, "10.0.0.8", "all"))
        self.assertTrue(is_ip_allowed(SERVER, "127.0.0.1", "last1"))
        self.assertTrue(is_ip_allowed(SERVER, "::ffff:127.0.0.1", "last1"))

    def test_invalid_scope_falls_back_to_last_octet(self) -> None:
        self.assertTrue(is_ip_allowed(SERVER, "192.168.10.3", "bad"))
        self.assertFalse(is_ip_allowed(SERVER, "192.168.11.3", "bad"))

    def test_normalize_ipv4(self) -> None:
        self.assertEqual(normalize_ipv4("::ffff:192.168.1.2"), "192.168.1.2")
        self.assertIsNone(normalize_ipv4("not-an-ip"))

    def test_config_rejects_unknown_scope(self) -> None:
        config = ServerSettings.from_dict({"ip_scope": "bad"})
        self.assertEqual(config.ip_scope, "last1")
        config = ServerSettings.from_dict({"ip_scope": "last3"})
        self.assertEqual(config.ip_scope, "last3")


if __name__ == "__main__":
    unittest.main()
