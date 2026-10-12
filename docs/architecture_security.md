# ProfitGuard AI — Architecture & Security Specification

## 1. Multi-Tenant Isolation & PostgreSQL Row-Level Security (RLS)

ProfitGuard AI implements defense-in-depth tenant isolation across application layers and the database engine.

### Database Role Separation
Production deployments must use two distinct database roles:
1. **Migration / Admin Role (`pg_migrator`)**:
   - DDL privileges (`CREATE`, `ALTER`, `DROP`).
   - Bypasses RLS (`BYPASSRLS`).
   - Used strictly by Alembic migration runners. Never exposed to application runtime.
2. **Runtime Application Role (`pg_app_runtime`)**:
   - DML privileges only (`SELECT`, `INSERT`, `UPDATE`, `DELETE`).
   - Subject to RLS (`NOBYPASSRLS`).
   - Used by FastAPI application instances and Celery worker tasks.

### Transaction-Local Tenant Context
Every database transaction executed by the application or worker sets the active organization ID:

```sql
SELECT set_config('app.current_org_id', :org_id, true);
```

- Parameter `:org_id` is bound as a parameterized UUID.
- Setting is transaction-local (`true`), which guarantees that upon transaction `COMMIT` or `ROLLBACK`, the setting is cleared automatically. This prevents any tenant context leakage across pooled database connections.

### Row-Level Security (RLS) Policies
Tenant-scoped tables (`merchant_economics`, `audit_logs`, and future order tables) enforce PostgreSQL RLS:

```sql
CREATE POLICY tenant_isolation_policy ON <table_name>
    FOR ALL
    TO pg_app_runtime
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
    WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
```

If `app.current_org_id` is unset or empty, PostgreSQL evaluates the expression to `NULL` and denies access by default (returns zero rows).

---

## 2. Cryptographic Architecture: AES-256-GCM Credential Encryption

Sensitive integration credentials (Shopify offline access tokens, communication API keys, webhook signing secrets) are encrypted before persistence using authenticated AES-256-GCM.

### Token Format
```text
v{version}:{12-byte-hex-iv}:{ciphertext-hex}:{16-byte-hex-tag}
```

- **Algorithm**: AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).
- **Initialization Vector**: A fresh, cryptographically secure 12-byte random nonce generated via `os.urandom(12)` for every operation.
- **Tamper Detection**: Verification of the 16-byte Galois authentication tag guarantees ciphertext integrity. Any altered byte in the IV, ciphertext, or tag raises `TamperDetectedException`.
- **Key Rotation**: Versioned keys allow seamless re-encryption from old versions (e.g. `v1`) to the active version (`v2`) without service interruption.

### Operational Risks & Cloud KMS Upgrade Path
- **Current Architecture**: Master keys reside in process environment variables (`ENCRYPTION_KEYS={"v1": "...", "v2": "..."}`).
- **Operational Risk**: If an attacker gains memory-dump or root execution privileges inside the container, active keys can be recovered from process memory.
- **Enterprise Upgrade**: The codebase implements the `ICryptoService` interface. For production compliance, implementations can switch to `AWSKMSCryptoService` or `GCPKMSCryptoService` to use cloud-managed Key Encryption Keys (KEK) and hardware security modules (HSM).

---

## 3. Append-Only Tamper-Evident Audit Logging

Audit logging tracks critical actions (`ORGANIZATION_INITIALIZED`, `ECONOMICS_CONFIG_UPDATED`, `MEMBER_ADDED`, `MEMBER_ROLE_UPDATED`).

### Cryptographic Chaining
Each audit entry computes a deterministic SHA-256 digest:
$$\text{hash}_k = \text{SHA256}(\text{hash}_{k-1} \,||\, \text{org\_id} \,||\, \text{sequence\_number} \,||\, \text{actor\_id} \,||\, \text{action} \,||\, \text{resource\_type} \,||\, \text{resource\_id} \,||\, \text{canonical\_payload} \,||\, \text{timestamp})$$

- **Genesis Block**: Each organization's audit log begins with $\text{hash}_0 = \text{"0" * 64}$.
- **Canonical Serialization**: JSON payloads are formatted with sorted keys (`sort_keys=True`), compact separators (`,`, `:`), and second-precision UTC timestamps (`%Y-%m-%dT%H:%M:%SZ`).
- **Concurrency Safety**: To prevent chain forking under concurrent requests, writes are serialized per-tenant using a transaction-scoped PostgreSQL advisory lock:
  ```sql
  SELECT pg_advisory_xact_lock(hashtext('audit_lock_' || :org_id::text));
  ```
- **Tamper-Evidence vs. Tamper-Proof**: Modifying any historical row breaks the hash verification chain for all subsequent entries (`AuditService.verify_chain`). It is tamper-evident, but **not tamper-proof** against database superusers with raw table write access.

---

## 4. Role-Based Access Control (RBAC) Matrix

| Permission / Action | OWNER | ADMIN | OPERATOR | AUDITOR |
| :--- | :---: | :---: | :---: | :---: |
| View Organization & Members | Yes | Yes | Yes | Yes |
| View Merchant Economics | Yes | Yes | Yes | Yes |
| View Audit Logs & Verify Chain | Yes | Yes | Yes | Yes |
| Update Merchant Economics | Yes | Yes | No | No |
| Invite Members (Operator/Auditor) | Yes | Yes | No | No |
| Modify Member Roles | Yes | No | No | No |
| Transfer Organization Ownership | Yes | No | No | No |
