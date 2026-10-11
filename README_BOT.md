# CloudStream Otomatik Alan Adı (Domain) Güncelleme Botu

Bu bot, [eklenti_domainleri.txt](file:///Users/karakas/Downloads/cs-yerel-main/eklenti_domainleri.txt) dosyasındaki tüm film, dizi ve anime sitelerinin alan adlarını otomatik olarak kontrol eder. Adres değiştiğinde (yönlendirme, BTK engeli, sayı rotasyonu vb.) yeni adresi tespit edip dosyayı günceller ve GitHub'a push eder.

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

# Güncelleyip doğrudan GitHub'a push etmek için:
python3 domain_bot.py --push

# Arka planda daemon olarak (her 4 saatte bir otomatik) çalıştırmak için:
python3 domain_bot.py --daemon --push --interval 14400
```

---

## 🛠️ Botun Özellikleri ve Algoritmaları

1. **HTTP 301/302 Yönlendirme Takibi:** Bir site yeni bir alan adına yönlendiğinde (örn. `tranimeizle.io` -> `tranimeizle.live`) otomatik olarak yeni domain kaydedilir.
2. **Sayısal Rotasyon Avcısı:** Engellendikçe sonundaki sayıyı artıran siteleri (örn. `dizipal1589.com`, `dizi77.life`) otomatik olarak taranıp en güncel çalışan sayıya geçirilir.
3. **TLD / Uzantı Rotasyonu:** Engellenen sitelerin `.net`, `.to`, `.me`, `.org`, `.tel`, `.live` gibi popüler alternatif aynaları taranır.
4. **BTK ve Sahte Ekran Filtresi:** Mahkeme/BTK engelleme ekranları (`.erisime_engellenmis`), boş Plesk sayfaları ve satılık domain park sayfaları tespit edilip filtrelenir.
5. **Git Otomasyonu:** Yalnızca gerçek bir domain değişikliği olduğunda anlamlı bir commit mesajıyla GitHub'a push yapar.
