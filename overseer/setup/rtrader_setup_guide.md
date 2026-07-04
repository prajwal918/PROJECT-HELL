# R|Trader Pro Setup Guide

This guide configures the Windows host side for OVERSEER v12. R|Trader Pro remains a manual GUI dependency because credentials, exchange agreements, routing permissions, and Rithmic entitlements must be accepted inside the Rithmic client.

## 1. Install And Login

1. Install R|Trader Pro from the official Rithmic installer provided by your broker or prop account.
2. Launch R|Trader Pro.
3. In the login window, set:
   - Login server: `Rithmic Paper Trading`
   - Username: `YOUR_USERNAME`
   - Password: `YOUR_PASSWORD`
4. If your credentials are live-tier, select the live Rithmic server assigned by your broker instead of paper trading.
5. Click `Login`.

## 2. Enable Plug-ins

1. Open the R|Trader Pro login or settings dialog.
2. Enable the checkbox named `Allow Plug-ins`.
3. Restart R|Trader Pro after enabling plug-ins.
4. Log in again using the same credentials.

## 3. Routing And Market Data

1. Set routing to `Best Route`.
2. Confirm market data entitlement:
   - Minimum required: `Level 2 (DOM)`
   - Preferred: `Level 3` if your Rithmic plan supports MBO/order-by-order depth.
3. Open a DOM for the target futures contract, for example `6E`.
4. Confirm bid and ask depth updates in real time.

## 4. Confirm RAPIPlus.dll

1. Locate the R|Trader Pro installation directory.
2. Confirm `RAPIPlus.dll` exists.
3. Common paths are:
   - `C:\Program Files\Rithmic\RTrader Pro\RAPIPlus.dll`
   - `C:\Program Files (x86)\Rithmic\RTrader Pro\RAPIPlus.dll`
4. Note the exact DLL path for pythonnet or other host bindings:

```text
RAPIPlus.dll path: C:\Program Files\Rithmic\RTrader Pro\RAPIPlus.dll
```

If your installation uses a different path, record it exactly. Do not copy the DLL into the project unless your license permits redistribution.

## 5. Verify Plug-in Activity

1. Open R|Trader Pro.
2. Confirm the connection indicator is green or shows `Connected`.
3. Open the R|Trader log window.
4. Look for plug-in startup or API permission lines such as:

```text
Plug-ins allowed
Rithmic API enabled
Market data connected
```

5. In Quantower, connect using the Rithmic connection configured through the Quantower UI.
6. Load the OVERSEER bridge strategy.
7. Confirm `bridge/bridge.log` receives startup lines and no permission errors.
8. Confirm UDP packets are emitted to `127.0.0.1:65000`.

## 6. Troubleshooting

- If DOM does not update, verify exchange data agreements and Level 2/Level 3 entitlements.
- If the bridge cannot see the symbol, verify the exact Quantower symbol mapping, for example `6E`, `6E M6`, or the active contract name used by your data connection.
- If plug-in errors appear, disable and re-enable `Allow Plug-ins`, then restart R|Trader Pro and Quantower.
- If `RAPIPlus.dll` is missing, reinstall R|Trader Pro from the broker-provided installer.
