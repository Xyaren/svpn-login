#!/bin/bash

set +x

if [ "$(id -u)" != "0" ]; then
  echo "This script must be run as root" 1>&2
  exit 1
fi

if [ $SUDO_USER ]; then
  real_user=$SUDO_USER
else
  real_user=$(whoami)
fi

script_full_path=$(dirname "$0")

PID_FILE=/var/run/vpn.pid

#
if [ -f $PID_FILE ]; then
  PREV_PID=$(cat $PID_FILE)
  echo "Stopping PID $PREV_PID"
  kill -SIGKILL "$PREV_PID"
  while kill -0 "$PREV_PID"; do
    sleep 1
  done
  echo "Stopped PID $PREV_PID"
  rm -f "$PID_FILE"
fi

echo $$ >$PID_FILE

remove_pid() {
  rm -f "$PID_FILE"
}

trap remove_pid SIGQUIT SIGINT SIGTERM

# Source the credentials file if it exists
CREDENTIALS_FILE="${script_full_path}/.credentials"
if [ -f "$CREDENTIALS_FILE" ]; then
  set -o allexport
  source "$CREDENTIALS_FILE"
  set +o allexport
fi

# Prompt for missing credentials

if [ -z "$HOSTNAME" ]; then
  read -p "Enter Hostname: " HOSTNAME
fi

if [ -z "$USERNAME" ]; then
  read -p "Enter Username (AD Email): " USERNAME
fi

if [ -z "$PASSWORD" ]; then
  read -s -p "Enter Password: " PASSWORD
  echo ""
fi

if [ -z "$TOTP" ]; then
  read -p "Enter TOTP: " TOTP
fi

token=$(sudo -H -u "$real_user" bash -c "source $script_full_path/venv/bin/activate && $script_full_path/token-extract.py -s '$HOSTNAME' -u '$USERNAME' -p '$PASSWORD' -t '$TOTP' -o direct") > >(sed 's/^/Login: /') 2> >(sed 's/^/Login (err): /' >&2)

tear_down() {
  echo "Teardown..."
  resolvectl dns tun0 "" >/dev/null 2>&1 || true
  resolvectl domain tun0 "" >/dev/null 2>&1 || true
  ip route del 10.0.0.0/8 dev tun0 >/dev/null 2>&1 || true
  echo "Complete"
}

set_up() {
  echo "Adding route for 10.0.0.0/8"
  ip route add 10.0.0.0/8 dev tun0
}

watch_tunnel() {
  sleep 2
  until [[ $(ip -s tuntap) = tun* ]]; do
    echo '⏳ Waiting for Tunnel to come up...'
    sleep 2
  done

  echo "🟢 ONLINE!"
  set_up

  until [[ $(ip -s tuntap) != tun* ]]; do
    sleep 1
  done
  ip -s tuntap
  echo "🔴 OFFLINE"

  watch_tunnel &
}

start_vpn() {
  echo "$token"
  echo "Starting"

  #add trap
  interrupt_handler() {
    kill -SIGINT "$child_pid" # Forward the interrupt signal to the Python script
    wait "$child_pid"
    echo "Shutting down. Please wait..."

    remove_pid
  }

  # Set up the interrupt handler
  trap interrupt_handler SIGINT SIGTERM EXIT

  watch_tunnel &
  PYTHONUNBUFFERED=true exec "$script_full_path/venv/bin/python3" "$script_full_path/svpn-login.py" --sessionid="$token" --skip-routes --reconnect "$HOSTNAME" | ts "🔌 SVPN:" &
  child_pid=$!
  wait "$child_pid"
  echo "svpn.py finished"

  trap '' SIGINT SIGTERM EXIT
  tear_down

  remove_pid
}

start_vpn
