#!/bin/sh
set -eu

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

iso_now() {
  date -u +"%Y-%m-%dT%H:%M:%S"
}

write_log() {
  log_path="$1"
  shift || true
  if [ -z "$log_path" ]; then
    return 0
  fi
  mkdir -p "$(dirname "$log_path")"
  timestamp="$(iso_now)"
  for line in "$@"; do
    if [ -n "${line:-}" ]; then
      printf '[%s] %s\n' "$timestamp" "$line" >> "$log_path"
    fi
  done
}

find_tool() {
  tool_name="$1"
  shift
  for candidate in "$@"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  if command -v "$tool_name" >/dev/null 2>&1; then
    command -v "$tool_name"
    return 0
  fi
  return 1
}

emit_json() {
  runtime_state="$1"
  handle="$2"
  pid="$3"
  last_activity="$4"
  last_handshake="$5"
  reason_code="$6"
  last_error="$7"
  log_excerpt="$8"
  exit_code="${9:-0}"

  printf '{'
  printf '"runtime_state":"%s",' "$(json_escape "$runtime_state")"
  printf '"handle":"%s",' "$(json_escape "$handle")"
  if [ -n "$pid" ]; then
    printf '"pid":%s,' "$pid"
  else
    printf '"pid":null,'
  fi
  printf '"last_activity_at":"%s",' "$(json_escape "$last_activity")"
  printf '"last_handshake_at":"%s",' "$(json_escape "$last_handshake")"
  if [ -n "$reason_code" ]; then
    printf '"reason_code":"%s",' "$(json_escape "$reason_code")"
  else
    printf '"reason_code":"",'
  fi
  printf '"last_error":"%s",' "$(json_escape "$last_error")"
  printf '"log_excerpt":"%s",' "$(json_escape "$log_excerpt")"
  printf '"exit_code":%s' "$exit_code"
  printf '}\n'
}

run_command() {
  log_path="$1"
  command_text="$2"
  require_auth="${3:-0}"

  if [ "$require_auth" = "1" ]; then
    temp_script="$(mktemp /tmp/proxyvault-wireguard-XXXXXX.sh)"
    cat > "$temp_script" <<EOF
#!/bin/sh
set -eu
$command_text
EOF
    chmod +x "$temp_script"
    output="$(
      /usr/bin/osascript -e "do shell script quoted form of POSIX path of POSIX file \"$temp_script\" with administrator privileges" 2>&1
    )" || {
      rm -f "$temp_script"
      write_log "$log_path" "$output"
      printf '%s' "$output"
      return 1
    }
    rm -f "$temp_script"
    write_log "$log_path" "$output"
    printf '%s' "$output"
    return 0
  fi

  output="$(sh -c "$command_text" 2>&1)" || {
    write_log "$log_path" "$output"
    printf '%s' "$output"
    return 1
  }
  write_log "$log_path" "$output"
  printf '%s' "$output"
  return 0
}

latest_handshake_iso() {
  handle="$1"
  wg_bin="$2"
  if [ -z "$wg_bin" ]; then
    return 0
  fi
  raw="$("$wg_bin" show "$handle" latest-handshakes 2>/dev/null || true)"
  max_epoch="$(printf '%s\n' "$raw" | awk 'BEGIN{max=0} NF >= 2 && $2+0 > max {max=$2+0} END{print max}')"
  if [ "$max_epoch" -gt 0 ] 2>/dev/null; then
    date -u -r "$max_epoch" +"%Y-%m-%dT%H:%M:%S"
  fi
}

COMMAND="${1:-}"
shift || true

CONFIG_PATH=""
LOG_PATH=""
HANDLE=""
TUNNEL_NAME=""
MACOS_AUTH="0"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --log)
      LOG_PATH="$2"
      shift 2
      ;;
    --handle)
      HANDLE="$2"
      shift 2
      ;;
    --tunnel-name)
      TUNNEL_NAME="$2"
      shift 2
      ;;
    --macos-authorization-flow|--unsigned-build-check)
      MACOS_AUTH="1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

