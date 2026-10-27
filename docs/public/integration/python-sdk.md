# Python SDK

Install and use the RAI Control Plane Python SDK for runtime governance.

## Installation

```bash
pip install rai-control-plane-sdk
```

## Configuration

```python
import os
from rai_control_plane import RAIClient

client = RAIClient(
    base_url=os.environ["RAI_BASE_URL"],
    credential=os.environ["RAI_CREDENTIAL"],
)
```

## Authorize Before Acting

Always call `authorize` before performing a consequential action:

```python
result = client.authorize(
    tool_name="update_crm",
    parameters={
        "record_id": "deal-123",
        "field": "stage",
        "value": "closed_won",
    },
)

if result.decision == "allow":
    client.execute(tool_name="update_crm", parameters={...})
elif result.decision == "require_approval":
    print(f"Pending approval: {result.approval_request_id}")
else:
    print(f"Denied: {result.reason}")
```

## Admin operations

Registry and policy management use a Bearer token from `POST /v1/auth/login`. Sign in as the bootstrap admin or as a teammate invited on this instance.

## GitHub

Source and examples: [rai-control-plane-sdk-python](https://github.com/ztechnium/rai-control-plane-sdk-python)
