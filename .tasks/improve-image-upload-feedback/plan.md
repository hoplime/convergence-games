---
title: Improve image upload feedback and hardening in game submission
created: 2026-05-07
status: complete
---

# Improve image upload feedback and hardening in game submission

## Context

The submit-game and edit-game forms accept up to 10 images per game, with a single global `request_max_body_size=20 * 1024 * 1024` (20 MB) limit applied to the request as a whole. There is currently almost no client-side feedback about image size, and the server has no defence against malformed, oversized, or pixel-bomb images. Specifically:

- `convergence_games/app/templates/components/ImageUpload.html.jinja` shows a preview but does not validate file size, type, or dimensions.
- `convergence_games/app/templates/components/MultiImageUploadContainer.html.jinja` enforces the 10-image cap in the UI only.
- `convergence_games/app/routers/frontend/submit_game.py` (POST `/event/{event_sqid}/game`, PUT `/game/{game_sqid}`) only handles HTTP 413 with a generic toast; it does not validate count, MIME, or per-file size, and the POST handler is annotated `RequestEncodingType.URL_ENCODED` even though the form is multipart.
- `convergence_games/services/image/image_loader.py` calls `PIL.Image.open()` and re-encodes as JPEG with no try/except, no `MAX_IMAGE_PIXELS` guard, no max-dimension cap.
- `convergence_games/settings.py` has no image-related limits configured.

Users currently learn about the 20 MB cap only after a failed submit; non-image, corrupt, or decompression-bomb uploads can cause uncaught exceptions; and there is no protection against a 100,000×100,000-pixel PNG. We want concrete, configurable limits, friendly client-side feedback, and server-side hardening that silently downscales oversized images.

## Requirements

- Image limits live in `Settings` and are tunable via `.env` (no hard-coded constants in route files).
- Defaults: max 5 MB per file, max 10 images per game, max 4096 px on the longest side, allowed MIME types `image/png`, `image/jpeg`, `image/gif`.
- The Litestar `request_max_body_size` for both submit-game POST and edit-game PUT is derived from the per-file and per-count settings (with a small headroom buffer for non-image fields), not a hard-coded 20 MB.
- Client-side, before submit, the form shows: per-file errors (size, type), a running total-size meter (`X.X MB / Y.Y MB`), a count badge (already present), and disables the submit button while any error is unresolved.
- Server-side, the submit/edit form validation rejects: too many images, wrong MIME types, files exceeding the per-file size cap. Rejections surface through the existing `handle_submit_game_form_validation_error` machinery as field errors on the `image` field.
- Server-side image decoding is wrapped in error handling. Unreadable / corrupt files produce a friendly `image` field validation error, not a 500.
- `Pillow.Image.MAX_IMAGE_PIXELS` is configured (per-process) so decompression bombs raise `Image.DecompressionBombError`, which is caught and converted to a friendly validation error.
- Images whose decoded dimensions exceed `MAX_IMAGE_DIMENSION_PIXELS` are silently downscaled to fit before being saved (using `PIL.Image.thumbnail`).
- The pre-existing `RequestEncodingType.URL_ENCODED` on POST `/event/{event_sqid}/game` is corrected to `RequestEncodingType.MULTI_PART`.
- The 413 fallback toast is updated to reference the configured limit instead of the hard-coded "20MB".

## Technical Design

### Settings

Add to `convergence_games/settings.py` under a new "Image upload" block:

```python
# Image upload limits
IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024      # 5 MB per image
IMAGE_UPLOAD_MAX_IMAGES_PER_GAME: int = 10
IMAGE_UPLOAD_MAX_DIMENSION_PIXELS: int = 4096                 # longest side
IMAGE_UPLOAD_MAX_DECODE_PIXELS: int = 50_000_000              # PIL.Image.MAX_IMAGE_PIXELS guard
IMAGE_UPLOAD_ALLOWED_MIME_TYPES: Json[list[str]] | list[str] = [
    "image/png", "image/jpeg", "image/gif",
]
IMAGE_UPLOAD_REQUEST_BODY_HEADROOM_BYTES: int = 2 * 1024 * 1024  # for non-image form fields
```

Add a `cached_property`:

```python
@cached_property
def IMAGE_UPLOAD_MAX_REQUEST_BODY_BYTES(self) -> int:  # noqa: N802
    return (
        self.IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES * self.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME
        + self.IMAGE_UPLOAD_REQUEST_BODY_HEADROOM_BYTES
    )
```

