from lanxang.core.runtime import AtlasRuntime


class AtlasApplication:
    """
    Main Lanxang application container.
    """

    def __init__(self):

        self.runtime = AtlasRuntime()


application = AtlasApplication()