WG_QUICK_BIN="$(find_tool wg-quick /opt/homebrew/bin/wg-quick /usr/local/bin/wg-quick || true)"
WG_BIN="$(find_tool wg /opt/homebrew/bin/wg /usr/local/bin/wg || true)"

if [ "$COMMAND" = "up" ]; then
  if [ ! -f "$CONFIG_PATH" ]; then
    emit_json "ERROR" "$TUNNEL_NAME" "" "$(iso_now)" "" "invalid_config" "WireGuard config was not found at $CONFIG_PATH." "WireGuard config was not found at $CONFIG_PATH." 1
    exit 1
  fi
  if [ -z "$WG_QUICK_BIN" ]; then
    message="wg-quick is not available. Install wireguard-tools via Homebrew or MacPorts before using WireGuard in ProxyVault."
    write_log "$LOG_PATH" "$message"
    emit_json "ERROR" "$TUNNEL_NAME" "" "$(iso_now)" "" "helper_not_found" "$message" "$message" 1
    exit 1
  fi
  command_text="$(shell_quote "$WG_QUICK_BIN") up $(shell_quote "$CONFIG_PATH")"
  output="$(run_command "$LOG_PATH" "$command_text" "$MACOS_AUTH")" || {
    reason="tunnel_exited_early"
    case "$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')" in
      *"not found"*|*"no such file"*)
        reason="helper_not_found"
        ;;
      *"operation not permitted"*|*"permission denied"*|*"administrator privileges"*|*"authorization was canceled"*|*"authorisation was canceled"*|*"user canceled"*)
        reason="privileges_required"
        ;;
      *"parse"*|*"invalid"*)
        reason="invalid_config"
        ;;
    esac
    emit_json "ERROR" "$TUNNEL_NAME" "" "$(iso_now)" "" "$reason" "$output" "$output" 1
    exit 1
  }
  handshake="$(latest_handshake_iso "$TUNNEL_NAME" "$WG_BIN")"
  emit_json "RUNNING" "$TUNNEL_NAME" "" "$(iso_now)" "$handshake" "" "" "$output" 0
  exit 0
fi

if [ "$COMMAND" = "down" ]; then
  if [ -z "$WG_QUICK_BIN" ]; then
    message="wg-quick is not available. Install wireguard-tools via Homebrew or MacPorts before using WireGuard in ProxyVault."
    write_log "$LOG_PATH" "$message"
    emit_json "ERROR" "$HANDLE" "" "$(iso_now)" "" "helper_not_found" "$message" "$message" 1
    exit 1
  fi
  target_ref="$CONFIG_PATH"
  if [ -z "$target_ref" ]; then
    target_ref="$HANDLE"
  fi
  command_text="$(shell_quote "$WG_QUICK_BIN") down $(shell_quote "$target_ref")"
  output="$(run_command "$LOG_PATH" "$command_text" "1")" || {
    lowered="$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')"
    if printf '%s' "$lowered" | grep -q "does not exist"; then
      emit_json "DISCONNECTED" "$HANDLE" "" "$(iso_now)" "" "" "" "$output" 0
      exit 0
    fi
    emit_json "ERROR" "$HANDLE" "" "$(iso_now)" "" "tunnel_exited_early" "$output" "$output" 1
    exit 1
  }
  emit_json "DISCONNECTED" "$HANDLE" "" "$(iso_now)" "" "" "" "$output" 0
  exit 0
fi

if [ "$COMMAND" = "status" ]; then
  if ! ifconfig "$HANDLE" >/dev/null 2>&1; then
    emit_json "DISCONNECTED" "$HANDLE" "" "$(iso_now)" "" "" "" "" 0
    exit 0
  fi
  handshake="$(latest_handshake_iso "$HANDLE" "$WG_BIN")"
  emit_json "RUNNING" "$HANDLE" "" "$(iso_now)" "$handshake" "" "" "" 0
  exit 0
fi

emit_json "ERROR" "$HANDLE" "" "$(iso_now)" "" "invalid_config" "Unsupported helper command: $COMMAND" "Unsupported helper command: $COMMAND" 2
exit 2
