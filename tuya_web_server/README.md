# Tuya Local Control Web Server

This project provides a web interface to control Tuya devices on your local network without relying on cloud services.

## Features

*   Discover Tuya devices on your local network.
*   Add devices manually using their IP address, device ID, and local key.
*   View the status and metrics of your configured devices.

## Setup

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Get Local Keys:**
    To control your Tuya devices, you need to obtain the `local_key` for each one. You can do this using the `tinytuya` library's wizard:
    *   Follow the instructions on the [tinytuya GitHub page](https://github.com/jasonacox/tinytuya#setup-wizard---getting-local-keys) to set up a Tuya IoT developer account and link your Smart Life app.
    *   Run the wizard from your terminal:
        ```bash
        python -m tinytuya wizard
        ```
    *   This will create a `devices.json` file containing the `local_key` for each of your devices. You'll need to copy these keys into the web interface.

## Running the Server

1.  **Start the Server:**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```

2.  **Access the Web Interface:**
    Open your web browser and navigate to `http://localhost:8000`.

## Usage

*   **Discover Devices:** Click the "Discover Devices" button to scan your network for Tuya devices.
*   **Add a Device:** Manually add a device by entering its IP address, device ID, and the local key you obtained from the `tinytuya` wizard.
*   **View Device Status:** Once a device is added, you can click the "Get Status" button to view its current metrics.
