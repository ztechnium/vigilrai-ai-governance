# Contributing to @ztechnium/rai-sdk

> **DO NOT EDIT HERE.** Authoritative repository:
> [github.com/ztechnium/rai-typescript-sdk](https://github.com/ztechnium/rai-typescript-sdk)

Thank you for helping improve the RAI TypeScript SDK.

## Development Setup

```bash
git clone https://github.com/ztechnium/rai-typescript-sdk.git
cd rai-typescript-sdk
npm install
npm test
```

## Making Changes

1. Fork the public repository and create a feature branch.
2. Keep changes focused on the public `/sdk/v1` client contract.
3. Add or update tests in `tests/` for behavior changes.
4. Run `npm test` before opening a pull request.
5. Update `CHANGELOG.md` for user-visible changes.

## Pull Request Checklist

- [ ] `npm run build` succeeds
- [ ] `npm test` passes
- [ ] `npm pack --dry-run` includes only intended files
- [ ] Public exports remain stable or breaking changes are documented

## Release Process

Releases are automated from tags matching `v*` on `ztechnium/rai-typescript-sdk`
via `.github/workflows/publish.yml`.

Do not publish manually unless responding to an incident.
