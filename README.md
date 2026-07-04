# PROJECT HELL

Welcome to **PROJECT HELL**, a comprehensive and advanced algorithmic trading and data bridge architecture.

## Overview
Project Hell is an interconnected suite of services designed for automated, high-performance trading operations. It seamlessly bridges real-time trading data, manages low-latency execution layers, handles strategic decision-making, and maintains strict overarching risk monitoring.

## System Architecture & Modules

The platform is divided into four main architectural pillars and a dedicated data bridge layer:

### 1. **Nova** (Execution & Order Routing)
Nova acts as the core execution engine of the project. It interfaces directly with market endpoints to ensure sub-millisecond execution times and handles connection stability, retries, and fallback protocols during volatile market conditions.
- **Key Validation**: `test_nova_connection.py`

### 2. **Nexus** (Central Data Hub & Routing)
Nexus serves as the central circulatory system. It receives normalized market data from various bridges and efficiently routes it to the necessary analytical and execution components without bottlenecking the system.

### 3. **Prophet** (Predictive Analytics & Strategy)
Prophet is the brain of the trading system. It utilizes quantitative models and algorithmic strategies to analyze incoming tick data, spot market inefficiencies, and generate actionable trading signals in real-time.

### 4. **Overseer** (Monitoring & Risk Management)
The Overseer module operates as the safety net and risk controller. It continuously monitors open positions, calculates risk metrics (like drawdown and exposure) on-the-fly, and is capable of automatically halting trading activities if strict, pre-defined risk thresholds are breached.

### 5. **Rithmic Data Bridge**
A high-throughput adapter specifically designed to interface seamlessly with the Rithmic API. It translates proprietary market feeds into standard formats consumed by the Nexus hub.
- **Key Scripts**: `rithmic_data_bridge.py`, `rithmic_data_bridge_v2.py`, `START_DATA_BRIDGE.bat`

## Testing and Validation
The repository comes equipped with a comprehensive suite of testing scripts to ensure all modules are functioning correctly before any live deployment.
- **Connectivity**: `test_connectivity.py`
- **Data Feeds**: `test_rithmic.py`, `test_rithmic_live.py`
- **Simulation**: `test_paper_trading.py` (Simulated execution testing)
- **Endpoint Diagnostics**: `test_correct_endpoint.py`, `test_correct_endpoint_final.py`
- **Post-Support Verification**: `quick_test_after_support.py`

## Documentation Reference
In-depth documentation is available in the root directory for specific subsystem insights:
- `MASTER.md` & `MASTER_ALL.md`: High-level architectural blueprints and overarching system logic.
- `MASTER_DOCUMENTATION.md`: Exhaustive details covering API endpoints, message structures, and latency optimization techniques.
- `MASTER_RITHMIC.md`: Dedicated guide to handling the intricacies and specific configurations of the Rithmic data feed.
- `RITHMIC_RESOLUTION_PLAN.md` & `EDGE_CLEAR_SUPPORT_REQUEST.md`: Troubleshooting paths, resolution steps, and external support references.
- `SUPPORT_CALL_QUICK_REFERENCE.md`: Quick reference guide for handling support inquiries.

## Getting Started

1. **Environment Setup**
   Ensure you have the required Python environment variables configured and dependencies installed.
2. **Launch Data Bridge**
   Execute `START_DATA_BRIDGE.bat` to initialize the data feed and establish the connection to Rithmic.
3. **Verify Connections**
   Run the test scripts (e.g., `python test_connectivity.py` and `python test_nova_connection.py`) to confirm all internal modules are successfully communicating.
4. **Initiate Core Systems**
   Once verified, launch the main `demo.py` or the respective subsystem entry points.

## Disclaimer & Caution
*Project Hell* is designed for aggressive performance. Always ensure the risk management protocols within the **Overseer** module are active and rigorously tested via paper trading before any live market deployments to mitigate unintended market exposure.
