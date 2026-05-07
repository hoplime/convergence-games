"""Process-wide Pillow configuration.

Importing this module sets `PIL.Image.MAX_IMAGE_PIXELS` and promotes
`DecompressionBombWarning` to a hard error so any image whose pixel count
exceeds the configured cap raises immediately rather than being decoded.

Pillow's default behaviour is to warn at the cap and only raise
`DecompressionBombError` at twice the cap. We treat the cap as the hard limit.
"""

import warnings

import PIL.Image as PILImage

from convergence_games.settings import SETTINGS

PILImage.MAX_IMAGE_PIXELS = SETTINGS.IMAGE_UPLOAD_MAX_DECODE_PIXELS

warnings.simplefilter("error", PILImage.DecompressionBombWarning)
