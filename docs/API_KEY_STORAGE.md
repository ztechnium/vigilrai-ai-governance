# API Key Storage Guide

The RAI Control Plane uses **two types of API keys** with different storage strategies:

---

## 1. **Provider API Keys** (External LLM Services)

Keys for OpenAI, Anthropic, Azure, etc. that the gateway uses to call LLM providers.

### 📍 **Where They're Stored**

| Environment | Storage Location | Example |
|-------------|------------------|---------|
| **Local Development** | `.env` file (gitignored) | `LLM_PROVIDER_API_KEY=sk-proj-...` |
| **Docker Compose** | `.env` file → container env vars | Mounted via `docker-compose.yml` |
| **Kubernetes** | Kubernetes Secrets | `kubectl create secret generic llm-keys` |
| **AWS** | AWS Secrets Manager / Systems Manager | Injected at runtime |
| **Azure** | Azure Key Vault | Managed identity access |
| **GCP** | Secret Manager | Service account access |

### 🔒 **Security Best Practices**

```bash
# ❌ NEVER commit to git
.env              # Contains real keys

# ✅ ALWAYS commit template
.env.example      # Placeholder values only
```

**Current `.env` structure**:
```bash
# Provider API Keys (External Services)
LLM_PROVIDER_API_KEY=sk-proj-...           # OpenAI
ANTHROPIC_API_KEY=sk-ant-...               # Anthropic Claude
AZURE_OPENAI_API_KEY=...                   # Azure OpenAI
AWS_REGION=us-east-1                       # Bedrock (uses IAM)
GCP_PROJECT_ID=my-project                  # Vertex AI (uses service account)
OLLAMA_ENDPOINT=http://localhost:11434     # Local Ollama

# Security Keys
JWT_SECRET_KEY=...                         # For session tokens
EVIDENCE_ENCRYPTION_KEY=...                # For encrypted evidence storage
ADMIN_TOKEN=change-me                      # Admin console access
```

### 🚀 **Production Deployment**

**Kubernetes Example**:
```bash
# Create secret
kubectl create secret generic rai-provider-keys \
  --from-literal=openai-key=sk-proj-... \
  --from-literal=anthropic-key=sk-ant-...

# Reference in deployment
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: rai-gateway
        env:
        - name: LLM_PROVIDER_API_KEY
          valueFrom:
            secretKeyRef:
              name: rai-provider-keys
              key: openai-key
```

**AWS Secrets Manager**:
```python
# Runtime injection
import boto3


def get_secret(secret_name):
    client = boto3.client("secretsmanager")
    return client.get_secret_value(SecretId=secret_name)


# In config.py
settings.llm_provider_api_key = get_secret("prod/rai/openai-key")
```

---

## 2. **Client API Keys** (Issued to Systems)

Keys issued to client systems (e.g., `test_system`) for calling `/v1/execute`.

### 📍 **Where They're Stored**

| Component | Storage | Format | Security |
|-----------|---------|--------|----------|
| **Database (`api_keys` table)** | PostgreSQL | **SHA-256 hash only** | ✅ Irreversible |
| **Issued once to client** | Client's secrets manager | Plaintext `RoqeNmc7...` | Client responsibility |
| **Never stored plaintext** | ❌ Nowhere in RAI Gateway | - | - |

### 🔐 **Database Schema**

```sql
CREATE TABLE api_keys (
    api_key_id UUID PRIMARY KEY,
    key_hash VARCHAR NOT NULL,           -- SHA-256 hash of plaintext key
    system_id VARCHAR NOT NULL,          -- Which system owns this key
    scopes VARCHAR[] NOT NULL,           -- Permissions: ["execute", "admin"]
    status VARCHAR DEFAULT 'active',     -- active, revoked
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP,
    expires_at TIMESTAMP
);
```

**Example stored hash**:
```
key_hash: "a4c8b2e1f7d6e9c3b5a8d7e4f1c9b6e3a2d5c8f1e4b7a9c6e3d2f5a8b1e4c7d9"
```

**Plaintext key** (shown **only once** when issued):
```
api_key: "rai_example_key"
```

### 🔍 **Key Verification Process**

```python
# When client calls /v1/execute
incoming_key = request.headers.get("X-API-Key")  # "RoqeNmc7..."

# Hash the incoming key
key_hash = hashlib.sha256(incoming_key.encode()).hexdigest()

# Look up in database
api_key_record = (
    db.query(ApiKey)
    .filter(ApiKey.key_hash == key_hash, ApiKey.status == "active")
    .first()
)

if not api_key_record:
    raise Unauthorized("Invalid API key")
```

**Security guarantees**:
- ✅ Database breach doesn't expose working keys (hashed)
- ✅ Keys shown **only once** during issuance
- ✅ Revocation instant (status flag)
- ✅ Scoped permissions (execute vs admin)

---

## 3. **Key Rotation Strategy**

### Provider Keys (OpenAI, Claude, etc.)

**Rotation frequency**: Every 90 days

```bash
# Step 1: Generate new key in provider console
# OpenAI: https://platform.openai.com/api-keys

# Step 2: Update .env or secrets manager
LLM_PROVIDER_API_KEY=sk-proj-NEW_KEY

# Step 3: Restart gateway
docker compose restart rai-gateway

# Step 4: Revoke old key in provider console (after validation)
```

### Client API Keys

**Rotation on-demand** (compromise, employee offboarding, expiry):

