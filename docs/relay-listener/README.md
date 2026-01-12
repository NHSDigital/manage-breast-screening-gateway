# Azure Relay listener

Relay listener uses websocket communication to Manage Breast Screening service via Azure Relay.
The listener processes worklist actions sent from Manage/Django and creates worklist items in the Modality Worklist server.


## Architecture

```
┌─────────────────────┐                           ┌──────────────────────┐
│   Django (Manage)   │                           │  Gateway (Behind FW) │
└─────────────────────┘                           └──────────────────────┘
         │                                                          │
         │ (1) Send Worklist Actions                                │
         │ ────────────────────────────────>                        │
         │   Connection: name-of-your-choice-relay-test-hc          │
         │   Django: SENDER                                         │
         │   Gateway: LISTENER (relay-listener)                     │
         │                                                          │
```


## Firewall Compatibility

Connection works through firewalls because:

- All communication uses **outbound HTTPS (port 443)**
- "Listening" means maintaining a persistent outbound WebSocket connection
- Azure Relay pushes messages down existing connections
- No inbound ports required on the gateway

## Setup Instructions

### 1. Create Azure Relay Resources

In Azure Portal:

1. Create an Azure Relay namespace (if not exists):
   - Name: `manbrs-gateway-dev`
   - Region: UK South

2. Create Hybrid Connection:
   - `name-of-your-choice-relay-test-hc` (for worklist actions)

3. Get the Shared Access Policy:
   - Policy Name: `RootManageSharedAccessKey` (default)
   - Copy the Primary Key

### 2. Copy environment variables from .env.development to .env

#### Gateway (.env or .env.development)

```bash
AZURE_RELAY_NAMESPACE=manbrs-gateway-dev.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=name-of-your-choice-relay-test-hc
AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
AZURE_RELAY_SHARED_ACCESS_KEY=your_actual_key_here
```

#### Django Manage (.env)

```bash
AZURE_RELAY_NAMESPACE=manbrs-gateway-dev.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=name-of-your-choice-relay-test-hc
AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
AZURE_RELAY_SHARED_ACCESS_KEY=your_actual_key_here
```

### 3. Start the Gateway Services


```bash
docker compose up --build
```


## Message Flows

### Worklist Creation (Django → Gateway)

1. User clicks "Send to Modality" in clinic UI
2. Django creates `GatewayAction` with payload
3. Manage Breast Screening service sends via relay (as sender) to `name-of-your-choice-relay-test-hc`
4. Gateway `src.relay_listener.py` receives (as listener)
5. Gateway creates worklist item in Modality Worklist server storage via `CreateWorklistItem` service class.
6. Gateway sends success/failure response back.


## Testing

1. Start both gateway and Manage/Django services
2. Open clinic UI and send appointment to modality
3. Monitor logs to trace message flow
4. Verify worklist item created in Modality Emulator
