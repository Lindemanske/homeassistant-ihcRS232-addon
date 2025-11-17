#!/usr/bin/env python3
"""
IHC RS232 MQTT Bridge Add-on voor Home Assistant
Leest configuratie uit environment variables (gezet door run.sh)
"""

import serial
import paho.mqtt.client as mqtt
import json
import time
import logging
import threading
import os
import sys

# Lees configuratie uit environment variables
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
SERIAL_BAUD = int(os.getenv('SERIAL_BAUD', '19200'))
MQTT_HOST = os.getenv('MQTT_HOST', 'core-mosquitto')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USER = os.getenv('MQTT_USER', '')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'ihc')
NUM_OUTPUT_MODULES = int(os.getenv('NUM_OUTPUT_MODULES', '8'))
NUM_INPUT_MODULES = int(os.getenv('NUM_INPUT_MODULES', '4'))
POLL_INTERVAL = float(os.getenv('POLL_INTERVAL', '2.0'))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'info').upper()

# Configureer logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger('IHC-MQTT')

# IHC Protocol constants
STX = 0x02
ETB = 0x17
ID_IHC = 0x04
ID_PC = 0x1D

CMD_DATA_READY = 0x30
CMD_SET_OUTPUT = 0x7A
CMD_GET_OUTPUTS = 0x82
CMD_OUTP_STATE = 0x83
CMD_GET_INPUTS = 0x86
CMD_INP_STATE = 0x87
CMD_ACT_INPUT = 0x88


class IHCProtocol:
    """IHC RS232 Protocol Handler"""
    
    def __init__(self, port, baudrate):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
            logger.info(f"✓ RS232 opened: {port} @ {baudrate} baud")
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {port}: {e}")
            raise
        
        self.rx_buffer = bytearray()
        self.last_rx_time = 0
    
    def calculate_crc(self, data):
        return sum(data) & 0xFF
    
    def send_packet(self, dest_id, cmd, data=None):
        packet = bytearray([STX, dest_id, cmd])
        if data:
            packet.extend(data)
        packet.append(ETB)
        packet.append(self.calculate_crc(packet))
        
        self.ser.write(packet)
        self.ser.flush()
        logger.debug(f"TX: {' '.join(f'{b:02X}' for b in packet)}")
    
    def read_packet(self, timeout=1.0):
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.ser.in_waiting:
                data = self.ser.read(self.ser.in_waiting)
                self.rx_buffer.extend(data)
                self.last_rx_time = time.time()
            
            if self.rx_buffer and time.time() - self.last_rx_time > 0.05:
                stx_idx = self.rx_buffer.find(STX)
                if stx_idx == -1:
                    self.rx_buffer.clear()
                    continue
                
                if stx_idx > 0:
                    self.rx_buffer = self.rx_buffer[stx_idx:]
                
                etb_idx = self.rx_buffer.find(ETB, 1)
                if etb_idx != -1 and len(self.rx_buffer) > etb_idx + 1:
                    packet = self.rx_buffer[:etb_idx + 2]
                    self.rx_buffer = self.rx_buffer[etb_idx + 2:]
                    
                    expected_crc = self.calculate_crc(packet[:-1])
                    if packet[-1] == expected_crc:
                        logger.debug(f"RX: {' '.join(f'{b:02X}' for b in packet)}")
                        return packet
                    else:
                        logger.warning(f"CRC error")
                        continue
            
            time.sleep(0.01)
        
        return None


