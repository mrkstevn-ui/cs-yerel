import unittest
from unittest.mock import patch

import domain_bot


class DomainBotTests(unittest.TestCase):
    def test_composite_plugin_keys_match_published_list(self):
        domains = domain_bot.load_domains(domain_bot.DOMAIN_FILE)
        active = domain_bot.plugin_coverage(domains)
        self.assertTrue({"Kick", "Animecix", "HDFilmCehennemi", "FullHDFilmizlesene", "Atv", "TLC"} <= active)

    def test_scan_only_updates_packaged_dynamic_provider(self):
        domains = {"Dynamic": "https://old.example", "Static": "https://old-static.example"}
        with (patch.object(domain_bot, "load_domains", return_value=domains),
              patch.object(domain_bot, "plugin_coverage", return_value={"Dynamic"}),
              patch.object(domain_bot, "find_better_domain", return_value="https://new.example") as find,
              patch.object(domain_bot, "save_domains") as save):
            changed, updates = domain_bot.run_scan_and_update()
        self.assertTrue(changed)
        self.assertEqual(updates, {"Dynamic": ("https://old.example", "https://new.example")})
        find.assert_called_once_with("Dynamic", "https://old.example")
        self.assertEqual(save.call_args.args[1]["Static"], "https://old-static.example")

    def test_invalid_active_url_stops_scan(self):
        domains = {"Dynamic": "https://login.example/path?token=secret"}
        with (patch.object(domain_bot, "load_domains", return_value=domains),
              patch.object(domain_bot, "plugin_coverage", return_value={"Dynamic"}),
              patch.object(domain_bot, "find_better_domain") as find):
            with self.assertRaisesRegex(ValueError, "Geçersiz sağlayıcı"):
                domain_bot.run_scan_and_update()
        find.assert_not_called()

    def test_redirect_rejects_login_and_unlisted_domains(self):
        self.assertFalse(domain_bot.trusted_redirect(
            "https://provider.example", "https://login.example/path?token=secret"))
        self.assertFalse(domain_bot.trusted_redirect(
            "https://provider.example", "https://unrelated.example"))
        self.assertTrue(domain_bot.trusted_redirect(
            "https://provider.example", "https://www.provider.example/"))


if __name__ == "__main__":
    unittest.main()
