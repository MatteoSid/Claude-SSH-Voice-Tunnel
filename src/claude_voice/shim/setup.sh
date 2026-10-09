#!/bin/sh
# claude-voice: hook (or unhook) the `claude` wrapper into the server's shell configs.
# Usage: sh ~/.claude-voice/setup.sh install|uninstall
set -e
D="$HOME/.claude-voice"
BEGIN="# >>> claude-voice >>>"
END="# <<< claude-voice <<<"
FISH="$HOME/.config/fish/functions/claude.fish"

strip() {  # remove our block from file $1, keeping the file itself (symlinks, permissions)
  [ -f "$1" ] && grep -qF "$BEGIN" "$1" || return 0
  sed "/^$BEGIN\$/,/^$END\$/d" "$1" > "$1.claude-voice.tmp"
  cat "$1.claude-voice.tmp" > "$1" && rm -f "$1.claude-voice.tmp"
}

case "$1" in
  install)
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
      [ "$rc" = "$HOME/.bashrc" ] || [ -f "$rc" ] || continue
      strip "$rc"
      # shellcheck disable=SC2016  # written literally, expanded by the user's shell
      printf '%s\n' "$BEGIN" 'claude() { "$HOME/.claude-voice/bin/claude-wrap" "$@"; }' "$END" >> "$rc"
      echo "claude-voice: hooked $rc"
    done
    if command -v fish >/dev/null 2>&1; then
      mkdir -p "${FISH%/*}"
      printf '%s\n' "$BEGIN" 'function claude' '    ~/.claude-voice/bin/claude-wrap $argv' 'end' > "$FISH"
      echo "claude-voice: hooked $FISH"
    fi
    echo "claude-voice: installed in $D (open a new terminal on the server)"
    ;;
  uninstall)
    strip "$HOME/.bashrc"
    strip "$HOME/.zshrc"
    if [ -f "$FISH" ] && grep -qF "$BEGIN" "$FISH"; then rm -f "$FISH"; fi
    rm -rf "$D"
    echo "claude-voice: removed from this server"
    ;;
  *) echo "usage: $0 install|uninstall" >&2; exit 2 ;;
esac
