import sys
reload(sys)
sys.setdefaultencoding('utf8')

import os
import re
import subprocess
import time
import ConfigParser
import shlex
import shutil
import logging
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
sys.path.append(os.path.dirname(__file__))

from bricklayer.utils import pystache
import git

from twisted.internet import threads, reactor, defer
from config import BrickConfig
from projects import Projects

from builder_rpm import BuilderRpm
from builder_deb import BuilderDeb
from build_options import BuildOptions
from build_container import BuildContainer

#from dreque import Dreque

config = BrickConfig()
redis_server = config.get('redis', 'redis-server')
log_file = config.get('log', 'file')

#queue = Dreque(redis_server)

logging.basicConfig(filename=log_file, level=logging.DEBUG)
log = logging.getLogger('builder')

@defer.inlineCallbacks
def build_project(kargs):
    builder = Builder(kargs['project'])
    kargs.pop('project')
    yield builder.build_project(**kargs)

class Builder(object):
    def __init__(self, project):
        self.project = Projects(project)
        self.templates_dir = BrickConfig().get('workspace', 'template_dir')
        self.git = git.Git(self.project)
        self.build_system = BrickConfig().get('build', 'system')
        self.build_options = BuildOptions(self.git.workdir)

        
        self.build_container = None
        self.workspace = "%s/%s" % (
            BrickConfig().get('workspace', 'dir'),
            self.project.name,
        )

        self.real_workspace = "%s/%s" % (
            BrickConfig().get('workspace', 'dir'), self.project.name
        )

        if self.build_system == 'rpm':
            self.mod_install_cmd = self.project.install_cmd.replace(
                'BUILDROOT', '%{buildroot}'
            )
        elif self.build_system == 'deb' or self.build_system == None:
            self.mod_install_cmd = self.project.install_cmd.replace(
                'BUILDROOT', 'debian/tmp'
            )            
        if not os.path.isdir(self.workspace):
            os.makedirs(self.workspace)

        if not os.path.isdir(os.path.join(self.workspace, 'log')):
            os.makedirs(os.path.join(self.workspace, 'log'))

        self.stdout = None
        self.stderr = self.stdout

    def _exec(self, cmd, *args, **kwargs):
        if True or self.build_options.not_found:
            return subprocess.Popen(cmd, *args, **kwargs)
        else:
            chroot_cmd = "chroot %s bash -c \"cd %s; %s\"" % (self.build_container.dir, self.real_workspace, " ".join(cmd))
            kwargs.update({'shell': True})
            return subprocess.Popen(chroot_cmd, *args, **kwargs)
        

    def build_project(self, branch=None, release=None, version=None, commit=None):
        log.info("ENTER:build_project")
        if not self.project.is_building():
            self.project.start_building()
            try:
                if (release is not None and version is not None):
                    log.info("git fetch/clone")
                    if (not self.git.pull()):
                        self.git.clone(branch)

                self.workdir = "%s-%s" % (self.git.workdir, release)
                self.real_workspace = "%s-%s" % (self.real_workspace, release)
                if (os.path.exists(self.workdir)):
                    shutil.rmtree(self.workdir, ignore_errors=True)
                shutil.copytree(self.git.workdir, self.workdir, True)
                log.info("shutil.copytree: ok")

                if self.build_system == 'rpm':
                    self.package_builder = BuilderRpm(self)
                elif self.build_system == 'deb':
                    self.package_builder = BuilderDeb(self)

                os.chdir(self.workdir)
                self.git.workdir = self.workdir
                self.git.checkout_branch(branch)

                if release == 'experimental' and self.build_options.changelog:
                    self.git.checkout_branch(branch)
                    self.package_builder.build(branch, release)
                    self.package_builder.upload(branch)
                if release != None and commit != None:
                    self.git.checkout_tag(commit)
                    self.package_builder.build(branch, force_version=version, force_release=release)
                    self.package_builder.upload(release)
                else:
                    self.project.last_tag(release, self.git.last_tag(release))
                    self.git.checkout_tag(self.project.last_tag(release))
                    self.package_builder.build(branch, self.project.last_tag(release))
                    self.package_builder.upload(release)
                self.git.checkout_branch('master')
            except Exception, e:
                traceback.print_exc()
                log.exception("build failed: %s" % repr(e))
            finally:
                self.project.stop_building()
                shutil.rmtree(self.workdir, ignore_errors=True)
                if self.build_container != None:
                    self.build_container.teardown()
