#!/usr/bin/env bash
# Foreground server process (what the tmux session runs). Use bin/start.sh.
. "$(dirname -- "$0")/../../lib/common.sh"
cd "$SERVER_DIR"
read -r loader lver mc <.installed-loader
java=$(java_for_mc "$mc")
case $loader in
  neoforge) exec "$java" @user_jvm_args.txt @"libraries/net/neoforged/neoforge/$lver/unix_args.txt" nogui ;;
  fabric) exec "$java" $(grep -v '^#' user_jvm_args.txt | xargs) -jar fabric-server-launch.jar nogui ;;
  *) die "unknown loader in .installed-loader: $loader" ;;
esac
