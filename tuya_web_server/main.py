import tinytuya
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import logging
from typing import Any, Optional, Union

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
CLOUD_CONFIG_FILE = os.path.join(script_dir, "cloud_config.json")

# In-memory storage for configured devices
devices = {}
zigbee_devices = {}
IS_SCANNING = False

def get_cloud_api():
    """Get an instance of the Tuya Cloud API."""
    if not os.path.exists(CLOUD_CONFIG_FILE):
        raise HTTPException(status_code=400, detail="Cloud credentials not configured.")
    try:
        with open(CLOUD_CONFIG_FILE, "r") as f:
            config = json.load(f)
        if not all(k in config for k in ["api_key", "api_secret", "api_region"]):
            raise HTTPException(status_code=400, detail="Cloud credentials incomplete.")
        return tinytuya.Cloud(
            apiRegion=config["api_region"],
            apiKey=config["api_key"],
            apiSecret=config["api_secret"]
        )
    except (json.JSONDecodeError, FileNotFoundError):
        raise HTTPException(status_code=500, detail="Could not read cloud configuration.")
    except Exception as e:
        logger.exception("Error instantiating Tuya Cloud API")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Tuya Cloud: {str(e)}")

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
    ip: Optional[str] = None

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

class CloudConfig(BaseModel):
    api_key: str
    api_secret: str
    api_region: str

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(script_dir, 'index.html'))

@app.get("/config")
async def read_config():
    return FileResponse(os.path.join(script_dir, 'config.html'))

@app.post("/api/discover")
async def discover_devices():
    """Discover Tuya devices on the local network and list all potential devices."""
    global IS_SCANNING
    if IS_SCANNING:
        raise HTTPException(status_code=429, detail="A discovery scan is already in progress.")

    IS_SCANNING = True
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
    finally:
        IS_SCANNING = False

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
        "version": found_device_data.get('version', '3.4'),
        "product_name": found_device_data.get('product_name'),
        "mapping": found_device_data.get('mapping', {}),
        "icon": found_device_data.get('icon'),
        "control_method": "cloud" if device.ip is None else "local",
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
        "icon": found_device_data.get('icon'),
        "node_id": found_device_data.get('node_id'),
        "gateway_id": device_data.gateway_id, # Link to the gateway
        "control_method": "local", # Sub-devices are always local via gateway
        "default_features": []
    }

    # Save back to the devices file
    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)

    return {"status": "success", "device_id": device_data.device_id}

class GatewayStatus(BaseModel):
    is_gateway: bool

@app.post("/api/devices/{device_id}/set_gateway")
async def set_gateway_status(device_id: str, status: GatewayStatus):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    devices[device_id]['is_gateway'] = status.is_gateway

    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)

    return {"status": "success", "device_id": device_id, "is_gateway": status.is_gateway}

@app.post("/api/devices/{device_id}/set_default_features")
async def set_default_features(device_id: str, features: DefaultFeatures):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    devices[device_id]['default_features'] = features.features

    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)

    return {"status": "success", "device_id": device_id, "default_features": features.features}

@app.post("/api/cloud/config")
async def save_cloud_config(config: CloudConfig):
    """Save Tuya Cloud API credentials."""
    with open(CLOUD_CONFIG_FILE, "w") as f:
        json.dump(config.model_dump(), f, indent=4)
    return {"status": "success"}

@app.get("/api/cloud/config")
async def get_cloud_config_status():
    """Get the status of Tuya Cloud API credentials."""
    if not os.path.exists(CLOUD_CONFIG_FILE):
        return {"configured": False}
    try:
        with open(CLOUD_CONFIG_FILE, "r") as f:
            config_data = json.load(f)
        return {
            "configured": bool(config_data.get("api_key") and config_data.get("api_secret")),
            "region": config_data.get("api_region")
        }
    except (json.JSONDecodeError, FileNotFoundError):
        return {"configured": False}

@app.post("/api/cloud/import")
async def import_from_cloud():
    """Import devices from Tuya Cloud and overwrite devices.json."""
    if not os.path.exists(CLOUD_CONFIG_FILE):
        raise HTTPException(status_code=400, detail="Cloud credentials not configured.")

    try:
        with open(CLOUD_CONFIG_FILE, "r") as f:
            config = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        raise HTTPException(status_code=500, detail="Could not read cloud configuration.")

    if not all(k in config for k in ["api_key", "api_secret", "api_region"]):
        raise HTTPException(status_code=400, detail="Cloud credentials incomplete.")

    try:
        cloud = tinytuya.Cloud(
            apiRegion=config["api_region"],
            apiKey=config["api_key"],
            apiSecret=config["api_secret"]
        )
        # getdevices() returns a list of devices, which is what the app expects
        devices_from_cloud = cloud.getdevices()

        with open(TUYA_RAW_FILE, "w") as f:
            json.dump(devices_from_cloud, f, indent=4)

        return {"status": "success", "device_count": len(devices_from_cloud)}
    except Exception as e:
        logger.exception("Error importing from Tuya Cloud")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during cloud import: {str(e)}")

@app.get("/api/devices")
async def get_devices():
    """Get the list of configured devices."""
    return devices

@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    """Remove a configured device."""
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    del devices[device_id]

    with open(DEVICESw_FILE, "w") as f:
        json.dump(devices, f, indent=4)

    return {"status": "success", "removed_device_id": device_id}

