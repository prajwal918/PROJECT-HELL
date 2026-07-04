# RITHMIC CREDENTIALS CONFIGURATION

## Purpose
Direct Rithmic API access for NOVA and AEGIS systems

## Credentials
Stored securely in: `PROJECT HELL\nova\overseer\data\.env.rithmic`

## Environment Variables
```
RITHMIC_USERNAME=asdsadkiarhar6468
RITHMIC_PASSWORD=fd1135d1
RITHMIC_GATEWAY=Rithmic 01
```

## Usage
Update NEXUS backend to connect directly to Rithmic instead of via OVERSEER UDP

## Benefits
- Eliminates OVERSEER dependency for NOVA/AEGIS
- Direct L3 MBO data from Rithmic
- Lower latency
- More reliable data feed