`SETTINGS` is already imported in `submit_game.py`. We use `SETTINGS.IMAGE_UPLOAD_*` directly at module import time for `request_max_body_size` and pass the runtime values into form validators and the image loader.

### Pillow configuration

Add a small module `convergence_games/services/image/pil_config.py` that, on import, sets `PIL.Image.MAX_IMAGE_PIXELS = SETTINGS.IMAGE_UPLOAD_MAX_DECODE_PIXELS`. Import it once from `convergence_games/services/image/__init__.py` so the cap is in effect anywhere PIL is used. (Pillow raises `Image.DecompressionBombError` when the cap is exceeded.)

### Image loader: safe decode + downscale

Refactor `convergence_games/services/image/image_loader.py` so the abstract base offers a single safe entry point:

```python
class ImageDecodeError(Exception): ...

class ImageLoader(ABC):
    def _decode_and_normalise(self, image_data: bytes) -> PILImage.Image:
        """Open image safely, cap dimensions, return a PIL Image ready for save.

        Raises ImageDecodeError on any decode/bomb failure.
        """

    async def save_image(self, image_data: bytes, lookup: UUID) -> None:
        # Concrete in subclasses; calls self._decode_and_normalise and then
        # self._dump_to_bytes for full-size + each pre-cache size.
```

`_decode_and_normalise` does:

1. `PILImage.open(BytesIO(image_data))` inside `try/except (PILImage.UnidentifiedImageError, PILImage.DecompressionBombError, OSError)` → re-raise as `ImageDecodeError`.
2. `image.load()` to force decode (catches truncated files).
3. If `max(image.size) > SETTINGS.IMAGE_UPLOAD_MAX_DIMENSION_PIXELS`, call `image.thumbnail((max_dim, max_dim))`.
4. Return the in-memory image.

The two concrete loaders (`filesystem_image_loader.py`, `blob_image_loader.py`) currently each open the bytes themselves and call `_dump_to_bytes` per size. Refactor both to:

1. Call `image = self._decode_and_normalise(image_data)` once.
2. Pass that already-decoded image to `_dump_to_bytes` (which keeps the current `image.copy().thumbnail(...)` for per-size variants).

This both removes the redundant decode-per-size cost and concentrates the safety logic in one place.

### Form validation

In `convergence_games/app/routers/frontend/submit_game.py`:

1. Add a top-level helper that reads `SETTINGS` once:

   ```python
   def _validate_image_uploads(images: list[UploadFile | SqidInt]) -> list[UploadFile | SqidInt]:
       max_count = SETTINGS.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME
       max_size = SETTINGS.IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES
       allowed = set(SETTINGS.IMAGE_UPLOAD_ALLOWED_MIME_TYPES)
       errors: list[str] = []
       if len(images) > max_count:
           errors.append(f"You can upload at most {max_count} images.")
       for i, img in enumerate(images):
           if isinstance(img, UploadFile):
               if img.content_type not in allowed:
                   errors.append(f"Image {i + 1}: type '{img.content_type}' is not allowed.")
               if img.size is not None and img.size > max_size:
                   errors.append(f"Image {i + 1}: {img.size / 1024 / 1024:.1f} MB exceeds the {max_size / 1024 / 1024:.0f} MB per-image limit.")
       if errors:
           raise ValueError(errors)
       return images
   ```

2. Attach the validator to the `image` field on `SubmitGameForm`:

   ```python
   image: Annotated[
       list[UploadFile | SqidInt],
       MaybeListValidator,
       AfterValidator(_validate_image_uploads),
   ] = []
   ```

   The existing `handle_submit_game_form_validation_error` already aggregates per-field errors, so the messages surface in the existing `ErrorHolderOob` next to the image field.

3. Wrap the call to `image_loader.save_image(...)` in `create_image()` (line 321) with `try/except ImageDecodeError` and re-raise as a `ValidationException` carrying an `image`-field error (re-using the same shape `handle_submit_game_form_validation_error` consumes), so corrupt/bomb files produce a friendly inline error rather than a 500.

   Because that path is async + after Pydantic validation, the simplest approach is: catch in `post_game` / `put_game` around `create_image_links` and convert into a `ValidationException` with `extra=[{"key": "image", "message": "..."}]`. Confirm this shape by mirroring what `handle_submit_game_form_validation_error` reads from `exc.extra`.

### Route configuration

Replace the two hard-coded `request_max_body_size=20 * 1024 * 1024` lines with `request_max_body_size=SETTINGS.IMAGE_UPLOAD_MAX_REQUEST_BODY_BYTES`.

