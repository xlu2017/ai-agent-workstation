# Terminal Watcher Shell Hook for Zsh
# Source this in your .zshrc: source /opt/workstation/glue/terminal-watcher/shell-hook.zsh
#
# Automatically captures failed commands and sends them to the terminal watcher.

__tw_preexec() {
  # Store the command about to be executed
  __TW_LAST_COMMAND="$1"
}

__tw_precmd() {
  local exit_code=$?
  
  # Only fire on non-zero exit codes
  if [[ $exit_code -ne 0 && -n "$__TW_LAST_COMMAND" ]]; then
    # Determine session ID from environment or tmux
    local session_id="${WORKSTATION_SESSION_ID:-}"
    local tmux_session=""
    
    if [[ -n "$TMUX" ]]; then
      tmux_session=$(tmux display-message -p '#{session_name}' 2>/dev/null)
      if [[ -z "$session_id" ]]; then
        # Derive from tmux session name (strip "agent-" prefix)
        session_id="${tmux_session#agent-}"
      fi
    fi
    
    if [[ -n "$session_id" ]]; then
      # Fire the hook asynchronously to avoid slowing down the shell
      python3 /opt/workstation/glue/terminal-watcher/watcher.py hook \
        "$session_id" "$__TW_LAST_COMMAND" "$exit_code" "$tmux_session" &>/dev/null &
    fi
  fi
  
  unset __TW_LAST_COMMAND
}

# Register hooks
autoload -Uz add-zsh-hook
add-zsh-hook preexec __tw_preexec
add-zsh-hook precmd __tw_precmd
