# Custom Panel v16 Final

## One line install

curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash

## Show admin

sudo bash /etc/custom-panel/show-credentials.sh

## Reset admin password

sudo bash /etc/custom-panel/reset-admin-password.sh NEW_PASSWORD

## Services

systemctl status custom-panel
systemctl status custom-panel-agent

## Clean uninstall

sudo bash uninstall-clean.sh

Features:
- Clean installation
- Previous panel state cleanup
- New admin credentials
- Separate panel and agent services
- Database foundation
- Session and traffic modules
