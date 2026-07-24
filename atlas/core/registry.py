class ModuleRegistry:

    def __init__(self):

        self.modules = {}

    def register(self, name, module):

        self.modules[name] = module

    def get(self, name):

        return self.modules.get(name)

    def all(self):

        return self.modules
