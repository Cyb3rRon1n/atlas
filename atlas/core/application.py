from atlas.core.runtime import AtlasRuntime


class AtlasApplication:
    """
    Main Atlas application container.
    """

    def __init__(self):

        self.runtime = AtlasRuntime()


application = AtlasApplication()
