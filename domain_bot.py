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
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DomainBot")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FILE = os.path.join(REPO_DIR, "eklenti_domainleri.txt")

# SSL bağlamı (doğrulama hatalarına takılmamak için)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Özel arama kuralları olan servisler (sayı artıranlar veya TLD rotasyonu yapanlar)
SPECIAL_RULES = {
    "DiziPal": {
        "pattern": r"https://dizipal(\d+)\.com",
        "template": "https://dizipal{num}.com",
        "type": "numeric",
        "step": 1,
        "max_probe": 20
    },
    "DiziPalOrijinal": {
        "pattern": r"https://dizipal(\d+)\.com",
        "template": "https://dizipal{num}.com",
        "type": "numeric",
        "step": 1,
        "max_probe": 20
    },
    "DiziLife": {
        "pattern": r"https://dizi(\d+)\.life",
        "template": "https://dizi{num}.life",
        "type": "numeric",
        "step": 1,
        "max_probe": 15
    },
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


def save_domains(file_path, entries):
    sorted_items = sorted(entries.items(), key=lambda x: x[0].lower())
    output_str = " | ".join(f"{k}: {v}" for k, v in sorted_items)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(output_str)
    logger.info(f"Kayıt tamamlandı: {file_path} ({len(entries)} eklenti)")


def probe_url(url, timeout=5):
    """
    URL'nin aktifliğini ve yönlendirme hedefini test eder.
    Döner: (is_valid, final_url, status_description)
    """
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False, url, "Geçersiz URL"
    
    # 1. DNS Testi
    try:
        socket.getaddrinfo(hostname, 443 if parsed.scheme == "https" else 80, socket.AF_INET)
    except Exception as e:
        return False, url, f"DNS Başarısız: {e}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            code = resp.getcode()
            final_url = resp.geturl()
            html = resp.read(32768).decode("utf-8", errors="ignore")

            # BTK / Mahkeme engeli kontrolü
            if "erisime_engellenmis" in html or "milli piyango idaresi" in html.lower() or "idari tedbir" in html.lower():
                return False, url, "BTK / Mahkeme Kararıyla Engelli"
            
            # Plesk boş sunucu ekranı
            if "Plesk Obsidian" in html:
                return False, url, "Plesk Boş Sunucu Ekranı"

            # Domain satış / park sayfası
            if "domain for sale" in html.lower() or "buy this domain" in html.lower() or "hugedomains" in html.lower():
                return False, url, "Park Edilmiş / Satılık Domain"

            return True, final_url, f"HTTP {code} OK"

    except urllib.error.HTTPError as e:
        if e.code == 403:
            # Cloudflare bot koruması olabilir ancak site yayında olabilir
            return False, url, f"HTTP 403 Forbidden"
        return False, url, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, url, f"Bağlantı Hatası: {e.reason}"
    except Exception as e:
        return False, url, f"Hata: {e}"


def find_better_domain(name, current_url):
    """
    Belirli bir sağlayıcı için mevcut URL'yi kontrol eder,
    eğer bozuksa kurallara göre çalışan alternatif veya yönlenmiş adresi bulur.
    """
    is_valid, final_url, reason = probe_url(current_url)

    # 1. Mevcut URL yönlenmiş ve çalışan bir yere gidiyorsa
    if is_valid:
        netloc_cur = urllib.parse.urlparse(current_url).netloc
        netloc_final = urllib.parse.urlparse(final_url).netloc
        if netloc_cur != netloc_final:
            logger.info(f"[{name}] Yönlendirme algılandı: {current_url} -> {final_url}")
            return final_url.rstrip("/")
        return current_url

    logger.warning(f"[{name}] {current_url} yanıt vermiyor ({reason}). Alternatif aranıyor...")

    # 2. Özel Kural Kontrolü
    rule = SPECIAL_RULES.get(name)
    if rule:
        # Sayısal rotasyon (örn. Dizipal1589 -> Dizipal1590...)
        if rule.get("type") == "numeric":
            match = re.search(rule["pattern"], current_url)
            if match:
                curr_num = int(match.group(1))
                template = rule["template"]
                for delta in range(1, rule.get("max_probe", 15)):
                    candidate_num = curr_num + delta
                    candidate_url = template.format(num=candidate_num)
                    ok, final, _ = probe_url(candidate_url)
                    if ok:
                        logger.info(f"[{name}] Yeni sayısal ayna bulundu: {candidate_url}")
                        return candidate_url.rstrip("/")

        # Liste halindeki alternatif aynalar
        elif rule.get("type") == "mirrors":
            for mirror in rule.get("mirrors", []):
                if mirror.rstrip("/") == current_url.rstrip("/"):
                    continue
                ok, final, _ = probe_url(mirror)
                if ok:
                    logger.info(f"[{name}] Çalışan ayna bulundu: {mirror}")
                    return mirror.rstrip("/")

    # 3. Genel TLD Rotasyonu Denemesi
    parsed = urllib.parse.urlparse(current_url)
    domain_parts = parsed.netloc.split(".")
    if len(domain_parts) >= 2:
        base_name = domain_parts[-2] if not domain_parts[-2] in ("com", "org", "net") else domain_parts[-3]
        for tld in [".to", ".me", ".net", ".org", ".tel", ".co", ".live", ".cc", ".life"]:
            alt_url = f"{parsed.scheme}://{base_name}{tld}"
            if alt_url == current_url:
                continue
            ok, final, _ = probe_url(alt_url)
            if ok:
                logger.info(f"[{name}] TLD rotasyonuyla bulundu: {alt_url}")
                return alt_url.rstrip("/")

    return current_url


def run_scan_and_update():
    domains = load_domains(DOMAIN_FILE)
    if not domains:
        logger.error("Domain listesi yüklenemedi!")
        return False, []

    logger.info(f"Toplam {len(domains)} eklenti taranıyor...")
    updates = {}

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(find_better_domain, name, url): (name, url) for name, url in domains.items()}
        for future in futures:
            name, old_url = futures[future]
            try:
                new_url = future.result()
                if new_url and new_url.rstrip("/") != old_url.rstrip("/"):
                    updates[name] = (old_url, new_url)
                    domains[name] = new_url
            except Exception as e:
                logger.error(f"Hata ({name}): {e}")

    if updates:
        logger.info(f"Toplam {len(updates)} eklenti adresi güncellendi:")
        for name, (old, new) in updates.items():
            logger.info(f"  • {name}: {old} -> {new}")
        save_domains(DOMAIN_FILE, domains)
        return True, updates
    else:
        logger.info("Tüm domainler güncel, değişiklik yok.")
        return False, []


