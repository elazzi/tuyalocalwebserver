import tinytuya
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import logging
from typing import Any, Optional

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get the directory of the current script
script_dir = os.path.dirname(__file__)

# File paths
DEVICES_FILE = os.path.join(script_dir, "devices.json")
DEVICESw_FILE = os.path.join(script_dir, "devicesw.json")
ZIGBEE_DEVICES_FILE = os.path.join(script_dir, "zigbee_devices.json")
TUYA_RAW_FILE = os.path.join(script_dir, "devices.json")

# In-memory storage for configured devices
devices = {}
zigbee_devices = {}

def load_zigbee_devices():
    """Load zigbee devices from file, ensuring it's a dictionary."""
    global zigbee_devices
    try:
        with open(ZIGBEE_DEVICES_FILE, "r") as f:
            loaded_data = json.load(f)
            if isinstance(loaded_data, dict):
                zigbee_devices = loaded_data
            else:
                zigbee_devices = {}
    except (FileNotFoundError, json.JSONDecodeError):
        zigbee_devices = {}

def load_configured_devices():
    """Load devices from file, ensuring it's a dictionary."""
    global devices
    try:
        with open(DEVICESw_FILE, "r") as f:
            loaded_data = json.load(f)
            if isinstance(loaded_data, dict):
                devices = loaded_data
            else:
                devices = {}
    except (FileNotFoundError, json.JSONDecodeError):
        devices = {}

load_configured_devices()
load_zigbee_devices()

class DiscoveredDevice(BaseModel):
    device_id: str
    ip: str

class DeviceViaGateway(BaseModel):
    device_id: str
    name: str
    gateway_id: str

class ControlAction(BaseModel):
    command: str
    dp_index: Optional[int] = None
    value: Optional[Any] = None

class DefaultFeatures(BaseModel):
    features: list[str]

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(script_dir, 'index.html'))

@app.post("/api/discover")
async def discover_devices():
    """Discover Tuya devices on the local network and list all potential devices."""
    try:
        # Scan the network for active Tuya devices
        scanned_devices = tinytuya.deviceScan(False, 2)
        scanned_ids = {dev.get('gwId') for dev in scanned_devices.values()}

        # Load all potential devices from the local file
        try:
            with open(TUYA_RAW_FILE, "r") as f:
                tuya_raw_data = json.load(f)
                # Ensure tuya_raw_data is a list of devices
                if isinstance(tuya_raw_data, dict) and 'devices' in tuya_raw_data:
                    tuya_raw_data = tuya_raw_data['devices']
                elif not isinstance(tuya_raw_data, list):
                    tuya_raw_data = list(tuya_raw_data.values())

        except (FileNotFoundError, json.JSONDecodeError):
            tuya_raw_data = []

        all_devices = {}
        # First, process devices found by the scan
        for device_id, device_info in scanned_devices.items():
            mac = device_info.get('gwId', '')
            raw_device_details = next((d for d in tuya_raw_data if d.get('id') == mac), {})

            all_devices[mac] = {
                "id": mac,
                "ip": device_info.get('ip', ''),
                "has_ip": True, # Explicitly mark as having an IP
                "version": device_info.get('version', ''),
                "product_id": device_info.get('productKey', ''),
                "mac": mac,
                "name": raw_device_details.get('name', 'Unknown'),
                "product_name": raw_device_details.get('product_name', 'Unknown'),
                "mapping": raw_device_details.get('mapping', {}),
                "configured": mac in devices or mac in zigbee_devices,
                "is_zigbee": mac in zigbee_devices
            }

        # Second, add devices from the file that were not found in the scan
        for device in tuya_raw_data:
            device_id = device.get('id')
            if device_id and device_id not in scanned_ids:
                # This device is in our list but wasn't found on the network
                all_devices[device_id] = {
                    "id": device_id,
                    "ip": None, # No IP as it wasn't discovered
                    "has_ip": False, # Explicitly mark as not having an IP
                    "version": device.get('version', ''),
                    "product_id": device.get('productKey', ''),
                    "mac": device_id,
                    "name": device.get('name', 'Unknown'),
                    "product_name": device.get('product_name', 'Unknown'),
                    "mapping": device.get('mapping', {}),
                    "configured": device_id in devices or device_id in zigbee_devices,
                    "is_zigbee": device_id in zigbee_devices
                }

        return {"devices": all_devices}
    except Exception as e:
        logger.exception("Error during device discovery")
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")

