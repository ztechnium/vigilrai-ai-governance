# Compatibility

Integration compatibility and version requirements for RAI Control Plane.

## SDK Versions

| SDK | Package | Minimum Python/Node |
|-----|---------|---------------------|
| Python | `rai-control-plane-sdk` | Python 3.10+ |
| TypeScript | `@ztechnium/rai-sdk` | Node.js 18+ |

## API Versioning

The stable integration contract is `/sdk/v1`. Breaking changes require a new major namespace such as `/sdk/v2`. Internal `/v1/*` admin and domain routes can change without that guarantee. Rules and the SDK compatibility range are in [API compatibility](../../operations/API_COMPATIBILITY.md).

## Integration Methods

| Method | Status | Notes |
|--------|--------|-------|
| Python SDK | Available | Recommended for backend agents |
| TypeScript SDK | Available | Recommended for Node.js and browser |
| REST API | Available | Universal fallback |
| Proxy Preview | Preview | Gradual enforcement rollout |
| MCP Hooks | Available | IDE and coding agent integration |

## Browser Support

The admin console supports modern evergreen browsers (Chrome, Firefox, Safari, Edge).

## Backend Requirements

- PostgreSQL database
- Redis (optional, for caching in production deployments)
- Environment variables for auth, database, and provider configuration

See `DEVELOPMENT.md` in the repository root for local development setup.