Change the POST handler's `Body(media_type=RequestEncodingType.URL_ENCODED)` to `RequestEncodingType.MULTI_PART` to match the actual form encoding (the PUT handler is already correct).

Update `handle_request_entity_too_large_error` to reference the configured cap:

```python
limit_mb = SETTINGS.IMAGE_UPLOAD_MAX_REQUEST_BODY_BYTES / 1024 / 1024
raise AlertError([
    Alert("alert-error", "Too much data for the server to handle! (Error 413)"),
    Alert("alert-error", f"If you've submitted images, try reducing their total size below {limit_mb:.0f} MB."),
])
```

### Client-side feedback

The pattern in this codebase is inline `<script>` blocks inside JinjaX components (see `MultiImageUploadContainer.html.jinja`). Keep that pattern.

Pass the limits into the components from the templates. Since `SubmitGameController.get_submit_game()` already calls `catalog.render` for the page, and JinjaX components receive globals, the cleanest path is to expose the settings as Jinja globals — register them in `convergence_games/app/app_config/template_config.py` (where other globals live):

```python
"IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES": SETTINGS.IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES,
"IMAGE_UPLOAD_MAX_IMAGES_PER_GAME": SETTINGS.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME,
"IMAGE_UPLOAD_ALLOWED_MIME_TYPES": SETTINGS.IMAGE_UPLOAD_ALLOWED_MIME_TYPES,
```

Then:

