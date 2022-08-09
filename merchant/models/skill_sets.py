from django.db import models

from .merchant import Merchant


class SkillSet(models.Model):
    CHETWODE_BLUE = '#8D87E3'
    LAVENDER = '#AE62D6'
    JAVA = '#22C2BD'
    FROLY = '#F56E8F'
    FRUIT_SALAD = '#619F49'
    SHIRAZ = '#BE0649'
    BRIGHT_SUN = '#FECE46'
    COPPER = '#B87437'
    OLD_BRICK = '#891E28'
    TUNDORA = '#4B4B4B'
    PUMPKIN = '#FF7B1B'
    ALIZARIN_CRIMSON = '#E22B2B'
    DANUBE = '#6DB0CD'
    BLUE_CHILL = '#0C8F8A'
    FERN = '#63BD6E'
    BEAVER = '#876C59'
    ATLANTIS = '#A4BF35'
    ROYAL_BLUE = '#5158F4'

    color_choices = (
        ('#8D87E3', 'Chetwode Blue'),
        ('#AE62D6', 'Lavender'),
        ('#22C2BD', 'Java'),
        ('#F56E8F', 'Froly'),
        ('#619F49', 'Fruit Salad'),
        ('#BE0649', 'Shiraz'),
        ('#FECE46', 'Bright Sun'),
        ('#B87437', 'Copper'),
        ('#891E28', 'Old Brick'),
        ('#4B4B4B', 'Tundora'),
        ('#FF7B1B', 'Pumpkin'),
        ('#E22B2B', 'Alizarin Crimson'),
        ('#6DB0CD', 'Danube'),
        ('#0C8F8A', 'Blue Chill'),
        ('#63BD6E', 'Fern'),
        ('#876C59', 'Beaver'),
        ('#A4BF35', 'Atlantis'),
        ('#5158F4', 'Royal Blue')
    )

    name = models.CharField(max_length=50)
    color = models.CharField(choices=color_choices, max_length=10)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    is_secret = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    service_time = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('name', 'color', 'merchant')
        ordering = ('name', )

    def __str__(self):
        return u'SkillSet: "{}"'.format(self.name)

    @classmethod
    def get_colors(cls):
        return list(zip(*cls.color_choices))[0]


__all__ = ['SkillSet', ]
