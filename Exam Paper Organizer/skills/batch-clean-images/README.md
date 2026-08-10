---
name: batch-clean-images
description: Process every raster image in a local folder sequentially by sending each source image and one edit prompt directly to GPT-5.6 image editing, accepting the returned artifact without inspection or validation, backing up every original into a new folder, and replacing each successful source in place under the same name and path. Use for fast batch upscaling, transparent-background conversion, and removal of only handwritten scribbles while preserving printed text, diagram labels, intended linework, and existing Markdown image destinations.
---

# Batch Clean Images

Prioritize speed. Back up the complete source set, then send each image directly to the image-editing model once and replace the source in place with the returned artifact.

## Prepare the backup

1. Resolve the input folder to an absolute path.
2. Recursively enumerate supported raster images and sort them by relative path. Exclude every directory named `original-images-backup-*` from enumeration. Process image-editing calls sequentially; never parallelize them.
3. Create one new backup folder inside the input folder named `original-images-backup-<YYYYMMDD-HHMMSS>`. If that exact name already exists, add the smallest unused numeric suffix.
4. Copy every discovered source image into the backup folder before making any model call. Preserve each relative path, filename, extension, timestamps when practical, and file contents exactly.
5. Treat complete backup creation as a fail-closed gate. If any source cannot be copied, stop before replacing any image and report the failed backup path.

## Edit and replace each image

For each source path captured before backup creation:

1. Call the native image-generation/editing tool exactly once with `referenced_image_paths: [source]`. Do not inspect the source first and do not infer it from recent conversation images.
2. Use this prompt without adding image-specific assumptions:

```text
Edit this exact source image without redesigning it. Preserve the intended image content, composition, crop, aspect ratio, colors, geometry, and linework.

Preserve every printed or intended text element exactly as shown, including letters, numbers, Chinese characters, captions, diagram labels, point names, axis labels, tick values, units, formulas, symbols, logos, and watermarks. Preserve intended geometric strokes and diagram lines even when they look hand-drawn. Do not erase, rewrite, translate, correct, replace, or regenerate this text.

Remove only later-added handwritten scribbles, freehand annotations, pencil or pen calculations, stray marks, and accidental stains that are not part of the intended image or diagram. Reconstruct only the pixels hidden by those removed scribbles. If uncertain whether a mark is intended content or an added scribble, preserve it.

Remove the background and return the preserved content on true alpha transparency. Upscale it to high definition at the highest practical quality, targeting at least 2048 pixels on the long edge without reducing the source dimensions. Preserve crisp edges and do not invent new objects or details. Output exactly one image.
```

3. Save or copy the returned artifact directly over the exact source path, using the same directory and filename, including the original extension. Do not create a cleaned-output sibling and do not change any Markdown image destination.
4. Apply a 10-minute operational timeout unless the invoking organizer provides a shorter positive timeout. If the call is still active at the timeout, terminate it, leave the source unchanged, record it as timed out, and continue.
5. Do not inspect, validate, resize, transcode, post-process, chroma-key, OCR, or otherwise alter the returned artifact. Do not retry because of apparent quality, text, transparency, format, extension, or resolution issues. If the model returns no usable artifact or the replacement write fails, leave or restore the source from its batch backup, record the failure, and continue.

## Result semantics

- Set `image_replacement_status` to `completed` only when the complete backup exists and every nonfailed replacement is present at its original path.
- Set `image_quality_status` to `unverified` for returned artifacts. This skill does not establish visual correctness, true transparency, preserved text, or publication readiness.
- Never report `image_quality_status: passed`. Only the organizer's final rendered-page visual QA may promote it to `passed` or set it to `failed`.
- Preserve the backup and per-file source/replacement SHA-256 hashes so a resumed organizer run can prove that image cleaning must not run again.

## Report

Return the input folder, backup folder, discovered count, backed-up count, replaced count, timed-out count and paths, all failed source paths, per-file source and replacement SHA-256 hashes, `image_replacement_status`, and `image_quality_status: "unverified"`. Confirm that successful replacements retained their original paths and therefore required no Markdown changes. State that outputs were accepted directly from the model without quality checks.
