import numpy as np
from PIL import Image

from readablemusic.cleanup import blank_outside_music

IL = 24


def text(a, y, x0=100, x1=700):
    """Draw a line of 'words': short dark blocks, the size of lyrics."""
    for x in range(x0, x1, 40):
        a[y:y + 16, x:x + 25] = 0


def page():
    a = np.full((1400, 1000), 255, np.uint8)
    text(a, 100)  # title
    for top in (400, 700):  # two staves
        for k in range(5):
            a[top + k * IL:top + k * IL + 2, 50:950] = 0
    text(a, 540)  # lyrics under the first staff
    text(a, 840)  # lyrics under the last staff
    text(a, 1250)  # footer
    return a


def test_blanks_title_and_footer_only():
    a = page()
    b = np.asarray(blank_outside_music(Image.fromarray(a), IL))
    assert (b[90:130] == 255).all() and (b[1240:1280] == 255).all()
    assert (b[300:900] == a[300:900]).all()


def test_leaves_page_without_staves_alone():
    a = np.full((1400, 1000), 255, np.uint8)
    text(a, 100)
    text(a, 700)
    b = np.asarray(blank_outside_music(Image.fromarray(a), IL))
    assert (b == a).all()
