from litestar import Controller, get

from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class MiscComponentsController(Controller):
    @get(path="/components/image-upload")
    async def get_image_upload(self) -> Template:
        """
        Render the image upload component.
        """
        template_str = catalog.render("ImageUpload")
        return HTMXBlockTemplate(template_str=template_str)
