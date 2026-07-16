# Custom Panel Production v1

Install:
curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/install.sh | sudo bash

After install:
sudo bash /etc/custom-panel/show-credentials.sh

Reset admin:
sudo bash /etc/custom-panel/reset-admin-password.sh

Status:
systemctl status custom-panel
systemctl status custom-panel-agent

This release contains separated modules:
- installer
- panel
- agent
- database
- services
