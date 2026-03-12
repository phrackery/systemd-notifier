#!/usr/bin/env bash
#
# systemd-notifier Telegram sender script
# Sends messages to Telegram with retry logic and error handling
#
# Usage: telegram.sh "Your message here"
#

set -euo pipefail

# Configuration (can be overridden via environment variables)
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# Retry configuration
MAX_RETRIES="${TELEGRAM_MAX_RETRIES:-3}"
RETRY_DELAY="${TELEGRAM_RETRY_DELAY:-2}"

# Timeout for curl command (seconds)
CURL_TIMEOUT="${TELEGRAM_TIMEOUT:-30}"

# Function to URL encode a string
url_encode() {
    local string="$1"
    # Use Python for proper URL encoding if available
    if command -v python3 &>/dev/null; then
        python3 -c "import urllib.parse; print(urllib.parse.quote('''$string'''))"
    elif command -v python &>/dev/null; then
        python -c "import urllib; print urllib.quote('''$string''')" 2>/dev/null || echo "$string"
    else
        # Fallback to simple space encoding (basic)
        echo "$string" | sed 's/ /%20/g'
    fi
}

# Function to send message to Telegram
send_message() {
    local message="$1"
    local attempt=1
    local response
    local http_code
    local curl_exit
    
    # URL encode the message
    local encoded_message
    encoded_message=$(url_encode "$message")
    
    while [[ $attempt -le $MAX_RETRIES ]]; do
        # Send the request
        response=$(curl -s -w "\n%{http_code}" \
            --max-time "$CURL_TIMEOUT" \
            -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${encoded_message}" \
            -d "parse_mode=HTML" \
            -d "disable_notification=false" \
            2>/dev/null) || curl_exit=$?
        
        # Check if curl failed
        if [[ ${curl_exit:-0} -ne 0 ]]; then
            echo "Attempt $attempt failed: curl error (exit code: ${curl_exit:-0})" >&2
            
            if [[ $attempt -lt $MAX_RETRIES ]]; then
                sleep "$RETRY_DELAY"
                attempt=$((attempt + 1))
                continue
            else
                echo "Failed to send message after $MAX_RETRIES attempts" >&2
                return 1
            fi
        fi
        
        # Extract HTTP code and response body
        http_code=$(echo "$response" | tail -n1)
        body=$(echo "$response" | head -n -1)
        
        # Check if successful
        if [[ "$http_code" == "200" ]] && echo "$body" | grep -q '"ok":true'; then
            echo "Message sent successfully"
            return 0
        fi
        
        # Extract error message if available
        local error_desc
        error_desc=$(echo "$body" | grep -oP '"description":"\K[^"]+' 2>/dev/null || echo "Unknown error")
        
        echo "Attempt $attempt failed (HTTP $http_code): $error_desc" >&2
        
        # Check for rate limiting
        if [[ "$http_code" == "429" ]]; then
            local retry_after
            retry_after=$(echo "$body" | grep -oP '"retry_after":\K\d+' 2>/dev/null || echo "60")
            echo "Rate limited. Waiting ${retry_after}s..." >&2
            sleep "$retry_after"
        elif [[ $attempt -lt $MAX_RETRIES ]]; then
            sleep "$RETRY_DELAY"
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "Failed to send message after $MAX_RETRIES attempts" >&2
    return 1
}

# Main execution
main() {
    # Validate arguments
    if [[ $# -eq 0 ]]; then
        echo "Usage: $0 \"Your message here\"" >&2
        exit 1
    fi
    
    # Validate configuration
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
        echo "Error: TELEGRAM_BOT_TOKEN is not set" >&2
        exit 1
    fi
    
    if [[ -z "$TELEGRAM_CHAT_ID" ]]; then
        echo "Error: TELEGRAM_CHAT_ID is not set" >&2
        exit 1
    fi
    
    # Check if curl is available
    if ! command -v curl &>/dev/null; then
        echo "Error: curl is required but not installed" >&2
        exit 1
    fi
    
    # Send the message
    message="$1"
    if send_message "$message"; then
        exit 0
    else
        exit 1
    fi
}

main "$@"
