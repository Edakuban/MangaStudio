"""Shared B5 physical sizing for native panel generation and PDF raster placement."""
import math
from PIL import Image
from .layout import PAGE_W, PAGE_H

PRINT_DPI = 300
PAGE_WIDTH_MM, PAGE_HEIGHT_MM = 176, 250


def pixels_for_points(width, height):
    return (max(1,math.ceil(width*PRINT_DPI/72)),max(1,math.ceil(height*PRINT_DPI/72)))


def panel_pixel_size(box, alignment=16):
    width=box['w']/PAGE_W*PAGE_WIDTH_MM/25.4*PRINT_DPI
    height=box['h']/PAGE_H*PAGE_HEIGHT_MM/25.4*PRINT_DPI
    return tuple(max(alignment,math.ceil(v/alignment)*alignment) for v in (width,height))


def image_is_print_ready(store,panel,box):
    if not panel.get('image'):return False
    try:
        with Image.open(store.asset(panel['image'])) as image:
            width,height=image.size
            if image.getexif().get(274) in (5,6,7,8):width,height=height,width
        needed=panel_pixel_size(box,alignment=1)
        return width>=needed[0] and height>=needed[1]
    except (OSError,ValueError):return False
