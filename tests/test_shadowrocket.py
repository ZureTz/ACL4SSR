"""Static compatibility and routing regressions; not a Shadowrocket runtime test."""

import ipaddress
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate_shadowrocket as generator


class ShadowrocketConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = generator.generate()
        cls.rules = [line for line in cls.content.split("[Rule]\n", 1)[1].splitlines()
                     if line and not line.startswith("#")]
        # Expand known local snapshots for regression checks. External advertising
        # feeds and live upstream changes are deliberately outside this model.
        cls.expanded = []
        for rule in cls.rules:
            if rule.startswith("RULE-SET,"):
                _, url, policy = rule.split(",")
                path = generator.local_path(url)
                if path:
                    cls.expanded.extend(generator.with_policy(r, policy)
                                        for r in generator.active_rules(path))
            else:
                cls.expanded.append(rule)

    def domain_policy(self, domain):
        for rule in self.expanded:
            kind, *parts = rule.split(",")
            if kind == "FINAL":
                return parts[0]
            if kind not in {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"}:
                continue
            value, policy = parts
            if ((kind == "DOMAIN" and domain == value)
                or (kind == "DOMAIN-SUFFIX" and (domain == value or domain.endswith("." + value)))
                or (kind == "DOMAIN-KEYWORD" and value in domain)):
                return policy

    def test_generated_file_is_current(self):
        self.assertEqual(generator.OUTPUT.read_text(encoding="utf-8"), self.content)

    def test_no_groups_or_process_rules(self):
        self.assertNotIn("[Proxy Group]", self.content)
        self.assertNotIn("[Proxy]", self.content)
        for line in self.rules:
            self.assertFalse(line.startswith("PROCESS-"))
            self.assertNotIn("clash-classic:", line)
            self.assertNotIn("[]", line)
            parts = line.split(",")
            policy = parts[-2] if parts[-1] == "no-resolve" else parts[-1]
            self.assertIn(policy, {"DIRECT", "PROXY", "REJECT"})

    def test_apple_and_games_use_proxy(self):
        for domain in ("www.apple.com", "www.icloud.com", "guzzoni.apple.com",
                       "courier.push.apple.com", "ol.epicgames.com", "origin-a.akamaihd.net",
                       "store.epicgames.com", "www.origin.com", "store.steampowered.com",
                       "www.playstation.com", "www.nintendo.com"):
            with self.subTest(domain=domain):
                self.assertEqual(self.domain_policy(domain), "PROXY")

    def test_steam_cn_stays_direct_before_steam(self):
        for domain in ("dl.steam.clngaa.com", "cdn.steamcontent.com",
                       "cm.steampowered.com", "steamserver.net"):
            with self.subTest(domain=domain):
                self.assertEqual(self.domain_policy(domain), "DIRECT")
        steam_cn = next(i for i, r in enumerate(self.rules) if "/SteamCN.list," in r)
        steam = next(i for i, r in enumerate(self.rules) if "/Steam.list," in r)
        self.assertLess(steam_cn, steam)

    def test_other_policies_and_ad_whitelist(self):
        for domain, policy in (("www.bilibili.com", "DIRECT"), ("www.onedrive.com", "DIRECT"),
                               ("tracking-protection.cdn.mozilla.net", "DIRECT"),
                               ("admarvel.com", "REJECT"), ("www.youtube.com", "PROXY"),
                               ("unmatched-example.invalid", "PROXY")):
            with self.subTest(domain=domain):
                self.assertEqual(self.domain_policy(domain), policy)

    def test_apns_ip_and_no_resolve(self):
        self.assertIn("bypass-system = false", self.content)
        for address in ("17.249.0.1", "2620:149:a44::1"):
            ip = ipaddress.ip_address(address)
            matched = None
            for rule in self.expanded:
                parts = rule.split(",")
                if parts[0] in {"IP-CIDR", "IP-CIDR6"} and ip in ipaddress.ip_network(parts[1]):
                    matched = parts[2]
                    break
            self.assertEqual(matched, "PROXY")
        self.assertIn("IP-CIDR,100.64.0.0/10,DIRECT,no-resolve", self.rules)
        self.assertIn("IP-CIDR6,fd7a:115c:a1e0::/48,DIRECT,no-resolve", self.rules)

    def test_ad_source_and_final_rules(self):
        self.assertIn(f"RULE-SET,{generator.AWA_URL},REJECT", self.rules)
        self.assertEqual(self.rules[-2:], ["GEOIP,CN,DIRECT", "FINAL,PROXY"])
        self.assertEqual(sum(r.startswith("FINAL,") for r in self.rules), 1)
        self.assertEqual(sum(line.startswith("# 已省略 iOS 进程匹配：")
                             for line in self.content.splitlines()), 19)


if __name__ == "__main__":
    unittest.main()