@app.post("/api/devices/{device_id}/control")
async def control_device(device_id: str, action: ControlAction):
    """Send a control command to a specific device, handling both local and cloud control."""
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    device_info = devices[device_id]
    control_method = device_info.get("control_method", "local")

    try:
        if control_method == "cloud":
            cloud = get_cloud_api()

            # Find the code for the given dp_index from the mapping
            mapping = device_info.get('mapping', {})
            dp_info = mapping.get(str(action.dp_index))

            if not dp_info or 'code' not in dp_info:
                 raise HTTPException(status_code=400, detail=f"Could not find a code for DP index {action.dp_index} in the device mapping.")

            dp_code = dp_info['code']

            commands = []
            if action.command == "turn_on":
                commands.append({'code': dp_code, 'value': True})
            elif action.command == "turn_off":
                commands.append({'code': dp_code, 'value': False})
            elif action.command == "set_value":
                if action.value is None:
                    raise HTTPException(status_code=400, detail="Value is required for set_value.")
                commands.append({'code': dp_code, 'value': action.value})
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported command: {action.command}")

            logger.debug(f"Executing cloud command on {device_id}: {commands}")
            cloud.sendcommand(device_id, commands)
        else:  # local or gateway
            gateway_id = device_info.get('gateway_id')
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
                gateway_device.set_socketRetryLimit(1)
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
                target_device.set_socketRetryLimit(1)

            logger.debug(f"Executing local command '{action.command}' on device {device_id} with payload: {action.model_dump()}")

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
    """Get the status of a specific device, handling both local and cloud control."""
    if IS_SCANNING:
        raise HTTPException(status_code=429, detail="Scan in progress, status refresh temporarily unavailable.")
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not configured.")

    device_info = devices[device_id]
    control_method = device_info.get("control_method", "local")
    mapping = device_info.get('mapping', {})
    mapped_status = {}
    sub_devices = None
    status_error = None

    try:
        if control_method == "cloud":
            cloud = get_cloud_api()
            cloud_response = cloud.getstatus(device_id)
            cloud_status_list = cloud_response.get('result', [])
            for dp in cloud_status_list:
                code_name = dp['code']
                dp_info = next((info for _, info in mapping.items() if info.get('code') == code_name), {})
                mapped_status[code_name] = {"value": dp['value'], "type": dp_info.get("type", "Unknown"), "values": dp_info.get("values", {}), "code": code_name}
        else:  # local or gateway
            gateway_id = device_info.get('gateway_id')
            target_device = None
            if gateway_id:
                gateway_info = devices.get(gateway_id)
                if not gateway_info: raise HTTPException(status_code=404, detail=f"Gateway device {gateway_id} not found.")
                gateway_device = tinytuya.Device(dev_id=gateway_info['device_id'], address=gateway_info['ip'], local_key=gateway_info['local_key'], persist=True, version=float(gateway_info.get('version', 3.4)))
                gateway_device.set_socketRetryLimit(1)
                target_device = tinytuya.Device(dev_id=device_info['device_id'],cid=device_info['node_id'], parent=gateway_device)
            else:
                if not device_info.get('ip') or not device_info.get('local_key'): raise HTTPException(status_code=500, detail="Device configuration missing IP or local key.")
                target_device = tinytuya.OutletDevice(dev_id=device_info['device_id'], address=device_info['ip'], local_key=device_info['local_key'])
                target_device.set_version(float(device_info.get('version', 3.4)))
                target_device.set_socketRetryLimit(1)

            local_status = target_device.status()
            if not (local_status and isinstance(local_status, dict) and 'dps' in local_status): raise Exception("Failed to get a valid status from local device.")
            status_dps = local_status['dps']
            dp_to_code = {int(dp): info['code'] for dp, info in mapping.items() if isinstance(info, dict) and 'code' in info}
            for dp, value in status_dps.items():
                dp_int = int(dp)
                code_name = dp_to_code.get(dp_int, str(dp_int))
                dp_info = mapping.get(str(dp_int), {})
                mapped_status[code_name] = {"value": value, "type": dp_info.get("type", "Unknown"), "values": dp_info.get("values", {}), "code": code_name}
    except Exception as e:
        status_error = str(e)
        logger.warning(f"Could not get status for {device_id}: {e}")

    # If the device is a gateway, query for sub-devices
    if device_info.get('is_gateway'):
        try:
            gateway_device = tinytuya.Device(dev_id=device_info['device_id'], 
                                             address=device_info['ip'], 
                                             local_key=device_info['local_key'], 
                                             persist=True,
                                             version=3.4)

            gateway_device.set_socketRetryLimit(1)
            sub_devices_result = gateway_device.subdev_query()

            data_field = sub_devices_result.get('data')

            # 'data_field' will now be {'online': [...], 'offline': [...]}
            print(data_field)
            # Ensure sub_devices is a dictionary
            online_devices = data_field.get('online', [])
            offline_devices = data_field.get('offline', [])

            print("Online sub-devices:", online_devices)
            print("Offline sub-devices:", offline_devices)
            sub_devices =data_field
        except Exception as e:
            logger.warning(f"Could not get sub-devices for gateway {device_id}: {e}")
            sub_devices = {"error": f"Failed to get sub-devices: {e}"}

    # If both attempts failed, raise an error
    if status_error and (not sub_devices or "error" in sub_devices):
        raise HTTPException(status_code=500, detail=f"Failed to get status or sub-device list for {device_id}: {status_error}")

    response = {
        "device_info": {"id": device_id, "name": device_info.get('name', 'Unknown'), "mapping": mapping, "is_gateway": device_info.get('is_gateway', False)},
        "status": mapped_status if not status_error else {"error": status_error}
    }
    if sub_devices is not None:
        response["sub_devices"] = sub_devices

    return response