```bash
# Option 1: Revoke via API
curl -X POST http://localhost:8001/admin/api/api-keys/revoke \
  -H "X-Admin-Token: change-me" \
  -d '{"api_key_id": "67a646c9-..."}'

# Option 2: Direct database update
UPDATE api_keys 
SET status='revoked', revoked_at=NOW() 
WHERE api_key_id='67a646c9-...';

# Issue new key
curl -X POST http://localhost:8001/admin/api/api-keys/issue \
  -H "X-Admin-Token: change-me" \
  -d '{"system_id": "test_system", "scopes": ["execute"]}'
```

---

## 4. **Where Keys Are Used**

### Provider Keys → LLM Calls

```
Client Request
    ↓
[X-API-Key header] → Validated against api_keys table
    ↓
Allowlist check
    ↓
Prompt template loaded
    ↓
[LLM_PROVIDER_API_KEY] → OpenAI/Claude/Bedrock API call
    ↓
Response returned
```

### Architecture Flow

```
┌─────────────────────────────────────────────────────┐
│  Client System                                       │
│  (Stores: Plaintext Client API Key)                 │
└────────────────┬─────────────────────────────────────┘
                 │ X-API-Key: RoqeNmc7...
                 ↓
┌─────────────────────────────────────────────────────┐
│  RAI Gateway                                        │
│  ┌──────────────────────────────────────────────┐  │
│  │ 1. Hash incoming key                         │  │
│  │ 2. Query api_keys table (SHA-256 hashes)     │  │
│  │ 3. Verify scope                              │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ 4. Load LLM_PROVIDER_API_KEY from env        │  │
│  │ 5. Call OpenAI/Anthropic/Bedrock             │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────┐
│  LLM Provider (OpenAI, Anthropic, etc.)             │
│  (Validates: Provider API Key)                      │
└─────────────────────────────────────────────────────┘
```

---

## 5. **Compliance Considerations**

### GDPR / HIPAA / SOC 2

| Requirement | Implementation |
|-------------|----------------|
| **At-rest encryption** | PostgreSQL with encryption enabled |
| **Hashed storage** | SHA-256 for client keys |
| **Access logs** | All key usage logged in `admin_audit` table |
| **Least privilege** | Scoped permissions (execute vs admin) |
| **Key expiry** | Optional `expires_at` timestamp |
| **Revocation** | Instant via status flag |

### Audit Trail

Every key operation is logged:

```sql
SELECT * FROM admin_audit 
WHERE action IN ('api_key.issue', 'api_key.revoke')
ORDER BY created_at DESC;

-- Example output:
trace_id                             | actor      | action          | target
-------------------------------------|------------|-----------------|-------------
6b664ec7-e0a3-485d-a7eb-382f692aefd1 | admin      | api_key.issue   | {"system_id": "test_system"}
...                                  | admin      | api_key.revoke  | {"api_key_id": "..."}
```

---

## 6. **Environment-Specific Storage**

### Development (Your Current Setup)

```bash
# .env file (gitignored)
LLM_PROVIDER_API_KEY=<your-openai-api-key>
```

### Staging

```bash
# Docker secrets
docker secret create openai_key /run/secrets/openai.key
docker service update --secret-add openai_key rai-gateway
```

### Production

**Option 1: Kubernetes Secrets**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: rai-provider-keys
type: Opaque
stringData:
  openai-key: sk-proj-...
  anthropic-key: sk-ant-...
```

**Option 2: AWS Secrets Manager**
```bash
aws secretsmanager create-secret \
  --name prod/rai/openai-key \
  --secret-string sk-proj-...
```

**Option 3: HashiCorp Vault**
```bash
vault kv put secret/rai/providers \
  openai_key=sk-proj-... \
  anthropic_key=sk-ant-...
```

---

## 7. **Quick Reference**

### Issue New Client API Key

```bash
curl -X POST http://localhost:8001/admin/api/api-keys/issue \
  -H "X-Admin-Token: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "system_id": "my_system",
    "scopes": ["execute"]
  }'

# Response (save this - shown only once!)
{
  "api_key": "rai_example_key",
  "api_key_id": "6b664ec7-e0a3-485d-a7eb-382f692aefd1",
  "system_id": "my_system",
  "scopes": ["execute"],
  "note": "Plaintext key is shown only once. Store it securely."
}
```

### List Active Keys

```bash
curl -H "X-Admin-Token: change-me" \
  http://localhost:8001/admin/api/api-keys

# Returns metadata only (no plaintext keys)
```

### Revoke Key

```bash
curl -X POST http://localhost:8001/admin/api/api-keys/revoke \
  -H "X-Admin-Token: change-me" \
  -d '{"api_key_id": "6b664ec7-..."}'
```

---

## Summary

| Type | Stored | Format | Rotation | Access |
|------|--------|--------|----------|--------|
| **Provider Keys** (OpenAI, etc.) | `.env` / Secrets Manager | Plaintext | 90 days | Gateway only |
| **Client API Keys** (Systems) | PostgreSQL `api_keys` | SHA-256 hash | On-demand | Issued once, never retrievable |
| **Admin Token** | `.env` / Secrets Manager | Plaintext | On-demand | Admin console access |
| **Encryption Keys** | `.env` / Secrets Manager | Plaintext | 1 year | Evidence encryption |

**Golden Rules**:
1. ✅ **Never commit `.env`** to git (already gitignored)
2. ✅ **Provider keys** = plaintext in secure env storage
3. ✅ **Client keys** = hashed in database, plaintext shown **once**
4. ✅ **Rotate regularly** (90 days for providers, on-demand for clients)
5. ✅ **Audit everything** (`admin_audit` table tracks all operations)

Your keys are **secure by design**! 🔒
