# Default avatar provenance

The existing asset manifest identifies the default avatar as `local-tutor-default-v1`, a project-authored SVG component, and declares its asset license as `CC0-1.0`.

- Canonical manifest: [web/src/avatar-manifest.json](../../web/src/avatar-manifest.json).
- Source implementation: the exported `Avatar` component in [web/src/Classroom.tsx](../../web/src/Classroom.tsx).
- Served manifest copy: [web/public/avatar-manifest.json](../../web/public/avatar-manifest.json), copied from the canonical manifest by the existing prebuild script.
- Release manifest copy: [web/dist/avatar-manifest.json](../../web/dist/avatar-manifest.json).

The recorded rights note states that the vector character was made directly in code for this project and does not depict a particular real person. Its simple joint motion and audio RMS mouth motion are described in the manifest; these are not a claim of full character rigging or phoneme synchronization.

This notice preserves the existing asset-specific declaration. It does not assign that license to the whole application, third-party icons or fonts, user-uploaded replacement PNGs, generated educational examples, or pretrained model weights. Replacement assets retain their own provenance and rights requirements.
