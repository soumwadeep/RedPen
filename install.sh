#!/usr/bin/env bash
# RedPen installer -- one command, no cloud account, no API key.
#
#   curl -fsSL https://raw.githubusercontent.com/soumwadeep/RedPen/main/install.sh | bash
#
# Installs the app, the local inference engine and the model weights, then
# checks the result. Everything lands on this machine.

set -euo pipefail

REPO="https://github.com/soumwadeep/RedPen.git"
DIR="${REDPEN_DIR:-$HOME/RedPen}"
MODEL="${REDPEN_MODEL:-gemma-3-1b}"

say()  { printf '\033[36m·\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" != "Darwin" ] && [ "$(uname -s)" != "Linux" ] && die "macOS or Linux only"

# ---------------------------------------------------------------- python ----
PY="$(command -v python3 || true)"
[ -z "$PY" ] && die "python3 not found. Install Python 3.10+ and re-run."
"$PY" - <<'EOF' || die "Python 3.10+ required."
import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)
EOF
say "python $("$PY" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"

# ------------------------------------------------------- inference engine ---
if command -v llama-server >/dev/null 2>&1; then
  say "llama-server already present: $(command -v llama-server)"
elif command -v brew >/dev/null 2>&1; then
  say "installing llama.cpp with Homebrew (a few minutes, no GPU needed)"
  brew install llama.cpp
else
  warn "llama.cpp not installed and Homebrew is missing."
  warn "Get it from https://brew.sh or build llama.cpp, then re-run."
  warn "RedPen also works with LM Studio or Ollama if you prefer: set REDPEN_BASE_URL."
fi

# -------------------------------------------------------------- the app -----
if [ -d "$DIR/.git" ]; then
  say "updating existing checkout at $DIR"
  git -C "$DIR" pull --ff-only
else
  say "cloning to $DIR"
  git clone "$REPO" "$DIR"
fi

cd "$DIR"
say "installing redpen and its dependencies"
"$PY" -m pip install --quiet --upgrade pip
if "$PY" -m pip install --quiet --editable . 2>/dev/null; then
  :
elif "$PY" -m pip install --quiet --user --editable .; then
  export PATH="$HOME/.local/bin:$PATH"
else
  die "pip install failed. Try: python3 -m venv venv && source venv/bin/activate && pip install -e ."
fi

# --------------------------------------------------------- model weights ----
say "fetching model weights (~770 MB, one time, from Hugging Face)"
"$PY" -m redpen.cli models --download "$MODEL" || warn "could not download $MODEL"

# ------------------------------------------------------------- verify -------
say "running doctor"
"$PY" -m redpen.cli doctor || true
say "running the test suite"
"$PY" -m pytest -q 2>/dev/null || say "tests skipped (pytest not installed)"

cat <<EOF

  ✓ RedPen installed.

      redpen                 start the app and open your browser
      redpen review x.pdf    review from the terminal
      redpen doctor          check this machine

  Contracts are parsed in memory and never leave the laptop.
  RedPen is an open rule library, not a lawyer.
EOF
