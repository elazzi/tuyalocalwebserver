
import tinytuya
import json
import logging
import time
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# --- Device Credentials ---
# Replace with your actual gateway and sub-device credentials
GATEWAY_DEVICE_ID = "bf9bac91e4180222c4sjjv"  #bfdf798d4baae73d21oarx"
GATEWAY_IP_ADDRESS = "192.168.50.214"  # Or 'Auto' to scan
GATEWAY_LOCAL_KEY = "ZI>n6#I0VW*Xk'X?"
ZIGBEE_dev_ID = "bf56352539f0a279dcs16n" # This is the 'cid' or 'node_id'
ZIGBEE_dev_nodeID = "068f30ed807c5451"

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

sub_devices_result = gateway.subdev_query()
data_field = sub_devices_result.get('data')

            # 'data_field' will now be {'online': [...], 'offline': [...]}
print(data_field)
            # Ensure sub_devices is a dictionary
online_devices = data_field.get('online', [])
offline_devices = data_field.get('offline', [])
print("Online sub-devices:", online_devices)
print("Offline sub-devices:", offline_devices)
sub_devices =data_field
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