@app.post("/api/add_device")
async def add_device(device: DiscoveredDevice):
    """Add a device, finding its key and mapping in tuya-raw.json."""
    try:
        with open(TUYA_RAW_FILE, "r") as f:
            tuya_raw_data = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{TUYA_RAW_FILE} not found.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Error reading {TUYA_RAW_FILE}.")

    found_device_data = None
    tuya_devices_list = tuya_raw_data if isinstance(tuya_raw_data, list) else tuya_raw_data.values()
    for dev_data in tuya_devices_list:
        if isinstance(dev_data, dict) and dev_data.get('id') == device.device_id:
            found_device_data = dev_data
            break

    if not found_device_data:
        raise HTTPException(status_code=404, detail=f"Device ID {device.device_id} not found in {TUYA_RAW_FILE}.")

    devices[device.device_id] = {
        "ip": device.ip,
        "device_id": device.device_id,
        "local_key": found_device_data.get('key'),
        "name": found_device_data.get('name'),
        "version": found_device_data.get('version', '3.3'),
        "product_name": found_device_data.get('product_name'),
        "mapping": found_device_data.get('mapping', {}),
        "default_features": []
    }
    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)
    return {"status": "success", "device_id": device.device_id}

@app.post("/api/add_device_via_gateway")
async def add_device_via_gateway(device_data: DeviceViaGateway):
    """Add a new device that is controlled via a gateway."""
    try:
        with open(TUYA_RAW_FILE, "r") as f:
            tuya_raw_data = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{TUYA_RAW_FILE} not found.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Error reading {TUYA_RAW_FILE}.")

    # Find device details from the raw file
    found_device_data = next((d for d in (tuya_raw_data if isinstance(tuya_raw_data, list) else tuya_raw_data.values()) if isinstance(d, dict) and d.get('id') == device_data.device_id), None)

    if not found_device_data:
        raise HTTPException(status_code=404, detail=f"Device ID {device_data.device_id} not found in {TUYA_RAW_FILE}.")
    if device_data.gateway_id not in devices:
         raise HTTPException(status_code=404, detail=f"Gateway device ID {device_data.gateway_id} not configured.")

    # Add the new device to the configured devices list
    devices[device_data.device_id] = {
        "ip": None, # It doesn't have a direct IP
        "device_id": device_data.device_id,
        "local_key": found_device_data.get('key'), # Sub-devices might have their own key
        "name": device_data.name,
        "version": found_device_data.get('version', '3.3'),
        "product_name": found_device_data.get('product_name'),
        "mapping": found_device_data.get('mapping', {}),
        "gateway_id": device_data.gateway_id, # Link to the gateway
        "default_features": []
    }

    # Save back to the devices file
    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)

    return {"status": "success", "device_id": device_data.device_id}

@app.post("/api/devices/{device_id}/set_default_features")
async def set_default_features(device_id: str, features: DefaultFeatures):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    devices[device_id]['default_features'] = features.features

    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)

    return {"status": "success", "device_id": device_id, "default_features": features.features}

@app.get("/api/devices")
async def get_devices():
    """Get the list of configured devices."""
    return devices

