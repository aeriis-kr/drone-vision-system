#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RX_DIR="$ROOT/vision_rx"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_SYSTEM_DEPS="${INSTALL_SYSTEM_DEPS:-1}"

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
	echo "[setup-rx] added ~/.local/bin to PATH in $profile"
}

install_uv() {
	ensure_user_local_bin_on_path
	if command -v uv >/dev/null 2>&1; then
		return
	fi
	echo "[setup-rx] installing uv"
	curl -LsSf https://astral.sh/uv/install.sh | sh
	ensure_user_local_bin_on_path
}

install_system_deps() {
	if [[ "$INSTALL_SYSTEM_DEPS" != "1" ]]; then
		return
	fi

	case "$(uname -s)" in
	Darwin)
		if ! command -v ffmpeg >/dev/null 2>&1; then
			if command -v brew >/dev/null 2>&1; then
				echo "[setup-rx] installing ffmpeg with Homebrew"
				brew install ffmpeg
			else
				echo "[setup-rx] Homebrew not found; install FFmpeg manually" >&2
			fi
		fi
		;;
	Linux)
		if command -v apt-get >/dev/null 2>&1; then
			local sudo_cmd
			sudo_cmd="$(need_sudo)"
			echo "[setup-rx] installing Linux system dependencies"
			${sudo_cmd} apt-get update
			${sudo_cmd} DEBIAN_FRONTEND=noninteractive apt-get install -y \
				ca-certificates \
				curl \
				ffmpeg \
				git \
				libgl1 \
				libglib2.0-0 \
				python3 \
				python3-dev \
				python3-pip \
				python3-venv
		elif command -v dnf >/dev/null 2>&1; then
			local sudo_cmd
			sudo_cmd="$(need_sudo)"
			${sudo_cmd} dnf install -y ffmpeg python3 python3-devel python3-pip git curl
		else
			echo "[setup-rx] install FFmpeg and Python build tools manually for this Linux distro" >&2
		fi
		;;
	MINGW* | MSYS* | CYGWIN*)
		echo "[setup-rx] Windows detected. Install FFmpeg and Python manually, then run uv sync in vision_rx." >&2
		;;
	esac
}

main() {
	install_system_deps
	install_uv

	echo "[setup-rx] creating uv venv with system site packages"
	cd "$RX_DIR"
	uv venv --system-site-packages --python "$PYTHON_BIN"
	uv sync

	echo "[setup-rx] done"
	echo "[setup-rx] next: make run-rx"
}

main "$@"
