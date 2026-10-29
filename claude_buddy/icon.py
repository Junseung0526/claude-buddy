"""앱·메뉴바 아이콘 그리기."""

from AppKit import NSAffineTransform, NSBitmapImageFileTypePNG, NSBitmapImageRep, NSImage

from .critter import draw_critter
from .gfx import ORANGE_HEX, rgb, tone


class _Still:
    """창 없이 고정 포즈로 그리기 (아이콘용)."""

    def __init__(self, p):
        self.P, self.W, self.H = p, 16 * p, 13 * p
        self.cols = (rgb(ORANGE_HEX), rgb(tone(ORANGE_HEX, 1.25)), rgb(tone(ORANGE_HEX, 0.82)))

    def pose(self):
        return {"legA": 0, "legB": 0, "bob": 0, "squash": 1, "armL": 0, "armR": self.P * 1.2, "lookX": 0, "lookY": 0,
                "tilt": 0, "shadow": False, "face": "normal", "emote": None, "emoteRise": 0}


def icon_image(px):
    c = _Still(px / 16)
    img = NSImage.alloc().initWithSize_((px, px))
    img.lockFocus()
    tf = NSAffineTransform.transform()
    tf.translateXBy_yBy_(0, (px - c.H) / 2)
    tf.concat()
    draw_critter(c, c.pose())
    img.unlockFocus()
    return img


def write_icon(path, px=1024):
    img = icon_image(px)
    rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None).writeToFile_atomically_(str(path), True)
