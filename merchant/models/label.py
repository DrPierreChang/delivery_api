from django.db import models
from django.db.models.deletion import CASCADE

from .merchant import Merchant


class Label(models.Model):
    DARK_RED = 'red'
    DARK_GREEN = 'green'
    TURQUOISE = 'blue'
    LIGHT_BROWN = 'yellow'
    ORANGE = 'orange'
    DARK_BLUE = 'dark_blue'
    NAVY_BLUE = 'navy_blue'
    BURGUNDY = 'burgundy'
    PURPLE = 'purple'
    PINK = 'pink'
    YELLOW = 'new_yellow'
    LIGHT_GREEN = 'light_green'
    NO_COLOR = 'no_color'

    color_choices = (
        (DARK_RED, 'Dark Red'),
        (DARK_GREEN, 'Dark Green'),
        (TURQUOISE, 'Turquoise'),
        (LIGHT_BROWN, 'Light Brown'),
        (ORANGE, 'Orange'),
        (DARK_BLUE, 'Dark Blue'),
        (NAVY_BLUE, 'Navy Blue'),
        (BURGUNDY, 'Burgundy'),
        (PURPLE, 'Purple'),
        (PINK, 'Pink'),
        (YELLOW, 'Yellow'),
        (LIGHT_GREEN, 'Light Green'),
        (NO_COLOR, 'No color')
    )

    BASE_COLORS = {
        DARK_RED: '#d33e43',
        DARK_GREEN: '#3c896d',
        TURQUOISE: '#8edce6',
        LIGHT_BROWN: '#d58936',
        ORANGE: '#ff7f51',
        DARK_BLUE: '#1768ac',
        NAVY_BLUE: '#5da9e9',
        BURGUNDY: '#91171f',
        PURPLE: '#52154e',
        PINK: '#e55381',
        YELLOW: '#f8d21c',
        LIGHT_GREEN: '#aad321',
        NO_COLOR: '#ffffff'
    }
    DARKENED_COLOR_PAIRS = {
        DARK_RED: '#bd373c',
        DARK_GREEN: '#357b61',
        TURQUOISE: '#7fc5ce',
        LIGHT_BROWN: '#bf7b30',
        ORANGE: '#e57248',
        DARK_BLUE: '#145d9a',
        NAVY_BLUE: '#5397d1',
        BURGUNDY: '#82141b',
        PURPLE: '#491246',
        PINK: '#cd4a73',
        YELLOW: '#debc19',
        LIGHT_GREEN: '#98bd1d',
        NO_COLOR: '#d2d2d2'
    }

    name = models.CharField(max_length=255)
    color = models.CharField(choices=color_choices, max_length=255, default=NO_COLOR)
    merchant = models.ForeignKey(Merchant, on_delete=CASCADE)

    class Meta:
        unique_together = ('color', 'name', 'merchant')
        ordering = ('id',)

    def __str__(self):
        return u'Label "{0}"'.format(self.name)

    @staticmethod
    def get_versioned_colors_map(request):
        if request and request.GET.get('full_color_map', request.version >= 2):
            return COLORS_MAP
        return COLORS_MAP['colors']


COLORS_MAP = {
    'colors': Label.BASE_COLORS,
    'darkened_pairs': {
        Label.BASE_COLORS[color_name]: Label.DARKENED_COLOR_PAIRS[color_name]
        for color_name in Label.BASE_COLORS.keys()
    }
}