class IHCController:
    """IHC Controller Manager"""
    
    def __init__(self, protocol):
        self.protocol = protocol
        self.output_states = [0] * NUM_OUTPUT_MODULES
        self.input_states = [0] * NUM_INPUT_MODULES
        self.pending_command = None
        self.lock = threading.Lock()
    
    def set_output(self, module, output, state):
        data = bytearray([module, output, 1 if state else 0])
        with self.lock:
            self.pending_command = (CMD_SET_OUTPUT, data)
        logger.info(f"Queued: SET_OUTPUT M{module}-O{output} = {'ON' if state else 'OFF'}")
    
    def request_outputs(self, module):
        data = bytearray([module])
        with self.lock:
            self.pending_command = (CMD_GET_OUTPUTS, data)
    
    def request_inputs(self, module):
        data = bytearray([module])
        with self.lock:
            self.pending_command = (CMD_GET_INPUTS, data)
    
    def process_packet(self, packet):
        if len(packet) < 5:
            return None
        
        pkt_id = packet[1]
        cmd = packet[2]
        
        if cmd == CMD_DATA_READY and pkt_id == ID_PC:
            return 'data_ready'
        elif cmd == CMD_OUTP_STATE and len(packet) >= 6:
            module = packet[3]
            state = packet[4]
            if module < NUM_OUTPUT_MODULES:
                self.output_states[module] = state
                return ('output_state', module, state)
        elif cmd == CMD_INP_STATE and len(packet) >= 7:
            module = packet[3]
            state_low = packet[4]
            state_high = packet[5]
            state = (state_high << 8) | state_low
            if module < NUM_INPUT_MODULES:
                self.input_states[module] = state
                return ('input_state', module, state)
        elif cmd == CMD_ACT_INPUT and len(packet) >= 6:
            module = packet[3]
            input_num = packet[4]
            return ('input_activated', module, input_num)
        
        return None
    
    def handle_data_ready(self):
        with self.lock:
            if self.pending_command:
                cmd, data = self.pending_command
                self.protocol.send_packet(ID_IHC, cmd, data)
                self.pending_command = None
                return True
        return False
    
    def get_output_state(self, module, output):
        if module >= NUM_OUTPUT_MODULES or output >= 8:
            return False
        return bool(self.output_states[module] & (1 << output))
    
    def get_input_state(self, module, input_num):
        if module >= NUM_INPUT_MODULES or input_num >= 16:
            return False
        return bool(self.input_states[module] & (1 << input_num))


class MQTTBridge:
    """MQTT Bridge voor Home Assistant"""
    
    def __init__(self, ihc_controller):
        self.ihc = ihc_controller
        self.client = mqtt.Client()
        
        if MQTT_USER and MQTT_PASSWORD:
            self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        try:
            self.client.connect(MQTT_HOST, MQTT_PORT, 60)
            self.client.loop_start()
            logger.info(f"✓ MQTT connected to {MQTT_HOST}:{MQTT_PORT}")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            raise
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"✓ MQTT connected successfully")
            self.client.subscribe(f"{MQTT_TOPIC}/output/+/+/set")
            self.publish_discovery()
        else:
            logger.error(f"MQTT connection failed with code {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning(f"MQTT disconnected unexpectedly. Reconnecting...")
    
    def on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split('/')
            if len(parts) == 5 and parts[1] == 'output' and parts[4] == 'set':
                module = int(parts[2])
                output = int(parts[3])
                state = msg.payload.decode().upper() == 'ON'
                
                logger.info(f"MQTT command: M{module}-O{output} = {state}")
                self.ihc.set_output(module, output, state)
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")
    
    def publish_discovery(self):
        """Home Assistant MQTT Discovery"""
        logger.info("Publishing Home Assistant discovery...")
        
        # Outputs als switches
        for module in range(NUM_OUTPUT_MODULES):
            for output in range(8):
                config = {
                    "name": f"IHC Output {module}-{output}",
                    "unique_id": f"ihc_output_{module}_{output}",
                    "state_topic": f"{MQTT_TOPIC}/output/{module}/{output}/state",
                    "command_topic": f"{MQTT_TOPIC}/output/{module}/{output}/set",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device": {
                        "identifiers": ["ihc_controller"],
                        "name": "IHC Controller",
                        "manufacturer": "LK/Gardy",
                        "model": "IHC Control"
                    }
                }
                topic = f"homeassistant/switch/ihc_output_{module}_{output}/config"
                self.client.publish(topic, json.dumps(config), retain=True)
        
        # Inputs als binary sensors
        for module in range(NUM_INPUT_MODULES):
            for input_num in range(16):
                config = {
                    "name": f"IHC Input {module}-{input_num}",
                    "unique_id": f"ihc_input_{module}_{input_num}",
                    "state_topic": f"{MQTT_TOPIC}/input/{module}/{input_num}/state",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "motion",
                    "device": {
                        "identifiers": ["ihc_controller"],
                        "name": "IHC Controller"
                    }
                }
                topic = f"homeassistant/binary_sensor/ihc_input_{module}_{input_num}/config"
                self.client.publish(topic, json.dumps(config), retain=True)
        
        logger.info(f"✓ Published {NUM_OUTPUT_MODULES*8} outputs and {NUM_INPUT_MODULES*16} inputs")
    
    def publish_output_state(self, module, output, state):
        topic = f"{MQTT_TOPIC}/output/{module}/{output}/state"
        payload = "ON" if state else "OFF"
        self.client.publish(topic, payload, retain=True)
    
    def publish_input_state(self, module, input_num, state):
        topic = f"{MQTT_TOPIC}/input/{module}/{input_num}/state"
        payload = "ON" if state else "OFF"
        self.client.publish(topic, payload, retain=True)