1. **`MultiImageUploadContainer.html.jinja`**:
   - Default `max_images` from `IMAGE_UPLOAD_MAX_IMAGES_PER_GAME` instead of literal 10.
   - Add a total-size element next to the count: `<span id="image-total-{{ id }}">0.0 MB / X.X MB</span>`.
   - Extend the inline script with a `recalcTotal()` function that sums `file.size` across all `<input type="file">` children plus a `data-existing-size` attribute on existing-image `<li>` elements (treat existing as 0 bytes — we don't re-upload them; this keeps the meter user-meaningful), and update colour state when over budget.
   - Listen for `change` events bubbling from any descendant `input[type=file]`; recompute on add/remove and on `htmx:load`.
   - Disable the form's submit button when any per-file error is present or the live total exceeds the body cap; re-enable when clean. Use a custom event `image-upload:status` dispatched from the container so `submit_game.html.jinja` can listen.

2. **`ImageUpload.html.jinja`**:
   - Add a small error banner element that becomes visible when validation fails.
   - On `change`, before assigning the preview src, validate:
     - `file.size <= IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES` → otherwise show "Image is X.X MB; the limit is Y MB".
     - `file.type in IMAGE_UPLOAD_ALLOWED_MIME_TYPES` → otherwise show "Type '<file.type>' is not supported. Use PNG, JPEG, or GIF."
   - The hyperscript block already runs on `change`; extend it to include the validation. The component sets a `data-image-error="..."` attribute on its `<li>` so the container can aggregate state.
   - Pass the limit values into the component via JinjaX globals.

3. **`submit_game.html.jinja`**: no structural change; the submit button picks up disabled state via the `image-upload:status` event listener (added inline near the form's submit row).

### Tests

Add `tests/services/image/test_image_loader.py`:

- A 1×1 valid PNG decodes and saves (use the in-memory bytes via a temp dir filesystem loader).
- A `b"not an image"` payload raises `ImageDecodeError`.
- A truncated PNG raises `ImageDecodeError` (catch via `image.load()`).
- A synthesised "decompression bomb" — create a `PIL.Image.new("RGB", (W, H))` where `W*H > MAX_IMAGE_PIXELS`, save to PNG bytes, and confirm `_decode_and_normalise` raises `ImageDecodeError` (`DecompressionBombError` is a subclass of `Exception`).
- A 6000×6000 valid image gets downscaled so `max(image.size) <= MAX_IMAGE_DIMENSION_PIXELS`.

Add `tests/app/routers/frontend/test_submit_game_image_validation.py`:

- A unit test on `_validate_image_uploads` covering: too many files, disallowed MIME, oversize per-file, valid case.

(Full route-level multipart tests are out of scope; the codebase has no existing route test infra to extend cheaply.)

## Implementation Plan

### Phase 1: Settings & Pillow guard

- [x] **Add image-upload settings** (`convergence_games/settings.py`)
  - Add `IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES`, `IMAGE_UPLOAD_MAX_IMAGES_PER_GAME`, `IMAGE_UPLOAD_MAX_DIMENSION_PIXELS`, `IMAGE_UPLOAD_MAX_DECODE_PIXELS`, `IMAGE_UPLOAD_ALLOWED_MIME_TYPES`, `IMAGE_UPLOAD_REQUEST_BODY_HEADROOM_BYTES`.
  - Add `IMAGE_UPLOAD_MAX_REQUEST_BODY_BYTES` cached property.
- [x] **Configure Pillow decompression-bomb cap** (`convergence_games/services/image/pil_config.py`, new file)
  - Set `PIL.Image.MAX_IMAGE_PIXELS = SETTINGS.IMAGE_UPLOAD_MAX_DECODE_PIXELS` at module import.
- [x] **Wire Pillow config into package init** (`convergence_games/services/image/__init__.py`)
  - Import the new module so it runs once on app startup.

#### Phase 1 verification

- [x] `basedpyright` — no new errors
- [x] `ruff check` — no new errors
- [x] App boots: `litestar --app convergence_games.app:app run --reload` starts without errors.

### Phase 2: Image loader hardening

- [x] **Add `ImageDecodeError` and `_decode_and_normalise`** (`convergence_games/services/image/image_loader.py`)
  - New exception class.
  - New method on `ImageLoader` performing safe `Image.open` + `image.load()` + dimension cap (via `image.thumbnail`).
  - Catch `UnidentifiedImageError`, `DecompressionBombError`, `OSError` and re-raise as `ImageDecodeError`.
- [x] **Refactor `FilesystemImageLoader.save_image`** (`convergence_games/services/image/filesystem_image_loader.py`)
  - Decode once via `_decode_and_normalise`, pass the decoded `PILImage.Image` to `_dump_to_bytes` for full-size and each pre-cache size.
- [x] **Refactor `BlobImageLoader.save_image`** (`convergence_games/services/image/blob_image_loader.py`)
  - Same refactor as filesystem loader.
- [x] **Tests** (`tests/services/image/test_image_loader.py`, new)
  - Valid image → success.
  - Garbage bytes → `ImageDecodeError`.
  - Truncated PNG → `ImageDecodeError`.
  - Bomb (pixel count > cap) → `ImageDecodeError`.
  - Oversized but valid image → downscaled.

#### Phase 2 verification

- [x] `pytest tests/services/image/` passes.
- [x] `basedpyright` — no new errors.
- [x] `ruff check` — no new errors.

### Phase 3: Server-side form validation & route fixes

- [x] **Add `_validate_image_uploads` helper and wire to `SubmitGameForm.image`** (`convergence_games/app/routers/frontend/submit_game.py`)
  - Helper raises `ValueError(errors)` so Pydantic surfaces them via the existing `ValidationException` machinery.
  - Field annotation gains `AfterValidator(_validate_image_uploads)`.
- [x] **Catch `ImageDecodeError` in `post_game` and `put_game`** (`convergence_games/app/routers/frontend/submit_game.py`)
  - Wrap `create_image_links` calls; convert `ImageDecodeError` to a `ValidationException` with `extra=[{"key": "image", "message": "..."}]` so `handle_submit_game_form_validation_error` renders it inline.
- [x] **Replace hard-coded body limits and fix encoding** (`convergence_games/app/routers/frontend/submit_game.py`)
  - Both routes: `request_max_body_size=SETTINGS.IMAGE_UPLOAD_MAX_REQUEST_BODY_BYTES`.
  - POST `post_game`: change `RequestEncodingType.URL_ENCODED` to `RequestEncodingType.MULTI_PART`.
  - Update `handle_request_entity_too_large_error` text to use the configured limit.
- [x] **Tests** (`tests/app/routers/frontend/test_submit_game_image_validation.py`, new)
  - Unit-test `_validate_image_uploads` for the four cases listed in Technical Design.

#### Phase 3 verification

- [x] `pytest` passes.
- [x] `basedpyright` — no new errors.
- [x] `ruff check` — no new errors.
- [x] Manual: submit a >5 MB JPEG via the form → inline image-field error, no 500.
- [x] Manual: submit a non-image file by removing the `accept` attribute via devtools → inline error.
- [x] Manual: submit a corrupt JPEG (truncated bytes) → inline error, no 500.

### Phase 4: Client-side feedback

- [x] **Expose limits as JinjaX globals** (`convergence_games/app/app_config/template_config.py`)
  - Add `IMAGE_UPLOAD_MAX_FILE_SIZE_BYTES`, `IMAGE_UPLOAD_MAX_IMAGES_PER_GAME`, `IMAGE_UPLOAD_ALLOWED_MIME_TYPES` to the global context.
- [x] **Update `MultiImageUploadContainer`** (`convergence_games/app/templates/components/MultiImageUploadContainer.html.jinja`)
  - Default `max_images` from the global.
  - Add total-size meter element.
  - Extend the inline script:
    - `recalcTotal()` summing all `input[type=file].files[0].size`.
    - Aggregate per-child `data-image-error` state.
    - Compute over-budget vs per-file budget × count.
    - Toggle a CSS warning state and dispatch `image-upload:status` `CustomEvent` with `{ ok: bool }` on the container.
  - Listen for child `change` and `htmx:load`; recompute.
- [x] **Update `ImageUpload`** (`convergence_games/app/templates/components/ImageUpload.html.jinja`)
  - Add error banner sibling.
  - Extend the hyperscript on `change` to validate size and MIME, set `data-image-error` on the `<li>`, and bubble a `change` event so the container can recompute.
- [x] **Submit button gating** (`convergence_games/app/templates/pages/submit_game.html.jinja`)
  - Add a small inline script near the form's submit row that listens for `image-upload:status` and toggles the button's `disabled` state.

#### Phase 4 verification

- [x] `npm run build` succeeds.
- [x] `npx tsc --noEmit` — no new errors (Jinja-side only, but ensure nothing in lib.ts regresses).
- [x] Manual: select a 10 MB image → red banner appears under the file input; submit button disabled; total meter shows the offending size.
- [x] Manual: pick a `.txt` renamed to `.png` (real type `text/plain`) → "type not supported" message.
- [x] Manual: add 10 valid small images, then try Add Image → button disabled at cap.
- [x] Manual: total size meter updates as files are added, removed, replaced.

## Acceptance Criteria

- [x] Type checking passes (`basedpyright`).
- [x] Linting passes (`ruff check`, `ruff format --check`).
- [x] All tests pass (`pytest`).
- [x] Dev server starts without errors.
- [x] All image limits live in `Settings` and are overridable via `.env`.
- [x] No hard-coded `20 * 1024 * 1024` remains in `submit_game.py`.
- [x] POST `/event/{event_sqid}/game` declares `RequestEncodingType.MULTI_PART`.
- [x] Submitting a corrupt/truncated image produces a friendly inline error, never a 500.
- [x] Submitting a decompression-bomb PNG produces a friendly inline error and never decodes the bomb.
- [x] An image larger than `IMAGE_UPLOAD_MAX_DIMENSION_PIXELS` on its longest side is downscaled before saving.
- [x] The submit form's total-size meter and per-file errors update live as files are added/removed/changed; submit is blocked when any error is unresolved.
- [x] The 413 fallback toast text reflects the configured cap, not a literal "20MB".

## Risks and Mitigations

1. **`UploadFile.size` may be `None` for streamed multipart parts**: Litestar typically populates it, but the validator must treat `None` as "skip the size check" so we don't reject valid uploads. The decoded-bytes path (after `await upload_file.read()`) is the authoritative size enforcement; the Pydantic check is a fast pre-screen. Mitigation: also enforce per-file size in `create_image` (reject after read if `len(image_bytes) > max`).
2. **Refactoring `save_image` to take a pre-decoded image changes the abstract base signature**: Both concrete loaders must be updated in the same commit. Mitigation: keep `save_image(image_data: bytes, lookup: UUID)` as the public API; the decode happens internally in each subclass via the shared `_decode_and_normalise`.
3. **Setting `PIL.Image.MAX_IMAGE_PIXELS` is process-global**: Other PIL usages in the codebase (e.g. allocator visualisations, if any) inherit the cap. Mitigation: pick a generous default (50M pixels — well above any legitimate user upload, well below a bomb).
4. **Client-side validation is bypassable**: All limits must also exist server-side. Covered by Phase 3.
5. **GIF handling**: PIL's `convert("RGB").save(format="JPEG")` flattens animated GIFs to a single frame. This is existing behaviour; document briefly in the code comment near `_dump_to_bytes` so future readers don't mistake it for a regression.

## Notes

- The `MaybeListValidator` (line 83) plus the new `AfterValidator` keeps the field schema honest while adding rich errors. If we later need richer per-file errors (e.g. "image 3 is wrong type" surfaced next to image 3), revisit splitting the field.
- `litestar.exceptions.ValidationException`'s `.extra` shape is `list[dict[str, str]]` with `key`/`message` — confirmed by the existing handler at `submit_game.py:243`.
- Out of scope: client-side resize-before-upload (deferred per planning discussion); pre-signed direct-to-blob uploads.