def git_commit_and_push(updates):
    try:
        # Git durumunu kontrol et
        status_res = subprocess.run(["git", "status", "--porcelain", "eklenti_domainleri.txt"],
                                   cwd=REPO_DIR, capture_output=True, text=True)
        if not status_res.stdout.strip():
            logger.info("Git üzerinde commit edilecek dosya değişikliği yok.")
            return

        # Değişiklik mesajı oluştur
        changed_names = ", ".join(list(updates.keys())[:5])
        if len(updates) > 5:
            changed_names += f" (+{len(updates)-5} diğer)"
        commit_msg = f"[Domain Bot] Güncellenen alan adları: {changed_names}"

        subprocess.run(["git", "add", "eklenti_domainleri.txt"], cwd=REPO_DIR, check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_DIR, check=True)
        logger.info(f"Git commit oluşturuldu: {commit_msg}")

        # Git push
        push_res = subprocess.run(["git", "push"], cwd=REPO_DIR, capture_output=True, text=True)
        if push_res.returncode == 0:
            logger.info("Değişiklikler GitHub'a başarıyla push edildi!")
        else:
            logger.warning(f"Git push uyarısı/hatası: {push_res.stderr.strip()}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Git işlemi başarısız: {e}")
    except Exception as e:
        logger.error(f"Git hatası: {e}")


def main():
    parser = argparse.ArgumentParser(description="CloudStream Domain Updater Bot")
    parser.add_argument("--push", action="store_true", help="Değişiklikleri otomatik git commit edip push et")
    parser.add_argument("--daemon", action="store_true", help="Arka planda döngü olarak sürekli çalıştır")
    parser.add_argument("--interval", type=int, default=14400, help="Daemon modu kontrol aralığı (saniye, varsayılan: 4 saat)")
    args = parser.parse_args()

    if args.daemon:
        logger.info(f"Daemon modu başlatıldı. Kontrol aralığı: {args.interval} saniye ({args.interval / 3600:.1f} saat)")
        while True:
            has_changes, updates = run_scan_and_update()
            if has_changes and args.push:
                git_commit_and_push(updates)
            time.sleep(args.interval)
    else:
        has_changes, updates = run_scan_and_update()
        if has_changes and args.push:
            git_commit_and_push(updates)


if __name__ == "__main__":
    main()
