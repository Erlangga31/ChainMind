# API quick reference

The local service listens at `http://localhost:8000`; interactive OpenAPI documentation is available at `/docs`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness and configured mode |
| `POST` | `/disruptions` | Analyze a disruption and prepare a pending draft |
| `GET` | `/runs` | List local or DynamoDB-backed analyses |
| `GET` | `/runs/{run_id}` | Retrieve an analysis, comparison, reasoning, and draft |
| `POST` | `/runs/{run_id}/decision` | Approve, reject, or request a vendor revision |

Example disruption:

```json
{
  "title": "Port delay on semiconductor shipment",
  "description": "Extreme weather has delayed the shipment carrying a critical production component.",
  "component_id": "microchip-x",
  "component_name": "Microchip X",
  "delay_days": 5
}
```

The response from `POST /disruptions` contains the `run_id`; use it to read the complete run. A significant disruption gets a `PENDING_APPROVAL` draft. The decision body is one of:

```json
{"decision": "approve", "note": "Expedite approved."}
{"decision": "reject", "note": "Wait for the next shipment."}
{"decision": "revise", "vendor_id": "vendor-c", "note": "Use alternate supplier."}
```

Only `approve` executes the purchase order. `revise` creates a replacement draft that remains pending approval; `reject` never executes. A decision on a non-pending run returns HTTP 409.

Expected failures use a stable JSON envelope with `code`, `message`, and `details`; request validation errors return HTTP 422. Unexpected server errors return a generic message and are logged server-side.

## Local SAP sandbox

Run the separate simulator on port 8100 with:

```powershell
uv run uvicorn sap_sandbox.main:app --app-dir sandbox --host 127.0.0.1 --port 8100 --reload
```

Its interactive API reference is at `http://localhost:8100/docs`. The simulator exposes OData-style
stock and purchase-order resources under `/sap/opu/odata/sap/`, Ariba sourcing under
`/ariba/sourcing/`, Event Mesh publishing under `/event-mesh/publish`, and approval tasks under
`/workflow/tasks`. Supported OData collection options are `$filter` equality, `$select`, and `$top`.
The OAuth token endpoint issues ephemeral demo tokens; it is not an identity service.
