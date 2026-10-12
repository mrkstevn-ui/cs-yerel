#!/usr/bin/env python3
"""
CloudStream Domain Auto-Updater & GitHub Push Bot
Tüm eklenti alan adlarını periyodik olarak tarar, yönlendirmeleri ve alternatif
aynaları test eder, eklenti_domainleri.txt dosyasını günceller ve değişiklikleri GitHub'a push eder.
"""

import os
import sys
import time
import argparse
import logging
import urllib.request
import urllib.error
import urllib.parse
import ssl
import tempfile
import json
import zipfile
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DomainBot")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FILE = os.path.join(REPO_DIR, "eklenti_domainleri.txt")
PLUGIN_FILE = os.path.join(REPO_DIR, "plugins.json")
BUILDS_DIR = os.path.join(REPO_DIR, "builds")
# Bu paketler tek bir ana sağlayıcı yerine listedeki alt sağlayıcıları okur.
COMPOSITE_PLUGIN_KEYS = {
    "KickTR": ("Kick",),
    "Turkdizileri": ("Atv", "DMax", "KanalD", "NowTv", "ShowTv", "StarTv",
                    "Teve2", "TLC", "Trt1", "Tv8"),
    "KraptorPlus": ("Animecix", "HDFilmCehennemi", "WebDramaTurkey",
                     "FullHDFilmizlesene", "DiziPalOrijinal", "FilmEkseni",
                     "HDFilmDelisi", "SetFilmIzle"),
}

# HTTPS sertifikası doğrulanmadan yeni adres kabul edilmez.
SSL_CTX = ssl.create_default_context()

# Güvenilirliği elle doğrulanmış alternatif sağlayıcı adresleri.
SPECIAL_RULES = {
    "HDFilmcehennemi": {
        "type": "mirrors",
        "mirrors": [
            "https://www.hdfilmcehennemi.nl",
            "https://www.hdfilmcehennemi.life",
            "https://www.hdfilmcehennemi.net",
            "https://www.hdfilmcehennemi.to"
        ]
    },
    "Ddizi": {
        "type": "mirrors",
        "mirrors": [
            "https://www.ddizi.tel",
            "https://www.ddizi.im",
            "https://www.ddizi.me"
        ]
    },
    "DiziYo": {
        "type": "mirrors",
        "mirrors": [
            "https://www.diziyo.me",
            "https://www.diziyo.to",
            "https://www.diziyo.so"
        ]
    },
    "Filmzal": {
        "type": "mirrors",
        "mirrors": [
            "https://filmzal.net",
            "https://filmzal.org",
            "https://filmzal.me"
        ]
    },
    "HDFilmizle": {
        "type": "mirrors",
        "mirrors": [
            "https://hdfilmizle.to",
            "https://www.hdfilmizle.live",
            "https://hdfilmizle.life"
        ]
    },
    "SetFilmIzle": {
        "type": "mirrors",
        "mirrors": [
            "https://setfilmizle.ltd",
            "https://www.setfilmizle.pro",
            "https://setfilmizle.tv"
        ]
    }
}


def load_domains(file_path):
    if not os.path.exists(file_path):
        logger.error(f"Dosya bulunamadı: {file_path}")
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    entries = {}
    for item in content.split("|"):
        item = item.strip()
        if ":" in item:
            k, v = item.split(":", 1)
            entries[k.strip()] = v.strip()
    return entries


