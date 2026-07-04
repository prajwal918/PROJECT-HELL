# Rithmic R | API+ SDK Install Notes

Rithmic R | API+ is proprietary. It is not installable through `pip`, `winget`, `npm`, or a public anonymous download.

Official Rithmic pages describe R | API+ as the C++/.NET API path and provide a request flow for the R | API+ Dev Kit:

- Rithmic API documentation: https://www.rithmic.com/documentation
- Rithmic API request/contact: https://www.rithmic.com/api-request

## What To Ask For

Ask Rithmic or your broker for:

```text
R | API+ Dev Kit
RApi.h / RApiPlus.h headers
RApi.lib / RApiPlus.lib import libraries
RApi.dll / RApiPlus.dll / rapiplus.dll runtime DLLs
C++ or C# sample applications
Market By Order / Level 3 / MBO entitlement
Paper Trading API entitlement
```

Also ask whether your current account may use:

```text
R | API+
R | Protocol API
MBO / Level 3 data
Plug-in access through R | Trader Pro
```

## Where To Put The SDK

When you receive the SDK zip, extract it here:

```text
vendor/rithmic/rapi/
```

Expected examples:

```text
vendor/rithmic/rapi/include/RApi.h
vendor/rithmic/rapi/include/RApiPlus.h
vendor/rithmic/rapi/lib/RApiPlus.lib
vendor/rithmic/rapi/bin/rapiplus.dll
vendor/rithmic/rapi/samples/
```

Then run:

```powershell
python tools\check_rapi_sdk.py
```

If the checker returns `"ready": true`, OVERSEER can add a direct RAPI+ market-data client for Level 3/MBO.
