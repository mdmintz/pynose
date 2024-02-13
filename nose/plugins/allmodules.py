"""Use the AllModules plugin by passing ``--all-modules`` or setting the
NOSE_ALL_MODULES environment variable to enable collection and execution of
tests in all python modules. Normal nose behavior is to look for tests only in
modules that match testMatch."""
from nose.plugins.base import Plugin


class AllModules(Plugin):
    """Collect tests from all python modules."""
    def options(self, parser, env):
        """Register commandline options."""
        env_opt = 'NOSE_ALL_MODULES'
        parser.add_option(
            '--all-modules', action="store_true",
            dest=self.enableOpt, default=env.get(env_opt),
            help="Enable plugin %s: %s [%s]" %
            (self.__class__.__name__, self.help(), env_opt)
        )

    def wantFile(self, file):
        """Override to return True for all files ending with .py"""
        if file.endswith('.py'):
            return True
        return None

    def wantModule(self, module):
        """Override return True for all modules"""
        return True
