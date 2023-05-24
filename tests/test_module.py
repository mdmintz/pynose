#
# Just a very simple test module to check that nose can run.
#

setup_module_called = False

def setup_module():
    """
    Does nothing.
    """
    setup_module_called = True

def test_1():
    """
    Does nothing. Alwasy will succeed.
    """

def teardown_module():
    """
    There is not much we can do here.

    It this is not called, there is nothing else called to check that this
    is called.
    """
    assert setup_module_called
