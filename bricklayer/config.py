import os
import ConfigParser

class BrickConfigImpl:
    _instance = None
    config_file = None

    def __init__(self):
        self.config_parse = ConfigParser.ConfigParser()
        self.config_parse.read([self.config_file])

    def get(self, section, name):
        return self.config_parse.get(section, name)

def BrickConfig(config_file=None):
    if not BrickConfigImpl._instance:
        BrickConfigImpl.config_file = resolve_config_file(config_file)
        BrickConfigImpl._instance = BrickConfigImpl()

    return BrickConfigImpl._instance

def resolve_config_file(config_file):
    if config_file == None:
        if "BRICKLAYERCONFIG" in os.environ.keys():
            config_file = os.environ['BRICKLAYERCONFIG']
        else:
            config_file = '/etc/bricklayer/bricklayer.ini'

    check_config_file(config_file)
    return config_file

def check_config_file(config_file):
    if not os.path.exists(config_file) and not os.path.isfile(config_file):
        print "You need to set BRICKLAYERCONFIG or create /etc/bricklayer/bricklayer.ini"
        exit(1)