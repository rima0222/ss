# Custom Panel v2.1.2 Verified

Only SSH and IKEv2 are enabled.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

The installer prints success only after strongSwan, accounting, the web service,
and the login health check all pass.

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```
