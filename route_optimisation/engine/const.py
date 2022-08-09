from .ortools.algorithm import GroupAlgorithm, OneDriverAlgorithm, SoftOneDriverAlgorithm


class Algorithms:
    GROUP = 'group'
    ONE_DRIVER = 'one_driver'
    SOFT_ONE_DRIVER = 'soft_one_driver'

    map = {
        GROUP: GroupAlgorithm,
        ONE_DRIVER: OneDriverAlgorithm,
        SOFT_ONE_DRIVER: SoftOneDriverAlgorithm,
    }
