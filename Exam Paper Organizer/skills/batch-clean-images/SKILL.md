---
name: batch-clean-images
description: Process every raster image in a local folder sequentially by sending each source image and one edit prompt directly to GPT-5.6 image editing, then accepting the returned artifact without inspection or validation. Use for fast batch upscaling, transparent-background conversion, and removal of only handwritten scribbles or added annotations while preserving printed text, letters, numbers, diagram labels, symbols, and intended linework.
---

# Batch Clean Images

Prioritize speed. Send each image directly to the image-editing model once and accept its returned artifact as-is.

## Process the folder

1. Resolve the input folder to an absolute path.
2. Write PNG outputs to a sibling folder named `<input-folder>-cleaned` unless the user specifies another folder. Keep all source files unchanged.
3. Recursively enumerate supported raster images and sort them by relative path. Process them sequentially; never parallelize image-editing calls.
4. If an exact destination PNG already exists, skip it unless the user explicitly requests overwrite.
5. For each image, call the native image-generation/editing tool exactly once with `referenced_image_paths: [source]`. Do not inspect the source first and do not infer the source from recent conversation images.
6. Use the following prompt without adding image-specific assumptions:

```text
Edit this exact source image without redesigning it. Preserve the intended image content, composition, crop, aspect ratio, colors, geometry, and linework.

Preserve every printed or intended text element exactly as shown, including letters, numbers, Chinese characters, captions, diagram labels, point names, axis labels, tick values, units, formulas, symbols, logos, and watermarks. Preserve intended geometric strokes and diagram lines even when they look hand-drawn. Do not erase, rewrite, translate, correct, replace, or regenerate this text.

Remove only later-added handwritten scribbles, freehand annotations, pencil or pen calculations, stray marks, and accidental stains that are not part of the intended image or diagram. Reconstruct only the pixels hidden by those removed scribbles. If uncertain whether a mark is intended content or an added scribble, preserve it.

Remove the background and return the preserved content on true alpha transparency. Upscale it to high definition at the highest practical quality, targeting at least 2048 pixels on the long edge without reducing the source dimensions. Preserve crisp edges and do not invent new objects or details. Output exactly one PNG.
```

7. Save or copy the returned artifact directly to the destination PNG path. Use the tool-provided local artifact path or output hint when present.
8. Do not inspect, validate, resize, post-process, chroma-key, OCR, or otherwise alter the returned artifact. Do not retry because of apparent quality, text, transparency, or resolution issues. If the model call returns no usable artifact, record the failure and continue to the next image.

## Report

Return the input folder, output folder, discovered count, processed count, skipped-existing count, and failed source paths. State that outputs were accepted directly from the model without quality checks.