def main():
    logger.info("=" * 60)
    logger.info("IHC RS232 MQTT Bridge Add-on Starting")
    logger.info("=" * 60)
    logger.info(f"Serial: {SERIAL_PORT} @ {SERIAL_BAUD} baud")
    logger.info(f"MQTT: {MQTT_HOST}:{MQTT_PORT}")
    logger.info(f"Modules: {NUM_OUTPUT_MODULES} outputs, {NUM_INPUT_MODULES} inputs")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info("=" * 60)
    
    try:
        protocol = IHCProtocol(SERIAL_PORT, SERIAL_BAUD)
        ihc = IHCController(protocol)
        mqtt_bridge = MQTTBridge(ihc)
        
        current_module = 0
        poll_outputs = True
        last_poll_time = 0
        
        logger.info("✓ Daemon started - listening for packets...")
        
        while True:
            packet = protocol.read_packet(timeout=0.5)
            
            if packet:
                result = ihc.process_packet(packet)
                
                if result == 'data_ready':
                    if not ihc.handle_data_ready():
                        if time.time() - last_poll_time > POLL_INTERVAL:
                            if poll_outputs:
                                ihc.request_outputs(current_module)
                            else:
                                ihc.request_inputs(current_module)
                            
                            poll_outputs = not poll_outputs
                            if poll_outputs:
                                current_module = (current_module + 1) % max(NUM_OUTPUT_MODULES, NUM_INPUT_MODULES)
                            
                            last_poll_time = time.time()
                
                elif result and result[0] == 'output_state':
                    _, module, state = result
                    logger.debug(f"Output M{module}: {state:08b}")
                    for output in range(8):
                        mqtt_bridge.publish_output_state(module, output, bool(state & (1 << output)))
                
                elif result and result[0] == 'input_state':
                    _, module, state = result
                    logger.debug(f"Input M{module}: {state:016b}")
                    for input_num in range(16):
                        mqtt_bridge.publish_input_state(module, input_num, bool(state & (1 << input_num)))
                
                elif result and result[0] == 'input_activated':
                    _, module, input_num = result
                    logger.info(f"! Input M{module}-I{input_num} activated")
                    mqtt_bridge.publish_input_state(module, input_num, True)
            
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'protocol' in locals():
            protocol.ser.close()
        if 'mqtt_bridge' in locals():
            mqtt_bridge.client.loop_stop()
            mqtt_bridge.client.disconnect()


if __name__ == "__main__":
    main()