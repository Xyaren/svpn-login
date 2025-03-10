wget "https://secure-gateway.tui.com/public/download/linux_f5epi.x86_64.deb" -O /tmp/f5epi.deb
wget "https://secure-gateway.tui.com/public/download/linux_f5vpn.x86_64.deb" -O /tmp/f5vpn.deb

sudo apt install /tmp/f5epi.deb /tmp/f5vpn.deb moreutils
rm /tmp/f5epi.deb /tmp/f5vpn.deb


