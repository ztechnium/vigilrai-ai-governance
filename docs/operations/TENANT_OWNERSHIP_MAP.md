# Instance data model

This community edition has one organization. There is no `organizations` table and no `organization_id` column.

People, departments, and governance roles live on the instance:

- `organization_memberships` assigns a user to a governance role
- `departments` is a single directory
- `organization_governance_profiles` stores one company profile (`singleton_key = default`)

Product APIs authorize the caller from those memberships. They do not accept `X-Organization-ID`.
