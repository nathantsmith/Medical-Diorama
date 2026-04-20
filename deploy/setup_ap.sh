#!/usr/bin/env bash

set -euo pipefail

CONNECTION_NAME="medical-diorama-ap"
IFACE="wlan0"
SSID="MedicalDiorama"
PASSWORD=""
CHANNEL="6"
MODE="start"

usage() {
    cat <<'EOF'
Usage: sudo ./deploy/setup_ap.sh [options]

Create and manage a Wi-Fi access point using NetworkManager on Raspberry Pi OS.

Modes:
  --start           Create/update the AP profile and bring it up (default)
  --stop            Bring the AP profile down
  --delete          Delete the AP profile from NetworkManager
  --status          Show AP profile status

Options:
  --ssid NAME       Wi-Fi SSID to broadcast
  --password PASS   WPA2 passphrase (8-63 chars)
  --iface IFACE     Wireless interface name (default: wlan0)
  --channel N       Wi-Fi channel (default: 6)
  --name NAME       NetworkManager connection name
  --help            Show this help text

Examples:
  sudo ./deploy/setup_ap.sh --ssid MedicalDioramaSetup --password 'replace-me'
  sudo ./deploy/setup_ap.sh --status
  sudo ./deploy/setup_ap.sh --stop
  sudo ./deploy/setup_ap.sh --delete
EOF
}

log() {
    printf '[ap] %s\n' "$*"
}

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Run this script with sudo." >&2
        exit 1
    fi
}

require_nmcli() {
    if ! command -v nmcli > /dev/null 2>&1; then
        echo "nmcli not found. Install NetworkManager first." >&2
        exit 1
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --start)
                MODE="start"
                shift
                ;;
            --stop)
                MODE="stop"
                shift
                ;;
            --delete)
                MODE="delete"
                shift
                ;;
            --status)
                MODE="status"
                shift
                ;;
            --ssid)
                SSID="$2"
                shift 2
                ;;
            --password)
                PASSWORD="$2"
                shift 2
                ;;
            --iface)
                IFACE="$2"
                shift 2
                ;;
            --channel)
                CHANNEL="$2"
                shift 2
                ;;
            --name)
                CONNECTION_NAME="$2"
                shift 2
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown argument: $1" >&2
                usage
                exit 1
                ;;
        esac
    done
}

validate_password() {
    if [[ "${MODE}" != "start" ]]; then
        return
    fi

    if [[ ${#PASSWORD} -lt 8 || ${#PASSWORD} -gt 63 ]]; then
        echo "Provide --password with a WPA2 passphrase between 8 and 63 characters." >&2
        exit 1
    fi
}

connection_exists() {
    nmcli -t -f NAME connection show | grep -Fxq "${CONNECTION_NAME}"
}

ensure_profile() {
    if connection_exists; then
        log "Updating existing AP profile ${CONNECTION_NAME}"
        nmcli connection modify "${CONNECTION_NAME}" \
            connection.id "${CONNECTION_NAME}" \
            connection.interface-name "${IFACE}" \
            802-11-wireless.ssid "${SSID}" \
            802-11-wireless.mode ap \
            802-11-wireless.band bg \
            802-11-wireless.channel "${CHANNEL}" \
            802-11-wireless-security.key-mgmt wpa-psk \
            802-11-wireless-security.psk "${PASSWORD}" \
            ipv4.method shared \
            ipv6.method ignore \
            connection.autoconnect yes
    else
        log "Creating AP profile ${CONNECTION_NAME}"
        nmcli connection add type wifi \
            con-name "${CONNECTION_NAME}" \
            ifname "${IFACE}" \
            autoconnect yes \
            ssid "${SSID}"
        nmcli connection modify "${CONNECTION_NAME}" \
            802-11-wireless.mode ap \
            802-11-wireless.band bg \
            802-11-wireless.channel "${CHANNEL}" \
            wifi-sec.key-mgmt wpa-psk \
            wifi-sec.psk "${PASSWORD}" \
            ipv4.method shared \
            ipv6.method ignore
    fi
}

start_ap() {
    ensure_profile
    log "Bringing up AP ${CONNECTION_NAME}"
    nmcli connection up "${CONNECTION_NAME}"
    log "Hotspot active"
    log "SSID: ${SSID}"
    log "Interface: ${IFACE}"
    log "Inspect address with: nmcli -f GENERAL.DEVICES,IP4.ADDRESS connection show '${CONNECTION_NAME}'"
}

stop_ap() {
    if ! connection_exists; then
        log "AP profile ${CONNECTION_NAME} does not exist"
        return
    fi
    log "Bringing down AP ${CONNECTION_NAME}"
    nmcli connection down "${CONNECTION_NAME}" || true
}

delete_ap() {
    if ! connection_exists; then
        log "AP profile ${CONNECTION_NAME} does not exist"
        return
    fi
    stop_ap
    log "Deleting AP ${CONNECTION_NAME}"
    nmcli connection delete "${CONNECTION_NAME}"
}

status_ap() {
    if ! connection_exists; then
        log "AP profile ${CONNECTION_NAME} does not exist"
        return
    fi
    nmcli connection show "${CONNECTION_NAME}"
}

main() {
    require_root
    require_nmcli
    parse_args "$@"
    validate_password

    case "${MODE}" in
        start)
            start_ap
            ;;
        stop)
            stop_ap
            ;;
        delete)
            delete_ap
            ;;
        status)
            status_ap
            ;;
    esac
}

main "$@"
