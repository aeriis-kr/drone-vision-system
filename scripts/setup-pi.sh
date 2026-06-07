#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_DIR="$ROOT/pi5_tx"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
APT_UPGRADE="${APT_UPGRADE:-1}"
CONFIGURE_AP="${CONFIGURE_AP:-1}"
WIFI_COUNTRY="${WIFI_COUNTRY:-KR}"
AP_CONNECTION_NAME="${AP_CONNECTION_NAME:-dvs-ap}"
AP_IFACE="${AP_IFACE:-}"
AP_SSID="${AP_SSID:-}"
AP_PSK="${AP_PSK:-}"
AP_CIDR="${AP_CIDR:-10.42.0.1/24}"
AP_BAND="${AP_BAND:-bg}"
AP_CHANNEL="${AP_CHANNEL:-6}"
AP_CONFIRM="${AP_CONFIRM:-}"
AP_INFO_FILE="${AP_INFO_FILE:-$PI_DIR/.ap-info}"

need_sudo() {
	if [[ "${EUID}" -eq 0 ]]; then
		echo ""
	else
		echo "sudo"
	fi
}

ensure_user_local_bin_on_path() {
	local local_bin="$HOME/.local/bin"
	case ":$PATH:" in
	*":$local_bin:"*) ;;
	*) export PATH="$local_bin:$PATH" ;;
	esac

	local profile="$HOME/.profile"
	case "${SHELL:-}" in
	*/bash) profile="$HOME/.bashrc" ;;
	*/zsh) profile="$HOME/.zshrc" ;;
	esac

	local marker="# >>> drone-vision-system uv PATH >>>"
	if [[ -f "$profile" ]] && grep -Fq "$marker" "$profile"; then
		return
	fi

	mkdir -p "$(dirname "$profile")"
	cat >>"$profile" <<'EOF'

# >>> drone-vision-system uv PATH >>>
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
# <<< drone-vision-system uv PATH <<<
EOF
	echo "[setup-pi] added ~/.local/bin to PATH in $profile"
}

install_uv() {
	ensure_user_local_bin_on_path
	if command -v uv >/dev/null 2>&1; then
		return
	fi
	echo "[setup-pi] installing uv"
	curl -LsSf https://astral.sh/uv/install.sh | sh
	ensure_user_local_bin_on_path
}

install_apt_packages() {
	if ! command -v apt-get >/dev/null 2>&1; then
		echo "[setup-pi] apt-get not found; this setup script is intended for Raspberry Pi OS" >&2
		exit 1
	fi

	local sudo_cmd
	sudo_cmd="$(need_sudo)"

	echo "[setup-pi] updating apt package index"
	${sudo_cmd} apt-get update

	if [[ "$APT_UPGRADE" == "1" ]]; then
		echo "[setup-pi] upgrading installed packages (set APT_UPGRADE=0 to skip)"
		${sudo_cmd} DEBIAN_FRONTEND=noninteractive apt-get full-upgrade -y
	fi

	local camera_pkg="${CAMERA_PKG:-rpicam-apps}"
	if ! apt-cache show "$camera_pkg" >/dev/null 2>&1; then
		camera_pkg="libcamera-apps"
	fi

	echo "[setup-pi] installing system dependencies"
	${sudo_cmd} DEBIAN_FRONTEND=noninteractive apt-get install -y \
		ca-certificates \
		curl \
		ffmpeg \
		git \
		iproute2 \
		network-manager \
		python3 \
		python3-dev \
		python3-pip \
		python3-venv \
		rfkill \
		wireless-regdb \
		"$camera_pkg"
}

sync_python_package() {
	echo "[setup-pi] creating uv venv with system site packages"
	cd "$PI_DIR"
	uv venv --system-site-packages --python "$PYTHON_BIN"
	uv sync
}

random_ssid() {
	"$PYTHON_BIN" - <<'PY'
import secrets
alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
print("DVS-" + "".join(secrets.choice(alphabet) for _ in range(6)))
PY
}

random_psk() {
	"$PYTHON_BIN" - <<'PY'
import secrets
alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
print("dvs-" + "".join(secrets.choice(alphabet) for _ in range(12)))
PY
}

detect_wifi_iface() {
	if [[ -n "$AP_IFACE" ]]; then
		printf '%s\n' "$AP_IFACE"
		return
	fi

	if command -v nmcli >/dev/null 2>&1; then
		nmcli -t -f DEVICE,TYPE device status | awk -F: '$2 == "wifi" { print $1; exit }'
		return
	fi

	if command -v iw >/dev/null 2>&1; then
		iw dev | awk '$1 == "Interface" { print $2; exit }'
		return
	fi

	printf '%s\n' "wlan0"
}

configure_wifi_country() {
	local sudo_cmd
	sudo_cmd="$(need_sudo)"

	if command -v raspi-config >/dev/null 2>&1; then
		${sudo_cmd} raspi-config nonint do_wifi_country "$WIFI_COUNTRY" || true
	fi
	if command -v iw >/dev/null 2>&1; then
		${sudo_cmd} iw reg set "$WIFI_COUNTRY" || true
	fi
}

