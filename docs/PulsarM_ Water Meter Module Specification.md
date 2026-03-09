# **Pulsar Water Meters: Protocol and Memory Map Documentation**

> Source archive: [link](https://pulsarm.ru/upload/iblock/757/757dbb4ee02863dc7963b89129f34ca5.zip).

This document provides a detailed technical description of the communication protocol and memory maps for the Pulsar family of water meters. The devices are categorized into **6 distinct types (A-F)** based on their data types and register addressing verified against the provided datasheets.

## **1\. Protocol Overview (All Types)**

- **Communication:** RS485 or Optical Head.
- **Settings:** 9600 baud, 8 Data bits, No Parity, 1 Stop bit (8N1).
- **Packet Structure:**
  - Request: ADDR(4) | FUNC(1) | LEN(1) | DATA(N) | ID(2) | CRC(2)
  - Response: ADDR(4) | FUNC(1) | LEN(1) | DATA(N) | ID(2) | CRC(2)
- **Byte Order:**
  - **Address:** Big Endian (MSB first).
  - **Data Values (Float/Int):** Little Endian (LSB first).
  - **CRC16:** Little Endian (Polynomial 0xA001).

## **2\. Device Classification**

| Type  | Description              | Volume (Ch1) | Battery Reg | Errors Reg | Error Type   |
| :---- | :----------------------- | :----------- | :---------- | :--------- | :----------- |
| **A** | Pulse Modules            | Int32        | 0x0041 (mV) | 0x0007     | Uint16       |
| **B** | Mechanical Meters        | Int32        | 0x000A (V)  | 0x0006     | Uint8        |
| **C** | RS485 Meters             | Float32      | N/A         | N/A        | N/A          |
| **D** | Two-Tariff Meters        | Float32      | 0x000A (mV) | 0x0006     | Uint32       |
| **E** | Electronic (Gen 1\)      | Float32      | 0x0040 (mV) | Ch 8       | Float/Uint32 |
| **F** | Electronic (Gen 2 / V24) | Float32      | 0x0040 (mV) | 0x0007     | Uint16       |

## **3\. Type A: Pulse Modules (IoT/Mini)**

Focus: Digital pulse counting modules for mechanical meters.

### **3.1 Primary Data (Function 0x01)**

- **Channel 1 (Volume):** Returns **Int32** (4 bytes).

### **3.2 Diagnostics (Function 0x0A)**

- **Map:** Modern IoT/Mini.

| Param Addr | Description      | Type   | Unit    | Notes             |
| :--------- | :--------------- | :----- | :------ | :---------------- |
| **0x0041** | Battery Voltage  | Uint16 | mV      | e.g. 3600 \= 3.6V |
| **0x0040** | Temperature      | Int8   | °C      | Range \-100..+100 |
| **0x0007** | Current Errors   | Uint16 | Bitmask | See **Table A**   |
| **0x000E** | Last Packet RSSI | Int8   | dBm     |                   |
| **0x0049** | Last RF Error    | Uint8  | Code    | 0 \= OK           |

## **4\. Type B: Mechanical Meters (Pulsar M)**

Focus: Meters with integrated mechanical counting and digital output.

### **4.1 Primary Data (Function 0x01)**

- **Channel 1 (Volume):** Returns **Int32** (SINT32).

### **4.2 Diagnostics (Function 0x0A)**

_Note: Data types differ from modern modules._

| Param Addr | Description      | Type    | Unit    | Notes           |
| :--------- | :--------------- | :------ | :------ | :-------------- |
| **0x000A** | Battery Voltage  | Float32 | V       | e.g. 3.65       |
| **0x000B** | Temperature      | Float32 | °C      |                 |
| **0x0006** | Error Flags      | Uint8   | Bitmask | See **Table B** |
| **0x0001** | Daylight Saving  | Uint16  | \-      | 0=Off, 1=On     |
| **0x0005** | Firmware Version | Uint16  | \-      |                 |

## **5\. Type C: RS485 Meters**

Focus: Meters specifically designed for RS485 communication.

### **5.1 Primary Data (Function 0x01)**

- **Channel 1 (Volume):** Returns **Float32**.

### **5.2 Diagnostics (Function 0x0A)**

- **Map:** Limited.
- _Battery/Temp registers are not available in standard protocol._
- **0x001C:** Protective Reed Switch (Uint8).

## **6\. Type D: Two-Tariff Meters**

Focus: Meters capable of tracking separate registers (e.g., based on temperature).

### **6.1 Primary Data (Function 0x01)**

All channels are **Float32**.

- Ch 3: Temp, Ch 6: Vol Total, Ch 7: Vol Cold, Ch 8: Vol Hot.
  (Note: Channel mapping may vary by firmware version; check Ch 10/20/29 for auxiliary data).

### **6.2 Diagnostics (Function 0x0A)**

- **Map:** Hybrid.

| Param Addr | Description     | Type   | Unit    | Notes           |
| :--------- | :-------------- | :----- | :------ | :-------------- |
| **0x000A** | Battery Voltage | Uint16 | mV      |                 |
| **0x000B** | Temperature     | Uint8  | °C      |                 |
| **0x0008** | Device Status   | Uint8  | Bitmask |                 |
| **0x0006** | Error Flags     | Uint32 | Bitmask | See **Table D** |

## **7\. Type E: Electronic Meters (Gen 1\)**

Focus: Ultrasonic or electronic meters using the Generalized Protocol.

### **7.1 Primary Data (Function 0x01)**

- **Channel 1:** Volume Forward (**Float32**).
- **Channel 8:** Error Flags (**Float32** bitmask representation or Uint32 via extended read).

### **7.2 Diagnostics (Function 0x0A)**

| Param Addr | Description     | Type    | Unit |
| :--------- | :-------------- | :------ | :--- |
| **0x0040** | Battery Voltage | Uint16  | mV   |
| **0x0100** | Flow Rate       | Float32 | m³/h |

## **8\. Type F: Electronic Meters (Gen 2 / V24)**

Focus: Electronic meters with V24 protocol.

### **8.1 Primary Data (Function 0x01)**

- **Channel 1:** Volume (**Float32**).
- **Channel 2:** Flow Rate (**Float32**).

### **8.2 Diagnostics (Function 0x0A)**

- **Map:** V24 Electronic.

| Param Addr | Description        | Type     | Unit    | Notes                 |
| :--------- | :----------------- | :------- | :------ | :-------------------- |
| **0x0040** | Battery Voltage    | Uint16   | mV      | Range 1700-4000       |
| **0x0007** | Current Errors     | Uint16   | Bitmask | See **Table F**       |
| **0x0010** | Module Detached    | Uint8/16 | Code    | "Module removal" flag |
| **0x0125** | Flow Threshold Min | Float32  | m³/h    |                       |
| **0x0126** | Flow Threshold Max | Float32  | m³/h    |                       |

## **9\. Error Codes Reference**

### **Table A: Modern Error Mask (Type A) \- Reg 0x0007 (Uint16)**

| Bit | Description        |
| :-- | :----------------- |
| 0   | Reset Occurred     |
| 1   | Low Battery        |
| 2   | EEPROM Error       |
| 3   | Reverse Flow       |
| 4   | Reed Switch Closed |
| 5   | Transceiver Error  |
| 6   | Quartz Failure     |
| 7   | Flash/Cache Error  |

### **Table B: Legacy Error Mask (Type B) \- Reg 0x0006 (Uint8)**

| Bit | Description          |
| :-- | :------------------- |
| 0   | Low Battery          |
| 1   | EEPROM Error         |
| 2   | Reset Occurred       |
| 3   | Quartz Failure       |
| 6   | Reverse Flow         |
| 7   | Reed Switch / Magnet |

### **Table D: Two-Tariff Error Mask (Type D) \- Reg 0x0006 (Uint32)**

| Bit | Description       |
| :-- | :---------------- |
| 0   | Low Battery       |
| 1   | EEPROM Error      |
| 5   | Thermometer Error |
| 16  | Low Flow          |
| 17  | High Flow         |

### **Table F: Electronic V24 Error Mask (Type F) \- Reg 0x0007 (Uint16)**

| Bit | Description                    |
| :-- | :----------------------------- |
| 0   | RAM Reset                      |
| 1   | Low Battery                    |
| 2   | Flash/EEPROM Error             |
| 4   | Reed Switch                    |
| 5   | RF Error                       |
| 6   | Quartz Failure                 |
| 9   | Reverse Flow                   |
| 10  | Low Flow                       |
| 11  | High Flow                      |
| 13  | Inductor 1 Error (Break/Short) |
| 14  | Inductor 2 Error (Break/Short) |
