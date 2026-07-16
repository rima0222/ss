# Custom Panel v6 — Optimized SSH

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

---

## Show current admin username/password

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

or

```bash
sudo cat /etc/custom-panel/admin-credentials.txt
```

---

## Generate a new random admin password

```bash
sudo bash /etc/custom-panel/reset-admin-password.sh
```

---

## Set a custom admin password

```bash
sudo bash /etc/custom-panel/reset-admin-password.sh 'NEW_STRONG_PASSWORD'
```

---

## Restart services

```bash
sudo systemctl restart custom-panel
sudo systemctl restart custom-panel-proxy
sudo systemctl restart custom-panel-accounting
```

---

## Check services

```bash
sudo systemctl status custom-panel
sudo systemctl status custom-panel-proxy
sudo systemctl status custom-panel-accounting
sudo systemctl status ssh
```

---

## Backup

From the web panel:
- Backup
- Restore

All users, ports, passwords, traffic, remaining days and settings are preserved.

---

Supported protocol:

- OpenSSH only
