import os
import signal
import sys
import json

sys.path.append(os.path.dirname(__file__))
from projects import Projects
from groups import Groups
from git import Git
from builder import Builder, build_project
from build_info import BuildInfo
from current_build import CurrentBuild
from config import BrickConfig

import cyclone.web
import cyclone.escape
from twisted.internet import reactor
from twisted.python import log
from twisted.application import service, internet

brickconfig = BrickConfig()

class Project(cyclone.web.RequestHandler):
    def post(self, *args):
        if len(args) >= 1:
            name = args[0]
            project = Projects(name)
            for key, value in self.request.arguments.iteritems():
                if key in ("git_url", "version", "build_cmd", "install_cmd"):
                    setattr(project, key, value[0])
            project.save()

        try:
            if not Projects(self.get_argument('name')).exists():
                raise
        except Exception, e:
            project = Projects()
            project.name = self.get_argument('name')[0]
            project.git_url = self.get_argument('git_url')[0]
            for name, parm in self.request.arguments.iteritems():
                if name not in ('branch', 'version'):
                    setattr(project, str(name), parm[0])
            try:
                project.add_branch(self.get_argument('branch'))
                project.version(self.get_argument('branch'), self.get_argument('version'))
                project.group_name = self.get_argument('group_name')
                project.save()
                log.msg('Project created:', project.name)
                
                self.write(cyclone.escape.json_encode({'status': 'ok'}))
            except Exception, e:
                log.err()
                self.write(cyclone.escape.json_encode({'status': "fail"}))

        else:
            self.write(cyclone.escape.json_encode({'status':  "Project already exists"}))

    def put(self, name):
        project = Projects(name)
        try:
            for aname, arg in self.request.arguments.iteritems():
                if aname in ('branch'):
                    branch = arg
                else:
                    setattr(project, aname, arg[0])
            
            json_data = json.loads(self.request.body)
            if len(json_data.keys()) > 0:
                for k, v in json_data.iteritems():
                    setattr(project, k, v)
            
            project.save()
        except Exception, e:
            log.err(e)
            self.finish(cyclone.escape.json_encode({'status': 'fail'}))
        self.finish(cyclone.escape.json_encode({'status': 'modified %s' % name}))

    def get(self, name='', branch='master'):
        try:
            if name:
                    project = Projects(name)
                    reply = {'name': project.name,
                            'branch': project.branches(),
                            'experimental': int(project.experimental),
                            'group_name': project.group_name,
                            'git_url': project.git_url,
                            'version': project.version(),
                            'last_tag_testing': project.last_tag(tag_type='testing'),
                            'last_tag_stable': project.last_tag(tag_type='stable'),
                            'last_tag_unstable': project.last_tag(tag_type='unstable'),
                            'last_commit': project.last_commit(branch)}


            else:
                projects = Projects.get_all()
                reply = []
                for project in projects:
                    reply.append(
                            {'name': project.name,
                            'branch': project.branches(),
                            'experimental': int(project.experimental),
                            'group_name': project.group_name,
                            'git_url': project.git_url,
                            'version': project.version(),
                            'last_tag_testing': project.last_tag(tag_type='testing'),
                            'last_tag_stable': project.last_tag(tag_type='stable'),
                            'last_tag_unstable': project.last_tag(tag_type='unstable'),
                            'last_commit': project.last_commit(branch)
                            })

            self.write(cyclone.escape.json_encode(reply))
        except Exception, e:
            self.write(cyclone.escape.json_encode("%s No project found" % e))


    def delete(self, name):
        log.msg("deleting project %s" % name)
        try:
            project = Projects(name)
            git = Git(project)
            git.clear_repo()
            project.clear_branches()
            project.delete()
            self.write(cyclone.escape.json_encode({'status': 'project deleted'}))
        except Exception, e:
            log.err(e)
            self.write(cyclone.escape.json_encode({'status': 'failed to delete %s' % str(e)}))


class Branch(cyclone.web.RequestHandler):
    def get(self, project_name):
        project = Projects(project_name)
        git = Git(project)
        branches = git.branches(remote=True)
        self.write(cyclone.escape.json_encode({'branches': branches}))

    def post(self, project_name):
        branch = self.get_argument('branch')
        project = Projects(project_name)
        if branch in project.branches():
            self.write(cyclone.escape.json_encode({'status': 'failed: branch already exist'}))
        else:
            project.add_branch(branch)
            project.version(branch, '0.1')
            reactor.callInThread(build_project, {'project': project.name, 'branch': self.get_argument('branch'), 'release': 'experimental'})
            self.write(cyclone.escape.json_encode({'status': 'ok'}))

    def delete(self, project_name):
        project = Projects(project_name)
        branch = self.get_argument('branch')
        project.remove_branch(branch)
        self.write(cyclone.escape.json_encode({'status': 'ok'}))

