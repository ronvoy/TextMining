#!/usr/bin/env bash
# wsgi_setup.sh — one-time setup for the Legal RAG app on a cPanel WSGI host
#
# Usage:
#   chmod +x wsgi_setup.sh
#   ./wsgi_setup.sh
#
# What it does:
#   1. Locates the correct Python / pip from the active cPanel virtualenv
#      (or falls back to the system python3).
#   2. Upgrades pip + setuptools.
#   3. Installs all requirements from requirements.txt.
#   4. Creates a .env file from .env.openrouter.example if .env is missing.
#   5. Checks that the vector_store indexes are present.
#   6. Creates the .htaccess file needed for WebSocket proxying.
#
# Run this once after uploading the app to the server.  It is safe to
# re-run — every step is idempotent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "▶ Working directory: $SCRIPT_DIR"

# ── 1. Locate Python interpreter ──────────────────────────────────────────────

# cPanel creates virtualenvs at ~/virtualenv/<domain>/<version>/bin/python
# Passenger sets PASSENGER_APP_ENV and activates the venv for us, but when
# running this script manually we need to find it ourselves.

PYTHON=""

# (a) Already inside an activated virtualenv?
if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON="$VIRTUAL_ENV/bin/python"
    echo "✔ Using active virtualenv: $PYTHON"

# (b) cPanel virtualenv sitting next to the app root (common layout)
elif [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
    echo "✔ Found local venv: $PYTHON"

# (c) Search ~/virtualenv for any env that contains streamlit
else
    FOUND=$(find "$HOME/virtualenv" -name "python" -type f 2>/dev/null | head -1 || true)
    if [[ -n "$FOUND" ]]; then
        PYTHON="$FOUND"
        echo "✔ Found cPanel virtualenv python: $PYTHON"
    else
        PYTHON="$(command -v python3 || command -v python)"
        echo "⚠ No virtualenv found — using system python: $PYTHON"
    fi
fi

PIP="$PYTHON -m pip"
echo "▶ Python: $($PYTHON --version)"

# ── 2. Upgrade pip & setuptools ───────────────────────────────────────────────

echo ""
echo "▶ Upgrading pip and setuptools..."
$PIP install --quiet --upgrade pip setuptools wheel

# ── 3. Install requirements ───────────────────────────────────────────────────

echo ""
echo "▶ Installing requirements from requirements.txt..."
$PIP install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "✔ Requirements installed."

# Verify Streamlit is importable
if $PYTHON -c "import streamlit" 2>/dev/null; then
    echo "✔ Streamlit import OK."
else
    echo "✗ ERROR: streamlit could not be imported. Check your virtualenv." >&2
    exit 1
fi

# ── 4. Create .env if missing ─────────────────────────────────────────────────

echo ""
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    if [[ -f "$SCRIPT_DIR/.env.openrouter.example" ]]; then
        cp "$SCRIPT_DIR/.env.openrouter.example" "$SCRIPT_DIR/.env"
        echo "✔ .env created from .env.openrouter.example."
        echo "  ⚠ Edit .env and set your API keys before starting the app!"
    else
        cat > "$SCRIPT_DIR/.env" <<'EOF'
# Legal RAG – environment variables
# Fill in your actual keys before starting the app.

OPENROUTER_API_KEY=your_openrouter_api_key_here
HUGGINGFACEHUB_API_TOKEN=your_huggingface_token_here

# Optional: override the port Streamlit binds to
# STREAMLIT_PORT=8501
EOF
        echo "✔ Blank .env created. Fill in your API keys!"
    fi
else
    echo "✔ .env already exists — skipping."
fi

# ── 5. Check vector stores ────────────────────────────────────────────────────

echo ""
echo "▶ Checking vector stores..."
VECTOR_DIR="$SCRIPT_DIR/vector_store"
REQUIRED_INDEXES=(
    "divorce_cases/index.faiss"
    "divorce_codes/index.faiss"
    "inheritance_cases/index.faiss"
    "inheritance_codes/index.faiss"
)
MISSING=0
for idx in "${REQUIRED_INDEXES[@]}"; do
    if [[ -f "$VECTOR_DIR/$idx" ]]; then
        echo "  ✔ $idx"
    else
        echo "  ✗ MISSING: $idx"
        MISSING=$((MISSING + 1))
    fi
done

if [[ $MISSING -gt 0 ]]; then
    echo ""
    echo "  ⚠ $MISSING vector store index(es) are missing."
    echo "  Run the following to build them:"
    echo "    $PYTHON $SCRIPT_DIR/build_vector_stores.py"
    echo ""
    read -rp "  Build vector stores now? [y/N] " BUILD_NOW
    if [[ "${BUILD_NOW,,}" == "y" ]]; then
        echo "▶ Building vector stores (this may take several minutes)..."
        $PYTHON "$SCRIPT_DIR/build_vector_stores.py"
        echo "✔ Vector stores built."
    fi
else
    echo "✔ All vector store indexes present."
fi

# ── 6. Create / update .htaccess for WebSocket proxying ──────────────────────

echo ""
HTACCESS="$SCRIPT_DIR/.htaccess"
PORT="${STREAMLIT_PORT:-8501}"

if [[ ! -f "$HTACCESS" ]]; then
    cat > "$HTACCESS" <<EOF
# Legal RAG — WebSocket + HTTP proxy rules for Streamlit on cPanel
# Requires: mod_proxy, mod_proxy_http, mod_proxy_wstunnel

Options -Indexes
PassengerEnabled on
PassengerAppRoot ${SCRIPT_DIR}

RewriteEngine On

# Forward WebSocket upgrade requests directly to Streamlit
RewriteCond %{HTTP:Upgrade} websocket [NC]
RewriteRule /(.*) ws://127.0.0.1:${PORT}/\$1 [P,L]

# Forward all other requests through the WSGI proxy
RewriteRule ^(.*)\$ http://127.0.0.1:${PORT}/\$1 [P,L]

ProxyPassReverse / http://127.0.0.1:${PORT}/
EOF
    echo "✔ .htaccess created (port ${PORT})."
else
    echo "✔ .htaccess already exists — skipping."
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "   1. Verify your API keys in .env"
echo "   2. In cPanel → Setup Python App:"
echo "        Application root : (this folder)"
echo "        Application URL  : your domain or subdomain"
echo "        Application startup file : passenger_wsgi.py"
echo "        Application Entry point  : application"
echo "   3. Restart the Python app from cPanel to apply changes."
echo "══════════════════════════════════════════════════"
