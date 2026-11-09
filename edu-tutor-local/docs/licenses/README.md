# Included UI notices

These files are byte-for-byte copies of LICENSE files in the locally installed packages used by the prebuilt browser UI or its generated support code. No network lookup or package update was performed for this collection.

`license-inventory.json` records the installed version, declared package license, exact source path and SHA256 of every copied file. The source paths refer to the development checkout; `node_modules` is deliberately excluded from the source release. The copies here remain available in the release through the `docs` allowlist.

React/React DOM/Scheduler and Lucide appear in the generated bundle's retained license headers. KaTeX is imported by the classroom renderer and includes its distributed styles/fonts. The generated lesson validator imports Ajv's `ucs2length` helper. Vite produces the UI and its module-preload support; its full installed LICENSE is preserved, including its own dependency notices, without claiming those build dependencies are all bundled in this application.

This is a bounded notice inventory for the shipped UI. It is not an inventory of redistributed Python wheels, CUDA libraries, pretrained weights, user uploads, or external character assets; those are not included in the source release. See [the main third-party notices](../../THIRD_PARTY_NOTICES.md) and [the project avatar declaration](PROJECT_AVATAR.md).
