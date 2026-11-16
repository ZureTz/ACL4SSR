#!/usr/bin/env python3
"""Generate the single-server Shadowrocket profile from Online_Full, offline."""

import argparse
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Clash/config/ACL4SSR_Online_Full.ini"
OUTPUT = ROOT / "Shadowrocket/ACL4SSR_Online_Full.conf"
UPDATE_URL = "https://raw.githubusercontent.com/ZureTz/ACL4SSR/master/Shadowrocket/ACL4SSR_Online_Full.conf"
AWA_URL = "https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-Surge-RULE-SET.list"
POLICIES = {
    "🎯 全球直连": "DIRECT",
    "🛑 广告拦截": "REJECT",
    "🍃 应用净化": "REJECT",
    "🆎 AdBlock": "REJECT",
    "🛡️ 隐私防护": "REJECT",
    "📢 谷歌FCM": "DIRECT",
    "Ⓜ️ 微软Bing": "DIRECT",
    "Ⓜ️ 微软云盘": "DIRECT",
    "Ⓜ️ 微软服务": "DIRECT",
    "🍎 苹果智能": "PROXY",
    "🍎 苹果APN": "PROXY",
    "🍎 苹果服务": "PROXY",
    "📲 电报消息": "PROXY",
    "💬 Ai平台": "PROXY",
    "🎶 网易音乐": "DIRECT",
    "🎮 游戏平台": "PROXY",
    "📹 油管视频": "PROXY",
    "🎥 奈飞视频": "PROXY",
    "📺 巴哈姆特": "PROXY",
    "📺 哔哩哔哩": "DIRECT",
    "🌏 国内媒体": "DIRECT",
    "🌍 国外媒体": "PROXY",
    "🚀 节点选择": "PROXY",
    "🐟 漏网之鱼": "PROXY",
}
SUPPORTED = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6", "URL-REGEX"}
GAME_EXCEPTIONS = {"DOMAIN-SUFFIX,ol.epicgames.com", "DOMAIN,origin-a.akamaihd.net"}


def active_rules(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith(("#", ";", "//"))]


def local_path(url):
    """Only map the two ACL4SSR repositories used by the source template."""
    parsed = urlparse(url)
    for prefix in ("/ACL4SSR/ACL4SSR/master/", "/ZureTz/ACL4SSR/master/"):
        if parsed.netloc == "raw.githubusercontent.com" and parsed.path.startswith(prefix + "Clash/"):
            path = (ROOT / parsed.path[len(prefix):]).resolve()
            if ROOT not in path.parents:
                raise ValueError(f"Invalid source path: {url}")
            return path
    return None


def with_policy(rule, policy):
    kind, value = rule.split(",", 1)
    if kind not in SUPPORTED:
        raise ValueError(f"Unsupported rule: {rule}")
    if kind in {"IP-CIDR", "IP-CIDR6"} and value.endswith(",no-resolve"):
        return f"{kind},{value.removesuffix(',no-resolve')},{policy},no-resolve"
    return f"{rule},{policy}"


def generate():
    lines = [
        "# ACL4SSR Online Full — Shadowrocket 单节点版",
        "# 由 scripts/generate_shadowrocket.py 生成；策略在生成器中维护。",
        "# PROXY 使用首页当前选中的节点；全局路由请选择“配置”。",
        "# 苹果/APNs/游戏走代理；SteamCN 保留直连；广告使用 REJECT。",
        "# APNs：还需在客户端 设置 > 隧道 中启用“包括 APNs”。",
        "# 若该选项不可选，请按当前版本界面先启用“包括所有网络”。",
        "# 含进程规则的列表内联为兼容快照；更新这些列表后请重新生成。",
        "",
        "[General]",
        "# 兼容仍支持旁路系统选项的版本，避免苹果服务绕过规则。",
        "bypass-system = false",
        "dns-server = system",
        "skip-proxy = 127.0.0.1, localhost, *.local",
        "udp-policy-not-supported-behaviour = REJECT",
        f"update-url = {UPDATE_URL}",
        "",
        "[Rule]",
    ]
    for entry in SOURCE.read_text(encoding="utf-8").splitlines():
        if not entry.startswith("ruleset="):
            continue
        group, source = entry.removeprefix("ruleset=").split(",", 1)
        policy = POLICIES[group]  # Fail on new groups rather than silently guessing.
        lines.extend(["", f"# {group} → {policy}"])
        if source.startswith("[]"):
            rule = source[2:]
            if rule not in {"GEOIP,CN", "FINAL"}:
                raise ValueError(f"Unsupported inline rule: {rule}")
            lines.append(f"{rule},{policy}")
            continue
        url = source.split(",", 1)[0]
        if url.startswith("clash-classic:"):
            if not url.endswith("/AWAvenue-Ads-Rule-Clash-Classical.yaml"):
                raise ValueError(f"Unsupported Clash source: {url}")
            url = AWA_URL
        path = local_path(url)
        if path is None:
            if url not in {AWA_URL, "https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-surge.txt"}:
                raise ValueError(f"Unreviewed external source: {url}")
            lines.append(f"RULE-SET,{url},{policy}")
            continue
        rules = active_rules(path)
        # Review every local type even when keeping a remote RULE-SET reference.
        for rule in rules:
            if rule.split(",", 1)[0] not in SUPPORTED | {"PROCESS-NAME"}:
                raise ValueError(f"Unsupported rule in {path}: {rule}")
        inline = path.name == "UnBan.list" or any(r.startswith("PROCESS-NAME,") for r in rules)
        if not inline:
            lines.append(f"RULE-SET,{url},{policy}")
            continue
        lines.append(f"# 内联快照：{path.relative_to(ROOT)}；源：{url}")
        for rule in rules:
            if rule.startswith("PROCESS-NAME,"):
                lines.append(f"# 已省略 iOS 进程匹配：{rule}")
                continue
            target = "PROXY" if path.name == "UnBan.list" and rule in GAME_EXCEPTIONS else policy
            if target != policy:
                lines.append("# 游戏白名单继续放行，但按用户要求通过代理。")
            lines.append(with_policy(rule, target))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check the committed output without writing")
    args = parser.parse_args()
    content = generate()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            parser.exit(1, "Shadowrocket config is stale; run scripts/generate_shadowrocket.py\n")
        print("Shadowrocket config is up to date")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(content, encoding="utf-8")
        print(f"Generated {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