confirm_ap_switch() {
	local iface="$1"
	local ssid="$2"
	local ap_ip="$3"
	local confirmation="${AP_CONFIRM,,}"

	case "$confirmation" in
	1 | true | yes | y | enable_ap)
		echo "[setup-pi] AP mode gate bypassed (AP_CONFIRM=$AP_CONFIRM)"
		return 0
		;;
	esac

	cat <<EOF

[setup-pi] AP mode gate
Enabling AP mode on interface '$iface' can immediately disconnect this Pi
from its current Wi-Fi network/SSH session.

Pending AP settings:
  SSID:  $ssid
  Pi IP: $ap_ip

Type ENABLE_AP to continue, or press Enter to skip AP setup safely.
For unattended installs, rerun with AP_CONFIRM=1 only when the disconnect is expected.
EOF

	if [[ ! -t 0 ]]; then
		echo "[setup-pi] refusing to enable AP mode without an interactive terminal. Set AP_CONFIRM=1 to proceed intentionally." >&2
		exit 1
	fi

	local answer
	if ! read -r -p "[setup-pi] Switch Wi-Fi into AP mode now? " answer; then
		echo "[setup-pi] AP setup skipped before changing Wi-Fi mode"
		return 1
	fi
	if [[ "$answer" == "ENABLE_AP" ]]; then
		return 0
	fi

	echo "[setup-pi] AP setup skipped before changing Wi-Fi mode"
	return 1
}

configure_ap() {
	if [[ "$CONFIGURE_AP" != "1" ]]; then
		echo "[setup-pi] AP setup skipped (CONFIGURE_AP=0)"
		return
	fi
	if ! command -v nmcli >/dev/null 2>&1; then
		echo "[setup-pi] nmcli not found after installing NetworkManager" >&2
		exit 1
	fi

	local sudo_cmd iface ssid psk ap_ip
	sudo_cmd="$(need_sudo)"
	iface="$(detect_wifi_iface)"
	ssid="${AP_SSID:-$(random_ssid)}"
	psk="${AP_PSK:-$(random_psk)}"
	ap_ip="${AP_CIDR%/*}"

	if [[ -z "$iface" ]]; then
		echo "[setup-pi] Wi-Fi interface not found. Set AP_IFACE=wlan0 and retry." >&2
		exit 1
	fi
	if ((${#psk} < 8 || ${#psk} > 63)); then
		echo "[setup-pi] AP_PSK must be 8-63 characters for WPA2." >&2
		exit 1
	fi

	echo "[setup-pi] configuring Raspberry Pi AP on interface $iface"
	if ! confirm_ap_switch "$iface" "$ssid" "$ap_ip"; then
		return
	fi

	configure_wifi_country
	if command -v rfkill >/dev/null 2>&1; then
		${sudo_cmd} rfkill unblock wifi || true
	fi
	if command -v systemctl >/dev/null 2>&1; then
		${sudo_cmd} systemctl enable --now NetworkManager
	fi

	${sudo_cmd} nmcli radio wifi on
	if ${sudo_cmd} nmcli -t -f NAME connection show | grep -Fxq "$AP_CONNECTION_NAME"; then
		${sudo_cmd} nmcli connection down "$AP_CONNECTION_NAME" >/dev/null 2>&1 || true
		${sudo_cmd} nmcli connection delete "$AP_CONNECTION_NAME"
	fi

	${sudo_cmd} nmcli connection add \
		type wifi \
		ifname "$iface" \
		con-name "$AP_CONNECTION_NAME" \
		autoconnect yes \
		ssid "$ssid"

	${sudo_cmd} nmcli connection modify "$AP_CONNECTION_NAME" \
		802-11-wireless.mode ap \
		802-11-wireless.band "$AP_BAND" \
		802-11-wireless.channel "$AP_CHANNEL" \
		ipv4.method shared \
		ipv4.addresses "$AP_CIDR" \
		ipv6.method ignore \
		wifi-sec.key-mgmt wpa-psk \
		wifi-sec.psk "$psk"

	${sudo_cmd} nmcli connection up "$AP_CONNECTION_NAME"

	umask 077
	cat >"$AP_INFO_FILE" <<EOF
AP_CONNECTION_NAME=$AP_CONNECTION_NAME
AP_IFACE=$iface
AP_SSID=$ssid
AP_PSK=$psk
AP_CIDR=$AP_CIDR
AP_IP=$ap_ip
WIFI_COUNTRY=$WIFI_COUNTRY
EOF

	print_ap_summary "$ssid" "$psk" "$ap_ip" "$iface"
}

print_ap_summary() {
	local ssid="$1"
	local psk="$2"
	local ap_ip="$3"
	local iface="$4"

	cat <<EOF

[setup-pi] AP setup complete

Connect the receiver laptop/tablet to this Wi-Fi AP:
  SSID:     $ssid
  WPA key:  $psk
  Pi IP:    $ap_ip
  Wi-Fi IF: $iface

Saved locally on the Pi:
  $AP_INFO_FILE

Classroom flow:
  1. Receiver user connects to SSID '$ssid'.
  2. Receiver user runs: make run-rx
  3. Receiver terminal prints the exact STREAM_HOST=<rx-ip> make run-pi command.
  4. Run that command on this Raspberry Pi to start video streaming.

EOF
}

main() {
	install_apt_packages
	install_uv
	sync_python_package
	configure_ap

	echo "[setup-pi] done"
}

main "$@"
