# Terminal Watcher Shell Hook for Bash
# Source this in your .bashrc: source /opt/workstation/glue/terminal-watcher/shell-hook.bash
#
# Automatically captures failed commands and sends them to the terminal watcher.

__tw_last_command=""

__tw_preexec() {
  __tw_last_command="$1"
}

__tw_precmd() {
  local exit_code=$?
  
  if [[ $exit_code -ne 0 && -n "$__tw_last_command" ]]; then
    local session_id="${WORKSTATION_SESSION_ID:-}"
    local tmux_session=""
    
    if [[ -n "$TMUX" ]]; then
      tmux_session=$(tmux display-message -p '#{session_name}' 2>/dev/null)
      if [[ -z "$session_id" ]]; then
        session_id="${tmux_session#agent-}"
      fi
    fi
    
    if [[ -n "$session_id" ]]; then
      python3 /opt/workstation/glue/terminal-watcher/watcher.py hook \
        "$session_id" "$__tw_last_command" "$exit_code" "$tmux_session" &>/dev/null &
    fi
  fi
  
  __tw_last_command=""
}

# Bash preexec emulation via DEBUG trap
trap '__tw_preexec "$BASH_COMMAND"' DEBUG
PROMPT_COMMAND="__tw_precmd${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
