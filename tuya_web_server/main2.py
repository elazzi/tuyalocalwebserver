
import tinytuya
import json
import logging
import time
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# --- Device Credentials ---
# Replace with your actual gateway and sub-device credentials
GATEWAY_DEVICE_ID = "bfdf798d4baae73d21oarx"  #bfdf798d4baae73d21oarx"
GATEWAY_IP_ADDRESS = "192.168.50.185"  # Or 'Auto' to scan
GATEWAY_LOCAL_KEY = "&`8j%*u>LYiAlT~$"
ZIGBEE_dev_ID = "bfa68b9b7fb66b6e492rot" # This is the 'cid' or 'node_id'
ZIGBEE_dev_nodeID = "a4c1388fba5285d7"

# 1. Instantiate the gateway 'Device' object (parent)
# This object handles the encrypted TCP connection to the gateway.
# persist=True maintains a persistent connection for receiving asynchronous updates.
gateway = tinytuya.Device(
    dev_id=GATEWAY_DEVICE_ID,
    address=GATEWAY_IP_ADDRESS,
    local_key=GATEWAY_LOCAL_KEY,
    persist=True,
    version=3.4
)

status_data = gateway.status()
#print(json.dumps(status_data, indent=4))
# 2. Instantiate the sub-device 'Device' object (child)
# This object represents the Zigbee switch. It is linked to the gateway via the 'parent' parameter.
# All commands to 'switch' will be proxied through the 'gateway' connection.
switch = tinytuya.Device(
    dev_id=ZIGBEE_dev_ID,
    cid=ZIGBEE_dev_nodeID,
    parent=gateway
)

# 3. Request the current status of the sub-device
# The status() command is sent to the gateway, which then polls the Zigbee device.
print("Requesting status for Zigbee switch...")
status_data = switch.status()
# Wait a moment for the async response to be fully processed
time.sleep(1)
# 4. Print and interpret the response
# The response contains a 'dps' dictionary with the state of all Data Points.
print("\nReceived status data:")
print(status_data)
if not (status_data and isinstance(status_data, dict) and 'dps' in status_data):
    print("\nFailed to get a valid status from device.")
    exit(0)
dps = status_data['dps']
print("Data Points (dps):")
for key, value in dps.items():
        print(f"  DPS {key}: {value}")
    # Example interpretation for a switch
if '1' in dps:
        switch_state = "ON" if dps['1'] else "OFF"
        print(f"\nZigbee Switch is currently: {switch_state}")