"""
menu_images.py - Finds the photo for a dish.

If a dish has an image_url in the database, that is used. If it is empty, we look for
static/img/menu/<dish-name-as-slug>.jpg (for example "Veg Biryani" -> veg-biryani.jpg).
This means the photos show up even on a database that was created before they were added.
"""

import os
import re

_MENU_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "menu")


def resolve_image_url(name, image_url):
    if image_url:
        return image_url

    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    if slug and os.path.isfile(os.path.join(_MENU_DIR, slug + ".jpg")):
        return "/static/img/menu/" + slug + ".jpg"

    return None
