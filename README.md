# Custom Panel Engineered v1

پنل مدیریت سبک و ماژولار برای **OpenSSH TCP** و **SSH WebSocket** روی Ubuntu 22.04/24.04.

## معماری

```text
Client
 ├─ TCP اختصاصی کاربر (20000–24999)
 └─ WebSocket مشترک (8080) با Path اختصاصی
              │
              ▼
      Async Gateway واحد
              │
              ▼
OpenSSH داخلی با پورت اختصاصی هر کاربر (localhost)
```

هر پورت داخلی فقط نام کاربری مربوط به همان حساب را می‌پذیرد. بنابراین یک کاربر نمی‌تواند با پورت شخص دیگری وارد شود و مصرف به حساب اشتباه ثبت شود.

### Online دقیق

Online اصلی از `PAM open_session / close_session` بعد از احراز هویت موفق ثبت می‌شود. Agent همچنین پردازش Session را هر دو ثانیه بررسی می‌کند تا بعد از Restart یا از دست رفتن Event وضعیت اصلاح شود.

### مصرف دقیق

Gateway هر دو جهت را اندازه می‌گیرد، اما **فقط بایت‌های Backend → Client (دانلود/Receive کاربر)** از سهمیه کم می‌شود. Upload جداگانه برای عیب‌یابی نگه‌داری می‌شود ولی مصرف حجمی نیست.

Metricها هر یک ثانیه در یک Transaction به SQLite WAL نوشته می‌شوند. تا زمانی که Manager تأیید نکند، Gateway شمارنده‌های محلی را صفر نمی‌کند؛ بنابراین در قطع موقت Manager، بایت‌ها از بین نمی‌روند.

## امکانات

- OpenSSH مستقیم و SSH WebSocket
- ساخت، ویرایش و حذف کاربر
- Pause/Resume با توقف زمان در حالت Pause
- تغییر رمز، حجم و زمان
- نمایش Online احراز‌شده
- نمایش Connectionهای TCP/WS
- محاسبه فقط دانلود کاربر
- قطع خودکار در پایان حجم یا زمان
- ریست مصرف
- دانلود اطلاعات اتصال
- Backup و Restore
- تغییر Username و Password مدیر از داخل پنل
- نصب Clean و حذف کاربران پنل قبلی
- Admin جدید در هر نصب تازه
- یک Gateway برای همه کاربران؛ بدون Process جدا برای هر کاربر
- SQLite WAL و Gunicorn تک‌Worker برای VPS ضعیف

## نصب یک‌خطی

محتویات ZIP را مستقیماً در ریشه Repository زیر قرار بده:

```text
https://github.com/rima0222/ss
```

سپس:

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash
```

برای Repository دیگر:

```bash
curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/install.sh |
sudo CUSTOM_PANEL_REPO_URL=https://github.com/USER/REPO.git bash
```

## اطلاعات ورود

در پایان نصب نمایش داده می‌شود. بعداً:

```bash
sudo bash /opt/custom-panel/show-credentials.sh
```

یا:

```bash
sudo cat /etc/custom-panel/admin-credentials.txt
```

## تغییر رمز مدیر از SSH

رمز تصادفی:

```bash
sudo bash /opt/custom-panel/reset-admin-password.sh
```

رمز و Username دلخواه:

```bash
sudo bash /opt/custom-panel/reset-admin-password.sh 'NEW_STRONG_PASSWORD' 'newadmin'
```

از داخل پنل نیز قابل تغییر است.

## وضعیت و تشخیص خطا

```bash
sudo bash /opt/custom-panel/diagnose.sh
```

یا:

```bash
sudo systemctl status custom-panel-sshd --no-pager -l
sudo systemctl status custom-panel-helper --no-pager -l
sudo systemctl status custom-panel-manager --no-pager -l
sudo systemctl status custom-panel-gateway --no-pager -l
sudo systemctl status custom-panel-web --no-pager -l
```

## حذف کامل

```bash
sudo bash /opt/custom-panel/uninstall.sh
```

Installer و Uninstaller فقط کاربران دارای Group/Marker اختصاصی پنل را حذف می‌کنند و حساب مدیریت VPS را دست‌نخورده نگه می‌دارند.

## پورت‌ها

- پنل: `5000/tcp`
- SSH WebSocket: `8080/tcp`
- OpenSSH کاربران: `20000–24999/tcp`
- Backend داخلی: `30000–34999` فقط روی localhost

## نکتهٔ Ping

Gateway فشرده‌سازی WebSocket را غیرفعال می‌کند، `TCP_NODELAY` فعال است و Backend روی localhost قرار دارد. این طراحی سربار نرم‌افزاری را پایین نگه می‌دارد؛ اما Ping اصلی همچنان به فاصلهٔ سرور، Route و ISP وابسته است.

## تست انجام‌شده روی Release

- بررسی Syntax تمام فایل‌های Python
- بررسی `bash -n` برای Scriptها
- بررسی ساختار Package و فایل‌های ضروری
- تست Schema SQLite و عملیات Admin
- تست Unit برای شمارش دانلود/آپلود و ACK شمارنده‌ها

تست اتصال واقعی OpenSSH، WebSocket، PAM و فشار هم‌زمان باید بعد از نصب روی VPS انجام شود، چون به systemd، PAM، sshd و شبکهٔ واقعی نیاز دارد.
