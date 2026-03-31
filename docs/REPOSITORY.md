# Repository Notes

## Status

This repository is maintained as a private project.

It is optimized for:

- personal use
- self-hosting
- low operational overhead
- direct pragmatic iteration

## Expected Workflow

- use Conventional Commits
- keep `CHANGELOG.md` updated
- prefer small, understandable changes
- treat Docker Compose as the main local runtime path

## Suggested Release Flow

1. make code and documentation changes
2. verify with `./scripts/manage.sh check`
3. build with `./scripts/manage.sh build`
4. update `CHANGELOG.md`
5. create a commit with a Conventional Commit message
6. optionally tag a release later if needed
