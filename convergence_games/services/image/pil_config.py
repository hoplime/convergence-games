"""Process-wide Pillow configuration.

Importing this module sets `PIL.Image.MAX_IMAGE_PIXELS` so that decoding any
image whose pixel count exceeds the configured cap raises
`PIL.Image.DecompressionBombError` (or a warning, depending on Pillow's mode).
This is our first line of defence against decompression-bomb uploads.
"""

import PIL.Image as PILImage

from convergence_games.settings import SETTINGS

PILImage.MAX_IMAGE_PIXELS = SETTINGS.IMAGE_UPLOAD_MAX_DECODE_PIXELS