class Build(cyclone.web.RequestHandler):
    def post(self, project_name):
        project = Projects(project_name)
        release = self.get_argument('tag')
        version = self.get_argument('version')
        commit = self.get_argument('commit', default='HEAD')

        reactor.callInThread(build_project, {
                    'project': project.name, 
                    'branch' : 'master', 
                    'release': release, 
                    'version': version,
                    'commit' : commit,
        })

        self.write(cyclone.escape.json_encode({'status': 'build of branch %s scheduled' % release}))

    def get(self, project_name):
        project = project_name
        build_ids = BuildInfo(project, -1).builds()
        builds = []
        for bid in build_ids[-10:]:
            build = BuildInfo(project, bid)
            builds.append({'build': int(bid), 'log': os.path.basename(build.log()), 'version': build.version(), 'release': build.release(), 'date': build.time()})
        self.write(cyclone.escape.json_encode(builds))

class Log(cyclone.web.RequestHandler):
    def get(self, project, bid):
        build_info = BuildInfo(project, bid)
        if os.path.isfile(build_info.log()):
            self.write(open(build_info.log()).read())

class Check(cyclone.web.RequestHandler):
    def post(self, project_name):
        project = Projects(project_name)
        builder = Builder(project_name)
        builder.build_project()

class Clear(cyclone.web.RequestHandler):
    def post(self, project_name):
        try:
            project = Projects(project_name)
            git = Git(project)
            git.clear_repo()
            self.write(cyclone.escape.json_encode({'status': 'ok'}))
        except Exception, e:
            self.write(cyclone.escape.json_encode({'status': 'fail', 'error': str(e)}))


class Group(cyclone.web.RequestHandler):
    def post(self, *args):
        try:
            if len(args) > 0:
                name = args[0]
                group = Groups(name)
                for key, value in self.request.arguments.iteritems():
                    if key in ("repo_addr", "repo_user", "repo_passwd"):
                        setattr(group, key, value[0])
                group.save()
            else:
                group = Groups(self.get_argument('name'))
                group.repo_addr = self.get_argument('repo_addr')
                group.repo_user = self.get_argument('repo_user')
                group.repo_passwd = self.get_argument('repo_passwd')
                group.save()
            self.write(cyclone.escape.json_encode({'status': 'ok'}))
        except Exception, e:
            self.write(cyclone.escape.json_encode({'status': 'fail', 'error': str(e)}))

    def get(self, *args):
        groups_json = []
        groups = []

        if len(args) > 1:
            name = args[0]
            groups = [Groups(name)]
        else:
            groups = Groups.get_all()

        for group in groups:
            group_json = {}
            for attr in ('name', 'repo_addr', 'repo_user', 'repo_passwd'):
                group_json.update({attr: getattr(group, attr)})
            groups_json.append(group_json)
        self.write(cyclone.escape.json_encode(groups_json))

class Current(cyclone.web.RequestHandler):
    def get(self):
        response = []
        currents = CurrentBuild.get_all()
        for current in currents:
            response.append({"name":current.name})
        self.set_header("Content-Type", "application/json")
        self.write(cyclone.escape.json_encode(response))

    def delete(self):
        CurrentBuild.delete_all()
        self.write(cyclone.escape.json_encode("ok"))

class Main(cyclone.web.RequestHandler):
    def get(self):
        self.redirect('/static/index.html')


restApp = cyclone.web.Application([
    (r'/project', Project),
    (r'/project/?(.*)', Project),
    (r'/branch/(.*)', Branch),
    (r'/clear/(.*)', Clear),
    (r'/build/current', Current),
    (r'/build/(.*)', Build),
    (r'/group', Group),
    (r'/group/?(.*)', Group),
    (r'/log/(.*)/+(.*)', Log),
    (r'/static/(.*)', cyclone.web.StaticFileHandler, {'path': brickconfig.get('static', 'dir')}),
    (r'/repo/(.*)', cyclone.web.StaticFileHandler, {'path': brickconfig.get('local_repo', 'dir')}),
    (r'/', Main),
])

application = service.Application("bricklayer_rest")
server = internet.TCPServer(int(brickconfig.get('server', 'port')), restApp, interface="0.0.0.0")
server.setServiceParent(application)
