---
title: Release
summary: Tag a version and let the release workflow publish the notes from CHANGELOG.md.
order: 20
audience: maintainers
status: draft
---

1. Add a `## <version>` section to `CHANGELOG.md` and set `version` in `custom_components/bscpylgtv/manifest.json` to the same value.
2. Push a tag named `<version>` or `v<version>`.
3. The workflow `.github/workflows/release.yaml` copies the matching `CHANGELOG.md` section into the release body and attaches `manifest.json`. Without a matching section it generates notes. A tag with a hyphen, such as `2.1.1-beta.1`, publishes a pre-release.

The HACS and hassfest workflows validate the repository on push.

:::see-also
- [[develop/build-and-test]]
:::
