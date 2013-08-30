import sys
import os
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
import pystache

from twisted.application import internet, service
from twisted.internet import protocol, task, threads, reactor, defer
from twisted.protocols import basic
from twisted.python import log

from bricklayer import builder
from bricklayer.builder import Builder, build_project
from bricklayer.projects import Projects
from bricklayer.git import Git
from bricklayer.config import BrickConfig
from bricklayer.rest import restApp

class BricklayerService(service.Service):

    def __init__(self):
        log.msg("scheduler: init")
        self.sched_task = task.LoopingCall(self.sched_builder)
    
    def send_job(self, project_name, branch, release, version):
        log.msg('sched build: %s [%s:%s]' % (project_name, release, version))
        brickconfig = BrickConfig()
        #queue = Dreque(brickconfig.get('redis', 'redis-server'))
        #queue.enqueue('build', 'builder.build_project', {
        builder.build_project({
            'project': project_name, 
            'branch': branch, 
            'release': release, 
            'version': version,
            })

    def sched_builder(self):
        for project in sorted(Projects.get_all(), key=lambda p: p.name):
            if (project.name == ""):
                continue
            try:
                log.msg("checking project: %s" % project.name)
                if project.is_building():
                    log.msg("project %s still building, skip" % project.name)
                    continue
                branch = "master"
                git = Git(project)
                if os.path.isdir(git.workdir):
                    git.checkout_branch(branch)
                    git.pull()
                else:
                    git.clone(branch)

                if not os.path.isdir(git.workdir):
                    continue

                for remote_branch in git.branches(remote=True):
                    git.checkout_remote_branch(remote_branch.replace('origin/', ''))

                for release in ('stable', 'testing', 'unstable'):
                    if project.last_tag(release) != git.last_tag(release):
                        try:
                            _, version = git.last_tag(release).split('_')
                            log.msg("new %s tag, building version: %s" % (release, version))
                            d = threads.deferToThread(self.send_job, project.name, branch, release, version)
                        except Exception, e:
                            log.msg("tag not parsed: %s:%s" % (project.name, git.last_tag(release)))
                
                #if int(project.experimental) == 1:
                #    for branch in project.branches():
                #        git.checkout_remote_branch(branch)
                #        git.checkout_branch(branch)
                #        git.pull()
                #        if project.last_commit(branch) != git.last_commit(branch):
                #            project.last_commit(branch, git.last_commit(branch))
                #            d = threads.deferToThread(self.send_job, project.name, branch, 'experimental', None)
                # 
                #        git.checkout_branch("master")

            except Exception, e:
                log.err(e)
                

    def startService(self):
        service.Service.startService(self)
        log.msg("scheduler: start %s" % self.sched_task)
        self.sched_task.start(10.0)

    @defer.inlineCallbacks
    def stopService(self):
        service.Service.stopService(self)
        yield self.sched_task.stop()


brickService = BricklayerService()

application = service.Application("Bricklayer")
brickService.setServiceParent(application)
