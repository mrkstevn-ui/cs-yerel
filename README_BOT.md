# CloudStream Otomatik Alan Adı (Domain) Güncelleme Botu

Bu bot, [eklenti_domainleri.txt](eklenti_domainleri.txt) dosyasındaki adresleri kontrol eder. Yalnızca bu dosyayı okuyan derlenmiş eklentiler için doğrulanmış adres değişikliklerini kaydeder. Bir ana sayfanın açılması, eklentinin arama veya video oynatma işlevlerinin çalıştığını göstermez.

---

## 🚀 Çalışma Şekilleri

### 1. GitHub Actions ile 7/24 Bulutta Çalıştırma (Önerilen)
`.github/workflows/domain-bot.yml` dosyası hazır olarak eklendi.
* **Otomatik:** Her 6 saatte bir (veya belirlediğiniz periyotta) GitHub sunucularında kendiliğinden çalışır.
* **Manuel:** GitHub deponuzdaki **Actions** sekmesinden **Run workflow** diyerek istediğiniz an tetikleyebilirsiniz.
* **Gereksinim:** GitHub depo ayarlarından `Settings -> Actions -> General -> Workflow permissions` kısmında **Read and write permissions** seçeneğinin açık olduğundan emin olun.

---

### 2. Yerel Olarak Bilgisayarda Çalıştırma

```bash
# Sadece tarayıp dosyayı yerel olarak güncellemek için:
python3 domain_bot.py

# İnternete bağlanmadan katalog, paket ve adres kapsamını denetlemek için:
python3 domain_bot.py --check

# Tek eklentiyi dosya değiştirmeden denemek için:
python3 domain_bot.py --dry-run --provider DiziPal

# Güncelleyip doğrudan GitHub'a push etmek için:
python3 domain_bot.py --push

# Arka planda daemon olarak (her 4 saatte bir otomatik) çalıştırmak için:
python3 domain_bot.py --daemon --push --interval 14400
```

---

## 🛠️ Botun Özellikleri ve Algoritmaları

1. **Paket kapsamı:** Bot `.cs3` paketlerini kontrol eder; birden çok sağlayıcı barındıran paketlerin kullandığı adres anahtarlarını da tarar. Adres listesini okumayan paketleri raporlar. Böyle eklentilerde adres düzeltmesi için kaynak kodun değiştirilip paketin yeniden derlenmesi gerekir.
2. **Yönlendirme ve aynalar:** Yalnızca aynı alan adına veya kodda açıkça tanımlanmış aynalara güvenli HTTPS yönlendirmeleri kabul edilir. Rastgele sayı ve uzantı tahmini yapılmaz.
3. **Yanıltıcı sayfa filtresi:** Erişim engeli, bot doğrulaması, park sayfası ve giriş bağlantıları sağlayıcı adresi olarak kaydedilmez.
4. **Katalog denetimi:** `plugins.json` sürümü, boyutu ve SHA-256 değeri gerçek `.cs3` paketleriyle karşılaştırılır. Uyuşmazlıkta tarama başarısız olur.
5. **Git otomasyonu:** Doğrulanmış adres değişikliği varsa yalnızca adres dosyası commit edilir ve push edilir.
