import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import linkfeger  # noqa: E402

RULES = linkfeger.read_json(os.path.join(linkfeger.HERE, 'rules.json'), {})


def clean(url):
    return linkfeger.clean_url(url, RULES)


class CleanUrl(unittest.TestCase):
    def test_global_parameters_removed(self):
        self.assertEqual(clean('https://example.com/a?utm_source=x&id=5&fbclid=abc'), 'https://example.com/a?id=5')

    def test_only_tracking_removed_all_gone_drops_question_mark(self):
        self.assertEqual(clean('https://example.com/a?utm_source=x&gclid=1'), 'https://example.com/a')

    def test_fragment_kept(self):
        self.assertEqual(clean('https://example.com/a?utm_medium=m#section'), 'https://example.com/a#section')

    def test_google_search_keeps_query(self):
        url = 'https://www.google.com/search?q=System+Wide+URL+Cleaner&sca_esv=294&sxsrf=AK%3A1&ei=ah&biw=1516&uact=5&sclient=gws-wiz-serp'
        self.assertEqual(clean(url), 'https://www.google.com/search?q=System+Wide+URL+Cleaner')

    def test_youtube_keeps_video_time_and_list(self):
        url = 'https://www.youtube.com/watch?v=abc&t=42s&list=PL1&si=xyz&feature=shared'
        self.assertEqual(clean(url), 'https://www.youtube.com/watch?v=abc&t=42s&list=PL1')

    def test_site_rule_does_not_leak_to_other_sites(self):
        self.assertEqual(clean('https://example.com/x?si=1&t=2'), 'https://example.com/x?si=1&t=2')

    def test_subdomain_matches_site(self):
        self.assertEqual(clean('https://music.youtube.com/watch?v=a&si=b'), 'https://music.youtube.com/watch?v=a')

    def test_lookalike_domain_does_not_match(self):
        self.assertEqual(clean('https://notyoutube.com/watch?v=a&si=b'), 'https://notyoutube.com/watch?v=a&si=b')

    def test_excluded_host_untouched(self):
        url = 'https://accounts.google.com/o/oauth2?utm_source=x&client_id=1'
        self.assertEqual(clean(url), url)

    def test_non_url_untouched(self):
        for text in ('hello world', 'see https://a.com?utm_source=x here', 'ftp://a.com/?utm_source=x', ''):
            self.assertEqual(clean(text), text)

    def test_surrounding_whitespace_trimmed_for_single_url(self):
        self.assertEqual(clean(' https://a.com/?utm_source=x\n'), 'https://a.com/')

    def test_param_without_value_and_case_sensitivity(self):
        self.assertEqual(clean('https://a.com/?fbclid&UTM_SOURCE=1'), 'https://a.com/?UTM_SOURCE=1')

    def test_no_query_unchanged(self):
        self.assertEqual(clean('https://a.com/path'), 'https://a.com/path')

    def test_encoding_preserved(self):
        self.assertEqual(clean('https://a.com/?q=a%20b%2Bc&utm_id=1'), 'https://a.com/?q=a%20b%2Bc')

    def test_amazon_keeps_variant_selection(self):
        self.assertEqual(clean('https://www.amazon.de/dp/B0?th=1&psc=1&tag=x&ref_=ab'), 'https://www.amazon.de/dp/B0?th=1&psc=1')


class SharedVectors(unittest.TestCase):
    """The same cases run in the browser extension's JavaScript (tests/test_extension.mjs)."""

    def test_vectors(self):
        import json
        with open(os.path.join(os.path.dirname(__file__), 'vectors.json'), encoding='utf-8') as f:
            for given, expected in json.load(f):
                self.assertEqual(clean(given), expected, given)

    def test_extension_rules_copy_is_in_sync(self):
        copy = linkfeger.read_json(os.path.join(linkfeger.HERE, 'extension', 'rules.json'), None)
        self.assertEqual(copy, RULES)


if __name__ == '__main__':
    unittest.main()
