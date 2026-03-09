# **PulsarM: Heat Meter Specification**

Module Type: Apartment Heat Meter (Ultrasonic/Mechanical)  
Protocol: PulsarM (Extension)

## **1\. Archives Support**

The device supports the following archive types (Function 0x06):

* **Hourly:** Depth \~62 days (1488 records).  
* **Daily:** Depth \~6 months (184 records).  
* **Monthly:** Depth \~5 years (60 records).

## **2\. Channels Table (Read via 0x01, Write via 0x02)**

The data format for most channels is **FLOAT32** (IEEE 754).

| Channel | Name | Access | Format | Description |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **Volume (Supply)** | R/W | FLOAT | Accumulated volume in supply pipe ($m^3$). |
| **2** | **Volume (Return)** | R/W | FLOAT | Accumulated volume in return/reverse pipe ($m^3$). |
| **3** | **Temp (Supply)** | R | FLOAT | Temperature in supply pipe (°C). |
| **4** | **Temp (Return)** | R | FLOAT | Temperature in return pipe (°C). |
| **5** | **Energy (Heat)** | R/W | FLOAT | Accumulated Heat Energy (Gcal/MWh). |
| **6** | **Energy (Cooling)** | R/W | FLOAT | Accumulated Cooling Energy (if supported). |
| **7** | **Operation Time** | R/W | UINT32 | Normal operation time (Hours). |
| **8** | **Pulse Input 1** | R/W | FLOAT | Accumulated value from Pulse Input 1 ($m^3$). |
| **9** | **Pulse Input 2** | R/W | FLOAT | Accumulated value from Pulse Input 2 ($m^3$). |
| **10** | **Pulse Input 3** | R/W | FLOAT | Accumulated value from Pulse Input 3 ($m^3$). |
| **11** | **Pulse Input 4** | R/W | FLOAT | Accumulated value from Pulse Input 4 ($m^3$). |
| **12** | **Pressure (Supply)** | R | FLOAT | Pressure in supply pipe (MPa/Bar). |
| **13** | **Pressure (Return)** | R | FLOAT | Pressure in return pipe (MPa/Bar). |

## **3\. Parameters Table (Read via 0x0A, Write via 0x0B)**

| Index (Hex) | Parameter Name | Access | Format | Description |
| :---- | :---- | :---- | :---- | :---- |
| **0x0000** | **Device ID** | R | UINT16 | Unique Device Identifier. |
| **0x0001** | **Network Address** | R/W | UINT32 | Logical address \[1...99999999\]. |
| **0x0002** | **FW Version** | R | UINT64 | Standard version structure (see Protocol Spec). |
| **0x0005** | **Factory Number** | R | STRING | Serial number (ASCII/BCD). |
| **0x0007** | **Current Errors** | R | UINT32 | Bitmask of current errors (see Section 4). |
| **0x0012** | **Operating Time** | R | UINT32 | Total hours of operation. |
| **0x0020** | **Pulse Out 1 Mode** | R/W | UINT8 | Configuration for Output 1\. |
| **0x0040** | **Battery Voltage** | R | UINT16 | Voltage in mV (e.g., 3600 \= 3.6V). |
| **0x0041** | **Pulse Out Weight** | R/W | FLOAT | Volume per pulse output ($m^3$/imp). |
| **0x000C** | **Pulse In 1 Weight** | R/W | FLOAT | Volume per pulse input 1 ($m^3$/imp). |
| **0x000D** | **Pulse In 1 Initial** | R/W | FLOAT | Initial offset for Input 1\. |
| **0x0100** | **Radio Mode** | R/W | UINT8 | Radio/IoT settings. |
| **0x1100** | **LoRa Device EUI** | R/W | BLOB | 8 bytes LoRaWAN DevEUI. |

## **4\. Error Flags (Parameter 0x0007)**

The "Current Errors" parameter is a 32-bit mask.

| Bit | Name | Description |
| :---- | :---- | :---- |
| **0** | **Reset** | Device reset occurred. |
| **1** | **Memory Error** | Internal EEPROM/Flash failure. |
| **2** | **Low Battery** | Battery voltage critical. |
| **3** | **Quartz Error** | RTC crystal failure. |
| **4** | **Transceiver** | Radio module failure. |
| **5** | **Magnetic Tamper** | Strong magnetic field detected. |
| **6** | **Reverse Flow** | Negative flow detected. |
| **7** | **Flow Limit** | Flow rate exceeded max limit. |
| **8** | **HW Error 1** | Frontend/Measurement circuit failure. |
| **9** | **HW Error 2** | Controller hardware failure. |
| **10** | **Flow Sensor** | Ultrasonic/Mechanical sensor error. |
| **11** | **Temp Supply** | Supply temperature sensor break/short. |
| **12** | **Temp Return** | Return temperature sensor break/short. |
| **13** | **Low dT** | Temp difference below minimum threshold. |
| **14** | **Pressure 1** | Supply pressure sensor error (if installed). |
| **15** | **Pressure 2** | Return pressure sensor error (if installed). |

