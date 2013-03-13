import sys
import os
from nose import *

from bricklayer.projects import Projects
from bricklayer.builder import Builder

def setup():
    os.chdir(os.path.join(os.path.dirname(__file__), '..'))

class TestBuilder:
    def build_init_test(self):
        print os.path.abspath(os.path.curdir)
        p = Projects('test_build')
        p.git_url = 'test/test_repo'
        p.group = 'test_group'
        p.version = '0.100.0'
        p.save()

        b = Builder('test_build')
        b.build_project(branch='master', release='experimental', version='0.100.1', commit=None)
        
        
