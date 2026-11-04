from __future__ import annotations

import contextlib
import unittest
from pathlib import Path

from quicklanshare.services.filenames import (
    InvalidFilename,
    content_disposition,
    is_plain_component,
    quote_url_name,
    resolve_upload_path,
    sanitize_upload_name,
)


class SanitizeUploadNameTests(unittest.TestCase):
    def test_strips_windows_and_posix_paths(self):
        self.assertEqual(sanitize_upload_name(r"..\..\evil.txt"), "evil.txt")
        self.assertEqual(sanitize_upload_name("../../evil.txt"), "evil.txt")
        self.assertEqual(sanitize_upload_name(r"C:\fakepath\photo.jpg"), "photo.jpg")
        self.assertEqual(sanitize_upload_name("/etc/passwd"), "passwd")

    def test_rejects_device_names_and_trailing_dots(self):
        self.assertEqual(sanitize_upload_name("CON.txt"), "_CON.txt")
        self.assertEqual(sanitize_upload_name("lpt1"), "_lpt1")
        self.assertEqual(sanitize_upload_name("report.txt."), "report.txt")

    def test_replaces_illegal_characters(self):
        self.assertEqual(sanitize_upload_name('a<b>c:d"e|f?g*h'), "a_b_c_d_e_f_g_h")

    def test_preserves_unicode_and_hashes(self):
        self.assertEqual(sanitize_upload_name("测试 #1.txt"), "测试 #1.txt")

    def test_empty_names_get_fallback(self):
        self.assertEqual(sanitize_upload_name(""), "upload")
        self.assertEqual(sanitize_upload_name(".."), "upload")
        self.assertEqual(sanitize_upload_name(None), "upload")

    def test_truncates_long_names(self):
        name = sanitize_upload_name("a" * 500 + ".txt")
        self.assertLessEqual(len(name), 180)
        self.assertTrue(name.endswith(".txt"))


class ResolveUploadPathTests(unittest.TestCase):
    def setUp(self):
        self.base = Path.cwd() / "tests" / "_tmp_uploads"
        self.base.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        with contextlib.suppress(OSError):
            self.base.rmdir()

    def test_accepts_plain_names(self):
        path = resolve_upload_path(self.base, "测试 #1.txt")
        self.assertEqual(path.name, "测试 #1.txt")
        self.assertEqual(path.parent, self.base.resolve())

    def test_rejects_traversal(self):
        for name in ("../evil.txt", r"..\evil.txt", "a/b.txt", "/etc/passwd", "C:\\x.txt"):
            with self.subTest(name=name):
                with self.assertRaises(InvalidFilename):
                    resolve_upload_path(self.base, name)

    def test_rejects_reserved_and_temporary_names(self):
        for name in ("download_counts.json", "x.part", "x.tmp", "a:b.txt"):
            with self.subTest(name=name):
                with self.assertRaises(InvalidFilename):
                    resolve_upload_path(self.base, name)

    def test_is_plain_component(self):
        self.assertTrue(is_plain_component("a.txt"))
        self.assertFalse(is_plain_component(""))
        self.assertFalse(is_plain_component("."))
        self.assertFalse(is_plain_component(".."))
        self.assertFalse(is_plain_component("a/b"))


class HeaderTests(unittest.TestCase):
    def test_content_disposition_rfc5987(self):
        header = content_disposition("测试 文件 #1.txt")
        self.assertIn("filename*=UTF-8''", header)
        self.assertIn("%E6%B5%8B%E8%AF%95", header)
        self.assertNotIn("\n", header)
        self.assertNotIn("\r", header)

    def test_quotes_are_escaped_in_ascii_fallback(self):
        header = content_disposition('a"b.txt')
        self.assertIn('filename="a_b.txt"', header)

    def test_quote_url_name(self):
        self.assertEqual(quote_url_name("a#b?.txt"), "a%23b%3F.txt")
