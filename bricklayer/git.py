import os 
import subprocess
import re
import shutil
import traceback
from twisted.python import log
from config import BrickConfig

class Git(object):
    def __init__(self, project, workdir=None):
        _workdir = workdir
        if not _workdir:
            _workdir = BrickConfig().get('workspace', 'dir')
        self.workdir = os.path.join(_workdir, project.name)
        self.project = project

    def _exec_git(self, cmd=[], cwd='.', stdout=None):
        if stdout is None:
            stdout = open('/dev/null', 'w')
        return subprocess.Popen(" ".join(cmd), cwd=cwd, shell=True, stdout=stdout, stderr=stdout)

    def clone(self, branch=None):
        try:
            if (os.path.exists(self.workdir)):
                shtuil.rmtree(self.workdir, ignore_errors=True)
            git_cmd = self._exec_git(['timeout', '300', 'git', 'clone', self.project.git_url, self.workdir], stdout=subprocess.PIPE)
            status = git_cmd.wait() == 0
            log.msg("[%s] git clone %s = %s" % (self.workdir, self.project.git_url, status))
            if branch:
                self.checkout_branch(branch)
        except Exception, e:
            log.msg("[%s] %s" % (self.workdir, traceback.format_exc()))
            status = False
        if (not status):
            shutil.rmtree(self.workdir, ignore_errors=True)
        return(status)

    def reset(self):
        git_cmd = self._exec_git(['git', 'reset', 'HEAD'], cwd=self.workdir)
        git_cmd.wait()
    
    def pull(self):
        status = True
        try:
            for cmd in [['timeout', '300', 'git', 'pull', '--ff-only'], ['timeout', '300', 'git', 'fetch', '--tags']]:
                git_cmd = self._exec_git(cmd, cwd=self.workdir)
                status = status and (git_cmd.wait() == 0)
        except:
            log.msg("[%s] %s" % (self.workdir, traceback.format_exc()))
            status = False
        if (not status):
            shutil.rmtree(self.workdir, ignore_errors=True)
        return(status)
    
    def checkout_tag(self, tag='master'):
        git_cmd = self._exec_git(['git', 'checkout', '-f', tag], stdout=subprocess.PIPE, cwd=self.workdir)
        s = git_cmd.wait()
        if s != 0:
            log.msg("[%s] checkout fail" % (self.workdir,))

    def checkout_branch(self, branch):
        if branch in self.branches():
            git_cmd = self._exec_git(['git', 'checkout', branch], cwd=self.workdir)
            git_cmd.wait()

    def checkout_remote_branch(self, branch):
        git_cmd = self._exec_git(
                ['git', 'checkout', '-b', branch, '--track', 'origin/%s' % branch], 
                cwd=self.workdir
            )
        git_cmd.wait()

    def branches(self, remote=False):
        if remote:
            git_cmd = self._exec_git("git branch -r".split(), stdout=subprocess.PIPE, cwd=self.workdir) 
        else:
            git_cmd = self._exec_git("git branch".split(), stdout=subprocess.PIPE, cwd=self.workdir) 
        branch_list = git_cmd.stdout.readlines()
        
        return map(lambda x: x.strip(), branch_list)

    def clear_repo(self):
        try:
            shutil.rmtree(self.workdir)
        except Exception, e:
            pass
            

    def last_commit(self, branch='master'):
        cf = os.path.join(self.workdir, '.git', 'refs', 'heads', branch)
        if os.path.exists(cf):
            return open(cf).read()

    def last_tag(self, tag_type):
        tags = self.tags(tag_type)
        check = []
        for tag in tags:
            if re.match("(\w+)_(\d+\.\d+\.\d+)", tag):
                tag_v = tag.split('_')[1].split("-")[0]
                check.append(map(int, tag_v.split('.')))
            else:
                continue
        if len(check) > 0:
            return tag_type + "_%d.%d.%d" % tuple(max(check))
        else:
            return ''    

    def tags(self, tag_type):
        try:
            git_cmd = self._exec_git(['git', 'tag', '-l'], stdout=subprocess.PIPE, cwd=self.workdir)
            git_cmd.wait()
            tags = git_cmd.stdout.readlines()
            result = []
            if tag_type:
                for t in tags:
                    if t.startswith(tag_type):
                        result.append(t.strip('\n'))
            else:
                for t in tags:
                    result.append(t.strip('\n'))
            return result

        except Exception, e:
            log.msg("[%s] %s" % (self.workdir, traceback.format_exc()))
            return []

    def create_tag(self, tag=''):
        git_cmd = self._exec_git(['git', 'tag', str(tag)], cwd=self.workdir)
        git_cmd.wait()

    def create_branch(self, branch=''):
        git_cmd = self._exec_git(['git', 'checkout', '-b', branch], cwd=self.workdir)
        git_cmd.wait()

    def log(self, number=3):
        git_cmd = self._exec_git(['git', 'log', '-n', str(number),
             '--pretty=oneline', '--abbrev-commit'], cwd=self.workdir, stdout=subprocess.PIPE)
        git_cmd.wait()
        return git_cmd.stdout.readlines()

    def push_tags(self):
        git_cmd = self._exec_git(['git', 'push', '--tags'])
        git_cmd.wait()
