
"""
MAP Client Plugin - Generated from MAP Client v0.18.0
"""

__version__ = '0.2.1'
__author__ = 'Hugh Sorby'
__stepname__ = 'Propagate Zinc Data'
__location__ = 'https://github.com/mapclient-plugins/mapclientplugins.propagatezincdatastep'

# import class that derives itself from the step mountpoint.
from mapclientplugins.propagatezincdatastep import step

# Import the resource file when the module is loaded,
# this enables the framework to use the step icon.
from . import resources_rc