@app.post("/api/devices/{device_id}/control")
async def control_device(device_id: str, action: ControlAction):
    """Send a control command to a specific device, handling direct and gateway-based connections."""
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    device_info = devices[device_id]
    gateway_id = device_info.get('gateway_id')

    try:
        target_device = None
        if gateway_id:
            # This is a sub-device, requires gateway connection
            if gateway_id not in devices:
                raise HTTPException(status_code=404, detail=f"Gateway device {gateway_id} not found.")

            gateway_info = devices[gateway_id]
            gateway_device = tinytuya.Device(
                dev_id=gateway_info['device_id'],
                address=gateway_info['ip'],
                local_key=gateway_info['local_key'],
                persist=True,
                version=float(gateway_info.get('version', 3.3))
            )
            # The 'target_device' is the sub-device, linked to the gateway
            target_device = tinytuya.Device(dev_id=device_info['device_id'], parent=gateway_device)
        else:
            # This is a direct-connected (IP) device
            if not device_info.get('ip') or not device_info.get('local_key'):
                 raise HTTPException(status_code=500, detail="Device configuration missing IP or local key.")
            target_device = tinytuya.OutletDevice(
                dev_id=device_info['device_id'],
                address=device_info['ip'],
                local_key=device_info['local_key']
            )
            target_device.set_version(float(device_info.get('version', 3.3)))
            target_device.set_socketPersistent(False)

        logger.debug(f"Executing command '{action.command}' on device {device_id} with payload: {action.model_dump()}")

        # Execute the command
        if action.command == "turn_on":
            target_device.turn_on(switch=action.dp_index or 1)
        elif action.command == "turn_off":
            target_device.turn_off(switch=action.dp_index or 1)
        elif action.command == "set_value":
            if action.dp_index is None or action.value is None:
                raise HTTPException(status_code=400, detail="DP index and value are required for set_value.")
            target_device.set_value(action.dp_index, action.value)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported command: {action.command}")

        # After control, fetch the updated status
        new_status = await get_device_status(device_id)
        return new_status

    except Exception as e:
        logger.exception(f"Error controlling device {device_id}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/api/devices/{device_id}/status")
async def get_device_status(device_id: str):
    """Get the status of a specific device, handling direct and gateway-based connections."""
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    device_info = devices[device_id]
    gateway_id = device_info.get('gateway_id')

    try:
        target_device = None
        if gateway_id:
            if gateway_id not in devices:
                raise HTTPException(status_code=404, detail=f"Gateway device {gateway_id} not found.")

            gateway_info = devices[gateway_id]
            gateway_device = tinytuya.Device(
                dev_id=gateway_info['device_id'],
                address=gateway_info['ip'],
                local_key=gateway_info['local_key'],
                persist=True,
                version=float(gateway_info.get('version', 3.3))
            )
            target_device = tinytuya.Device(dev_id=device_info['device_id'], parent=gateway_device)
        else:
            if not device_info.get('ip') or not device_info.get('local_key'):
                 raise HTTPException(status_code=500, detail="Device configuration missing IP or local key.")
            target_device = tinytuya.OutletDevice(
                dev_id=device_info['device_id'],
                address=device_info['ip'],
                local_key=device_info['local_key']
            )
            target_device.set_version(float(device_info.get('version', 3.3)))

        status = target_device.status()
        if not (status and isinstance(status, dict) and 'dps' in status):
            raise Exception("Failed to get a valid status from device.")

        mapping = device_info.get('mapping', {})
        dp_to_code = {int(dp): info['code'] for dp, info in mapping.items() if isinstance(info, dict) and 'code' in info}

        mapped_status = {}
        for dp, value in status['dps'].items():
            dp_int = int(dp)
            code_name = dp_to_code.get(dp_int, str(dp_int))
            dp_info = mapping.get(str(dp_int), {})
            mapped_status[code_name] = {
                "value": value,
                "type": dp_info.get("type", "Unknown"),
                "values": dp_info.get("values", {}),
                "code": code_name
            }

        return {
            "device_info": {
                "id": device_id,
                "name": device_info.get('name', 'Unknown'),
                "mapping": mapping
            },
            "status": mapped_status
        }
    except Exception as e:
        logger.exception(f"Error getting status for device {device_id}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")