def plugin_coverage(domains):
    """Find packages referencing the domain list with a matching catalog key."""
    with open(PLUGIN_FILE, encoding="utf-8") as f:
        plugins = json.load(f)
    keys = {name.casefold(): name for name in domains}
    active = set()
    static = []
    unmapped = []
    for plugin in plugins:
        name = plugin["internalName"]
        build = os.path.join(BUILDS_DIR, name + ".cs3")
        with zipfile.ZipFile(build) as archive:
            dex = archive.read("classes.dex")
            manifest = json.loads(archive.read("manifest.json"))
        with open(build, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        if (plugin["version"] != manifest["version"]
                or plugin["name"] != manifest["name"]
                or plugin["fileSize"] != os.path.getsize(build)
                or plugin["fileHash"] != "sha256-" + digest):
            raise ValueError("Katalog ile eklenti paketi uyuşmuyor: " + name)
        if b"eklenti_domainleri.txt" not in dex:
            static.append(name)
        elif name.casefold() in keys:
            active.add(keys[name.casefold()])
        elif name in COMPOSITE_PLUGIN_KEYS:
            missing = set(COMPOSITE_PLUGIN_KEYS[name]) - domains.keys()
            if missing:
                raise ValueError(name + " için eksik alan adı anahtarı: " + ", ".join(sorted(missing)))
            active.update(COMPOSITE_PLUGIN_KEYS[name])
        else:
            unmapped.append(name)
    if static:
        logger.warning("Adres listesini kullanmayan %d paket: %s", len(static), ", ".join(static))
    if unmapped:
        logger.warning("Listede eşleşen anahtarı olmayan %d paket: %s", len(unmapped), ", ".join(unmapped))
    return active


def save_domains(file_path, entries):
    sorted_items = sorted(entries.items(), key=lambda x: x[0].lower())
    output_str = " | ".join(f"{k}: {v}" for k, v in sorted_items)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=os.path.dirname(os.path.abspath(file_path)), delete=False) as f:
        temporary = f.name
        f.write(output_str + "\n")
    try:
        os.replace(temporary, file_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    logger.info(f"Kayıt tamamlandı: {file_path} ({len(entries)} eklenti)")


def safe_base_url(url):
    """Giriş, reklam ve oturum URL'leri sağlayıcı adresi değildir."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        return None
    host = parsed.hostname.lower()
    if host.endswith(".cloudflareaccess.com"):
        return None
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), "", "", ""))


def trusted_redirect(source, target, allowed_urls=()):
    if not safe_base_url(target):
        return False
    original = urllib.parse.urlsplit(source)
    destination = urllib.parse.urlsplit(target)
    if original.scheme == "https" and destination.scheme != "https":
        return False
    # Sadece www farkı veya açıkça tanımlanan aynalar kabul edilir.
    allowed = {urllib.parse.urlsplit(u).netloc.lower().removeprefix("www.")
               for u in (source, *allowed_urls)}
    return destination.netloc.lower().removeprefix("www.") in allowed


class ProviderRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, source, allowed_urls):
        super().__init__()
        self.source = source
        self.allowed_urls = allowed_urls

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted_redirect(self.source, newurl, self.allowed_urls):
            raise urllib.error.URLError("Onaylanmamış yönlendirme hedefi")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe_url(url, timeout=8, allowed_urls=()):
    if not safe_base_url(url):
        return False, url, "Geçersiz sağlayıcı ana adresi"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=SSL_CTX),
        ProviderRedirectHandler(url, allowed_urls))
    try:
        with opener.open(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if not trusted_redirect(url, final_url, allowed_urls):
                return False, url, "Onaylanmamış yönlendirme hedefi"
            html = resp.read(131072).decode("utf-8", errors="ignore").lower()
            markers = (
                "erisime_engellenmis", "idari tedbir", "plesk obsidian",
                "domain for sale", "buy this domain", "hugedomains",
                "sedoparking", "parkingcrew", "just a moment", "cf-chl-",
                "cloudflare access", "alwaysafepro.com", "milli piyango idaresi",
            )
            if any(marker in html for marker in markers):
                return False, url, "Engel, doğrulama veya park sayfası"
            if resp.getcode() != 200 or len(html.strip()) < 100:
                return False, url, "Boş veya başarısız yanıt"
            content_type = resp.headers.get("Content-Type", "").lower()
            if "html" not in content_type:
                return False, url, "HTML sayfası değil; otomatik doğrulanamadı"
            return True, safe_base_url(final_url), "HTTP 200; ana sayfa erişilebilir"
    except urllib.error.HTTPError as exc:
        return False, url, f"HTTP {exc.code}; erişilebilirlik doğrulanamadı"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, url, f"Bağlantı doğrulanamadı: {exc}"


def find_better_domain(name, current_url):
    rule = SPECIAL_RULES.get(name, {})
    mirrors = rule.get("mirrors", [])
    ok, final, reason = probe_url(current_url, allowed_urls=mirrors)
    if ok:
        return final
    logger.warning("[%s] %s", name, reason)
    # HTTP hatası aynı adlı başka bir sitenin doğru kaynak olduğunu göstermez.
    # Sayı/TLD tahmini kaldırıldı; yalnızca açıkça tanımlı aynalar denenir.
    for mirror in mirrors:
        if mirror.rstrip("/") == current_url.rstrip("/"):
            continue
        ok, final, _ = probe_url(mirror, allowed_urls=mirrors)
        if ok:
            return final
    return current_url


def run_scan_and_update(dry_run=False, providers=None):
    domains = load_domains(DOMAIN_FILE)
    if not domains:
        raise ValueError("Domain listesi yüklenemedi")
    active = plugin_coverage(domains)
    selected = {k: v for k, v in domains.items() if k in active and (not providers or k in providers)}
    if providers and set(providers) - domains.keys():
        raise ValueError("Bilinmeyen sağlayıcı: " + ", ".join(set(providers) - domains.keys()))
    if providers and set(providers) - active:
        raise ValueError("Botun adres listesini kullanmayan sağlayıcı: " + ", ".join(sorted(set(providers) - active)))
    invalid = [name for name, url in selected.items() if not safe_base_url(url)]
    if invalid:
        raise ValueError("Geçersiz sağlayıcı ana adresi: " + ", ".join(sorted(invalid)))
    updates = {}
    failures = []
    logger.info("%s sağlayıcı kontrol ediliyor; bu kontrol video oynatmayı doğrulamaz.", len(selected))
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(find_better_domain, n, u): (n, u) for n, u in selected.items()}
        for future in as_completed(futures):
            name, old_url = futures[future]
            try:
                new_url = future.result()
                if new_url and new_url.rstrip("/") != old_url.rstrip("/"):
                    updates[name] = (old_url, new_url)
                    domains[name] = new_url
            except Exception as exc:
                failures.append(name)
                logger.error("Kontrol başarısız (%s): %s", name, exc)
    if failures:
        raise RuntimeError("Tarama tamamlanamadı: " + ", ".join(failures))
    for name, (old, new) in sorted(updates.items()):
        logger.info("%s: %s -> %s", name, old, new)
    if updates and not dry_run:
        save_domains(DOMAIN_FILE, domains)
    if not updates:
        logger.info("Doğrulanmış adres değişikliği yok. Hata veren kaynaklar güncel sayılmaz.")
    return bool(updates), updates


def git_commit_and_push(updates):
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "eklenti_domainleri.txt"],
        cwd=REPO_DIR, capture_output=True, text=True, check=True)
    if result.stdout.strip():
        names = ", ".join(sorted(updates)) or "doğrulanmış adresler"
        # --only başka dosyalardaki staged değişiklikleri commit'e dahil etmez.
        subprocess.run(["git", "add", "--", "eklenti_domainleri.txt"], cwd=REPO_DIR, check=True)
        subprocess.run(["git", "commit", "--only", "-m", "[Domain Bot] " + names,
                        "--", "eklenti_domainleri.txt"], cwd=REPO_DIR, check=True)
    # Önceki turda push başarısızsa yeni adres değişmese de yeniden denenir.
    subprocess.run(["git", "push"], cwd=REPO_DIR, check=True)


def main():
    parser = argparse.ArgumentParser(description="CloudStream Domain Updater Bot")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Dosyaları değiştirmeden kontrol et")
    parser.add_argument("--check", action="store_true", help="Paket ve katalog tutarlılığını çevrimdışı kontrol et")
    parser.add_argument("--provider", action="append", help="Yalnızca bu sağlayıcıyı kontrol et; tekrarlanabilir")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--interval", type=int, default=14400)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval pozitif olmalı")
    if args.dry_run and args.push:
        parser.error("--dry-run ve --push birlikte kullanılamaz")
    if args.check and (args.push or args.dry_run or args.daemon or args.provider):
        parser.error("--check diğer çalışma seçenekleriyle kullanılamaz")
    if args.check:
        try:
            domains = load_domains(DOMAIN_FILE)
            active = plugin_coverage(domains)
            invalid = [name for name in active if not safe_base_url(domains[name])]
            inactive_invalid = [name for name in domains if name not in active and not safe_base_url(domains[name])]
            if inactive_invalid:
                logger.warning("Bot kapsamı dışındaki geçersiz kayıtlar: %s", ", ".join(sorted(inactive_invalid)))
            if invalid:
                raise ValueError("Geçersiz sağlayıcı ana adresi: " + ", ".join(sorted(invalid)))
            logger.info("Katalog doğrulandı; bot %d adres anahtarını kontrol edebilir.", len(active))
            return 0
        except Exception:
            logger.exception("Eklenti doğrulaması başarısız")
            return 1
    while True:
        try:
            _, updates = run_scan_and_update(args.dry_run, args.provider)
            if args.push:
                git_commit_and_push(updates)
        except Exception:
            logger.exception("Bot çalışması başarısız")
            if not args.daemon:
                return 1
        if not args.daemon:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
