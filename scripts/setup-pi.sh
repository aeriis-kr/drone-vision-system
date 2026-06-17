#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_DIR="$ROOT/pi5_tx"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
APT_UPGRADE="${APT_UPGRADE:-1}"
INSTALL_PI_INFERENCE="${INSTALL_PI_INFERENCE:-0}"

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
		python3 \
		python3-dev \
		python3-pip \
		python3-venv \
		"$camera_pkg"
}

truthy() {
	case "${1,,}" in
	1 | true | yes | y | on) return 0 ;;
	*) return 1 ;;
	esac
}

sync_python_package() {
	echo "[setup-pi] creating uv venv with system site packages"
	cd "$PI_DIR"
	uv venv --system-site-packages --python "$PYTHON_BIN"
	if truthy "$INSTALL_PI_INFERENCE"; then
		echo "[setup-pi] installing pi5_tx[inference] optional dependencies"
		uv sync --extra inference
	else
		echo "[setup-pi] installing control-only Pi dependencies (set INSTALL_PI_INFERENCE=1 for Pi-local YOLO)"
		uv sync
	fi
}


main() {
	install_apt_packages
	install_uv
	sync_python_package

	echo "[setup-pi] done"
}

main "$@"
