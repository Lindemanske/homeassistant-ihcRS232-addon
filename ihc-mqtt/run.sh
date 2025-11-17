#!/usr/bin/with-contenv bashio

bashio::log.info "Starting IHC RS232 MQTT Bridge..."

# Lees configuratie uit add-on options
export SERIAL_PORT=$(bashio::config 'serial_port')
export SERIAL_BAUD=$(bashio::config 'serial_baud')
export MQTT_HOST=$(bashio::config 'mqtt_host')
export MQTT_PORT=$(bashio::config 'mqtt_port')
export MQTT_USER=$(bashio::config 'mqtt_user')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
export MQTT_TOPIC=$(bashio::config 'mqtt_topic')
export NUM_OUTPUT_MODULES=$(bashio::config 'num_output_modules')
export NUM_INPUT_MODULES=$(bashio::config 'num_input_modules')
export POLL_INTERVAL=$(bashio::config 'poll_interval')
export LOG_LEVEL=$(bashio::config 'log_level')

bashio::log.info "Configuration loaded:"
bashio::log.info "  Serial Port: ${SERIAL_PORT}"
bashio::log.info "  MQTT: ${MQTT_HOST}:${MQTT_PORT}"
bashio::log.info "  Output Modules: ${NUM_OUTPUT_MODULES}"
bashio::log.info "  Input Modules: ${NUM_INPUT_MODULES}"
bashio::log.info "  Poll Interval: ${POLL_INTERVAL}s"

# Check of serial device bestaat
if [ ! -e "${SERIAL_PORT}" ]; then
    bashio::log.error "Serial device ${SERIAL_PORT} not found!"
    bashio::log.info "Available serial devices:"
    ls -la /dev/tty* 2>/dev/null | grep -E "ttyUSB|ttyAMA|ttyS" || bashio::log.info "  No devices found"
    
    if [ -d "/dev/serial/by-id" ]; then
        bashio::log.info "Devices by ID:"
        ls -la /dev/serial/by-id/ 2>/dev/null || bashio::log.info "  None"
    fi
    
    bashio::log.error "Please check your USB connection and serial_port configuration"
    exit 1
fi

bashio::log.info "Serial device found: ${SERIAL_PORT}"

# Start Python daemon met unbuffered output
bashio::log.info "Starting IHC daemon..."
exec python3 -u /ihc_mqtt.py